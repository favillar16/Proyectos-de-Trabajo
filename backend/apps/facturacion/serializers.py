"""
Serializers de facturación electrónica.

Por ahora solo los datos de traslado. El resto de la app serializa a mano en
`views.py` porque son respuestas de lectura armadas a medida; acá hace falta
un serializer de verdad porque esto **entra** datos: veinticinco campos que
un formulario escribe y que después tienen que sobrevivir la validación del
SIFEN.
"""
from rest_framework import serializers

from . import codigos
from .models import DatosTraslado


class DatosTrasladoSerializer(serializers.ModelSerializer):
    """
    Los datos del traslado, tal como los carga la pantalla.

    Dos cosas que hace a propósito:

    · **Corre `full_clean()` del modelo.** Las reglas que hacen que la nota de
      remisión no vuelva rechazada —vehículo identificable, dirección de
      entrega, kilómetros de la NT 010— viven en `DatosTraslado.clean()`, y un
      `ModelSerializer` de DRF **no** las ejecuta solo. Sin este paso la
      pantalla dejaría guardar un traslado que después no se puede emitir, y
      el error aparecería recién en el worker, horas más tarde.

    · **Devuelve las descripciones además de los códigos.** El formulario
      muestra "Traslado por venta", no el número 1, y la lista de opciones la
      sirve `OpcionesTrasladoView` desde `codigos.py`. Así la tabla de la DNIT
      vive en un solo lugar.
    """

    motivo_descripcion = serializers.SerializerMethodField()
    responsable_descripcion = serializers.SerializerMethodField()
    modalidad_descripcion = serializers.SerializerMethodField()
    pedido_numero = serializers.CharField(source='pedido.numero', read_only=True)

    class Meta:
        model = DatosTraslado
        fields = [
            'id', 'pedido', 'pedido_numero',
            # E6 — motivo y responsable
            'motivo', 'motivo_descripcion',
            'responsable', 'responsable_descripcion',
            'fecha_inicio_traslado', 'fecha_fin_traslado', 'kilometros',
            # E10 — transporte
            'tipo_transporte', 'modalidad', 'modalidad_descripcion',
            'responsable_flete',
            'vehiculo_tipo', 'vehiculo_marca',
            'vehiculo_matricula', 'vehiculo_numero',
            'tipo_identificacion_vehiculo',
            # E10.4 — transportista y chofer
            'transportista_nombre', 'transportista_ruc',
            'transportista_documento', 'transportista_direccion',
            'conductor_nombre', 'conductor_documento', 'conductor_direccion',
            # Direcciones
            'direccion_salida', 'salida_numero_casa',
            'salida_ciudad', 'salida_ciudad_desc',
            'direccion_entrega', 'entrega_numero_casa',
            'entrega_departamento', 'entrega_departamento_desc',
            'entrega_distrito', 'entrega_distrito_desc',
            'entrega_ciudad', 'entrega_ciudad_desc',
            'fecha_creacion',
        ]
        read_only_fields = ['id', 'pedido', 'pedido_numero', 'fecha_creacion',
                            'tipo_identificacion_vehiculo']

    def get_motivo_descripcion(self, obj):
        return codigos.MOTIVOS_TRASLADO.get(obj.motivo, '')

    def get_responsable_descripcion(self, obj):
        return codigos.RESPONSABLES_REMISION.get(obj.responsable, '')

    def get_modalidad_descripcion(self, obj):
        return codigos.MODALIDADES_TRANSPORTE.get(obj.modalidad, '')

    def validate(self, datos):
        """
        Aplica las reglas del modelo antes de guardar.

        `ModelSerializer` valida campo por campo pero no llama a `clean()`, así
        que las reglas que miran varios campos a la vez —la que exige matrícula
        **o** número de vehículo es la típica— se perderían. Acá se arma la
        instancia completa (la de la base más los cambios, si es una edición) y
        se la valida entera.
        """
        from django.core.exceptions import ValidationError as ErrorDeModelo

        instancia = self.instance
        if instancia is None:
            instancia = DatosTraslado(**{
                campo: valor for campo, valor in datos.items()
                if campo in {f.name for f in DatosTraslado._meta.get_fields()
                             if hasattr(f, 'name')}
            })
        else:
            for campo, valor in datos.items():
                setattr(instancia, campo, valor)

        try:
            instancia.clean()
        except ErrorDeModelo as e:
            # `clean()` lanza el error del modelo con el nombre del campo
            # adentro; DRF quiere el suyo. Se traduce para que el formulario
            # pueda marcar el campo que está mal en vez de mostrar un cartel
            # genérico arriba de todo.
            raise serializers.ValidationError(
                e.message_dict if hasattr(e, 'message_dict') else e.messages)
        return datos
