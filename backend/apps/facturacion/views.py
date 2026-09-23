"""
API de facturación electrónica.

Poco y concreto: emitir una nota de crédito, cancelar o inutilizar
comprobantes, y mirar el estado de la cola. La emisión de facturas no está
acá — sale sola al confirmar un cobro, desde `apps/caja/views.py`.
"""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.permissions import (EsAdmin, EsAdminOCajero,
                                       EsAdminVendedorODeposito)

from . import cdc as cdc_mod
from . import (autofactura, codigos, eventos, eventos_receptor, kude,
               nota_credito, nota_debito, remision, sifen_client,
               transmision)
from .emisor import sifen_activo
from .models import (DocumentoElectronico, EventoDocumento, EventoReceptor,
                     LoteTransmision)
from .payload import _fiscal
from .serializers import DatosTrasladoSerializer

logger = logging.getLogger(__name__)


def _serializar(documento) -> dict:
    return {
        'id': documento.pk,
        'tipo_documento': documento.tipo_documento,
        'tipo_descripcion': codigos.DESCRIPCION_TIPO_DE.get(
            documento.tipo_documento, ''),
        'cdc': documento.cdc,
        'cdc_legible': cdc_mod.formatear_legible(documento.cdc),
        'numero': documento.numero_completo,
        'fecha_emision': documento.fecha_emision,
        'estado': documento.estado,
        'estado_display': documento.get_estado_display(),
        'total': documento.total,
        'receptor_razon_social': documento.receptor_razon_social,
        'receptor_ruc': documento.receptor_ruc,
        'documento_asociado_cdc': documento.documento_asociado_cdc,
        'motivo_nota': documento.motivo_nota,
        'motivo_descripcion': codigos.MOTIVOS_NOTA.get(documento.motivo_nota, ''),
        'intentos_envio': documento.intentos_envio,
        'codigo_respuesta': documento.codigo_respuesta,
        'fecha_aprobacion': documento.fecha_aprobacion,
        # Lo que la pantalla necesita para saber si ofrecer "Cancelar" y con
        # cuánto apuro: el plazo corre desde la aprobación del SIFEN.
        'horas_para_cancelar': eventos.horas_restantes(documento),
        'impedimento_cancelacion':
            eventos.motivo_por_el_que_no_se_puede_cancelar(documento),
    }


class MotivosNotaView(APIView):
    """
    Los motivos de nota de crédito que acepta el SIFEN.

    Se sirven desde el backend para que la pantalla no tenga su propia copia
    de la tabla: si la DNIT cambia un código, se cambia en `codigos.py` y la
    UI lo refleja sin recompilar.
    """
    permission_classes = [IsAuthenticated, EsAdminOCajero]

    def get(self, request):
        return Response([
            {'codigo': codigo,
             'descripcion': texto,
             'devuelve_mercaderia': codigo in nota_credito.MOTIVOS_QUE_DEVUELVEN_MERCADERIA}
            for codigo, texto in codigos.MOTIVOS_NOTA.items()
        ])


class EmitirNotaCreditoView(APIView):
    """
    POST /api/v1/facturacion/documentos/<pk>/nota-credito/

    Emite la nota de crédito que revierte la factura `pk`.

    Solo admin: anular una venta ya facturada mueve stock y plata, y deja un
    documento tributario nuevo. No es una operación de mostrador.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def post(self, request, pk):
        factura = DocumentoElectronico.objects.filter(pk=pk).first()
        if factura is None:
            return Response({'error': 'No existe ese documento.'},
                            status=status.HTTP_404_NOT_FOUND)

        try:
            motivo = int(request.data.get('motivo'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'Falta indicar el motivo de la nota de crédito.'},
                status=status.HTTP_400_BAD_REQUEST)

        reponer = request.data.get('reponer_stock')
        if reponer is not None:
            reponer = bool(reponer)

        try:
            nota = nota_credito.emitir(
                factura,
                motivo=motivo,
                usuario=request.user,
                reponer_stock=reponer,
                observacion=request.data.get('observacion', ''),
            )
        except nota_credito.NotaCreditoInvalida as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # A diferencia de la emisión de facturas, acá SÍ conviene que el
            # error llegue al usuario: no hay una venta en curso que
            # proteger, y una nota a medias es peor que ninguna.
            logger.exception('Error al emitir la nota de crédito de %s', pk)
            return Response(
                {'error': f'No se pudo emitir la nota de crédito: {e}'},
                status=status.HTTP_400_BAD_REQUEST)

        return Response({'ok': True, 'nota_credito': _serializar(nota)},
                        status=status.HTTP_201_CREATED)


class EmitirRemisionView(APIView):
    """
    POST /api/v1/facturacion/pedidos/<pedido_id>/remision/

    Emite la nota de remisión que respalda el traslado de un pedido.

    Va por pedido y no por documento porque es el pedido el que tiene los
    datos del traslado, y porque quien decide que hay que emitirla es quien
    despacha la mercadería.

    **No se emite sola al cobrar, a propósito.** El Decreto 6.539/2005 ata la
    remisión al traslado, no a la venta, y la RG 41/2014 art. 5 exime de
    emitirla cuando la mercadería viaja acompañada del comprobante de venta.
    El cliente que se lleva los pisos en su camioneta con la factura no
    necesita ninguna; el pedido que sale en el flete del local, sí. Esa
    diferencia la sabe la persona que despacha, no el sistema — de ahí que
    sea un botón.

    Mismos roles que la carga del traslado: depósito prepara la entrega y ve
    el camión, vendedor y encargada cierran la venta, admin todo.
    """
    permission_classes = [IsAuthenticated, EsAdminVendedorODeposito]

    def post(self, request, pedido_id):
        from apps.ventas.models import NotaPedido

        pedido = get_object_or_404(NotaPedido, pk=pedido_id)

        # La remisión cuelga del cobro porque el DocumentoElectronico cuelga
        # del cobro. En este negocio se paga y después se despacha, así que
        # el orden coincide; si algún día se despacha antes de cobrar hay que
        # revisar esto, no forzarlo acá.
        from apps.caja.models import Pago
        pago = pedido.pagos.filter(estado=Pago.ESTADO_CONFIRMADO).first()
        if pago is None:
            return Response(
                {'error': f'El pedido {pedido.numero} no tiene un cobro '
                          f'confirmado. La nota de remisión se emite sobre el '
                          f'cobro del pedido.'},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            nota = remision.emitir(pago, usuario=request.user)
        except remision.RemisionInvalida as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(
                'Error al emitir la nota de remisión del pedido %s', pedido_id)
            return Response(
                {'error': f'No se pudo emitir la nota de remisión: {e}'},
                status=status.HTTP_400_BAD_REQUEST)

        return Response({'ok': True, 'remision': _serializar(nota)},
                        status=status.HTTP_201_CREATED)

    def get(self, request, pedido_id):
        """
        La remisión del pedido, si ya se emitió.

        La pantalla la necesita para decidir entre mostrar el botón de emitir
        o el de descargar el KuDE.
        """
        from apps.ventas.models import NotaPedido

        pedido = get_object_or_404(NotaPedido, pk=pedido_id)
        nota = DocumentoElectronico.objects.filter(
            pago__pedido=pedido,
            tipo_documento=codigos.TIPO_DE_NOTA_REMISION,
        ).exclude(estado=DocumentoElectronico.ESTADO_RECHAZADO).first()

        if nota is None:
            return Response({'existe': False, 'pedido': pedido.pk})
        datos = _serializar(nota)
        datos['existe'] = True
        return Response(datos)


class EmitirNotaDebitoView(APIView):
    """
    POST /api/v1/facturacion/documentos/<pk>/nota-debito/

    Emite una nota de débito sobre la factura `pk`: le suma un importe a lo
    que el cliente debe (interés por mora, recupero de flete, ajuste de
    precio hacia arriba).

    Body: `{"motivo": 8, "monto": 150000, "tasa_iva": 10}`. El monto va **con
    IVA incluido**, igual que todos los precios del sistema.

    Solo admin: emite un documento tributario nuevo y cambia lo que el
    cliente debe. No es una operación de mostrador.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def post(self, request, pk):
        factura = DocumentoElectronico.objects.filter(pk=pk).first()
        if factura is None:
            return Response({'error': 'No existe ese documento.'},
                            status=status.HTTP_404_NOT_FOUND)

        try:
            motivo = int(request.data.get('motivo'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'Falta indicar el motivo de la nota de débito.'},
                status=status.HTTP_400_BAD_REQUEST)

        tasa = request.data.get('tasa_iva')
        if tasa is not None:
            try:
                tasa = int(tasa)
            except (TypeError, ValueError):
                return Response({'error': 'Tasa de IVA inválida.'},
                                status=status.HTTP_400_BAD_REQUEST)

        try:
            nota = nota_debito.emitir(
                factura, motivo=motivo, monto=request.data.get('monto'),
                usuario=request.user, tasa_iva=tasa)
        except nota_debito.NotaDebitoInvalida as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception('Error al emitir la nota de débito de %s', pk)
            return Response(
                {'error': f'No se pudo emitir la nota de débito: {e}'},
                status=status.HTTP_400_BAD_REQUEST)

        return Response({'ok': True, 'nota_debito': _serializar(nota)},
                        status=status.HTTP_201_CREATED)


class MotivosDebitoView(APIView):
    """
    GET /api/v1/facturacion/motivos-debito/

    Los motivos que tienen sentido en una nota de débito. Es una lista más
    corta que la de crédito: los de devolución quedan afuera porque devolver
    mercadería baja lo que el cliente debe, no lo sube.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response([{'codigo': c, 'descripcion': d}
                         for c, d in nota_debito.MOTIVOS_DEBITO.items()])


class GeografiaView(APIView):
    """
    GET /api/v1/facturacion/geografia/
    GET /api/v1/facturacion/geografia/?departamento=6
    GET /api/v1/facturacion/geografia/?distrito=61

    Las tablas geográficas de la DNIT: departamentos, sus distritos y las
    ciudades de cada distrito.

    Se sirven desde acá y no se copian al frontend por la misma razón que
    `opciones-traslado`: son tablas de la DNIT y tener una segunda copia en
    la UI garantiza que un día queden desfasadas. Vienen adentro de `xmlgen`,
    así que las sirve el sidecar — **no necesitan certificado ni internet**,
    es un archivo de la librería.

    Las usa el formulario de autofactura, que es el único que pide un
    domicilio codificado cargado a mano.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def get(self, request):
        cuerpo = {}
        if request.query_params.get('distrito'):
            cuerpo['distrito'] = request.query_params['distrito']
        elif request.query_params.get('departamento'):
            cuerpo['departamento'] = request.query_params['departamento']

        try:
            return Response(sifen_client.geografia(cuerpo))
        except Exception as e:
            return Response(
                {'error': f'No se pudieron leer las tablas geográficas: {e}'},
                status=status.HTTP_502_BAD_GATEWAY)


class AutofacturaView(APIView):
    """
    POST /api/v1/facturacion/autofacturas/

    Emite una autofactura: el comprobante de una **compra** a alguien que no
    puede facturar (un particular, alguien sin RUC). Es el único de los cinco
    tipos que no documenta una venta, y por eso no cuelga de un cobro.

    Body: `{"vendedor": {...}, "items": [{descripcion, cantidad,
    precio_unitario, tasa_iva}]}`.

    Solo admin: respalda un gasto del negocio ante la DNIT.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def get(self, request):
        documentos = DocumentoElectronico.objects.filter(
            tipo_documento=codigos.TIPO_DE_AUTOFACTURA
        ).select_related('datos_autofactura')[:100]
        salida = []
        for d in documentos:
            fila = _serializar(d)
            datos = getattr(d, 'datos_autofactura', None)
            fila['vendedor'] = datos.nombre_vendedor if datos else ''
            salida.append(fila)
        return Response(salida)

    def post(self, request):
        vendedor = request.data.get('vendedor') or {}
        items = request.data.get('items') or []
        try:
            documento = autofactura.emitir(
                vendedor=vendedor, items=items, usuario=request.user)
        except autofactura.AutofacturaInvalida as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception('Error al emitir la autofactura')
            return Response({'error': f'No se pudo emitir la autofactura: {e}'},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({'ok': True, 'autofactura': _serializar(documento)},
                        status=status.HTTP_201_CREATED)


class EventosReceptorView(APIView):
    """
    GET  /api/v1/facturacion/eventos-receptor/  — los registrados
    POST /api/v1/facturacion/eventos-receptor/  — registra uno nuevo

    Lo que el local declara sobre un DTE que le emitió **otro**: la factura de
    un proveedor. Por eso se identifica por CDC y no por documento propio —
    ese documento no está en esta base.

    Body del POST: `{"tipo", "cdc", ...}`, y según el tipo:
      · conformidad    → `tipo_conformidad` (1 total, 2 parcial) y, si es
                         parcial, `fecha_recepcion`
      · disconformidad → `motivo` (5 a 500 caracteres)
      · desconocimiento→ `motivo`, `fecha_emision_documento`, `fecha_recepcion`
      · notificacion   → `fecha_emision_documento`, `fecha_recepcion`,
                         `total_documento`

    Se guarda y se transmite en el acto si se puede; si el sidecar no
    contesta, queda pendiente y lo levanta el worker. Solo admin: es una
    declaración del negocio ante la DNIT.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def get(self, request):
        eventos_ = EventoReceptor.objects.all()[:100]
        return Response([{
            'id': e.pk,
            'tipo': e.tipo,
            'tipo_display': e.get_tipo_display(),
            'conclusivo': e.es_conclusivo,
            'cdc': e.cdc,
            'cdc_legible': cdc_mod.formatear_legible(e.cdc),
            'motivo': e.motivo,
            'estado': e.estado,
            'estado_display': e.get_estado_display(),
            'intentos_envio': e.intentos_envio,
            'codigo_respuesta': e.codigo_respuesta,
            'fecha_creacion': e.fecha_creacion,
            'creado_por': e.creado_por.nombre_completo,
        } for e in eventos_])

    def post(self, request):
        datos = request.data
        try:
            evento = eventos_receptor.registrar(
                tipo=datos.get('tipo'),
                cdc=datos.get('cdc'),
                usuario=request.user,
                motivo=datos.get('motivo', ''),
                tipo_conformidad=(int(datos['tipo_conformidad'])
                                  if datos.get('tipo_conformidad') else None),
                fecha_recepcion=datos.get('fecha_recepcion') or None,
                fecha_emision_documento=datos.get('fecha_emision_documento') or None,
                total_documento=datos.get('total_documento'),
            )
        except eventos_receptor.EventoReceptorInvalido as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        except (TypeError, ValueError) as e:
            return Response({'error': f'Datos inválidos: {e}'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Se intenta mandarlo ya. Si no sale, queda pendiente: el evento
        # está guardado, que es lo que importa.
        eventos_receptor.transmitir(evento)

        return Response({
            'ok': True,
            'id': evento.pk,
            'estado': evento.estado,
            'estado_display': evento.get_estado_display(),
            'respuesta': evento.respuesta_sifen[:500],
        }, status=status.HTTP_201_CREATED)


class ConsultaRucView(APIView):
    """
    GET /api/v1/facturacion/consulta-ruc/?ruc=80012345

    Consulta un RUC en el padrón de la DNIT.

    Dos motivos para tenerlo: es uno de los web services contra los que la
    Guía de Pruebas exige ejercitar la autenticación mutua, y —fuera de la
    habilitación— permite verificar el RUC del cliente **antes** de emitir,
    en vez de enterarse de que estaba mal cuando el documento vuelve
    rechazado.

    Necesita el certificado y conexión: no se puede usar como validación
    obligatoria del cobro. Es una ayuda, no una barrera.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ruc = (request.query_params.get('ruc') or '').strip()
        if not ruc:
            return Response({'error': 'Falta el parámetro ruc.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            return Response(sifen_client.consultar_ruc(ruc))
        except Exception as e:
            # No se propaga como 500: que el padrón de la DNIT no conteste no
            # es un error del sistema, y quien llama tiene que poder seguir.
            return Response({'error': f'No se pudo consultar el RUC: {e}'},
                            status=status.HTTP_502_BAD_GATEWAY)


class LotesView(APIView):
    """
    GET  /api/v1/facturacion/lotes/   — los lotes enviados y su estado
    POST /api/v1/facturacion/lotes/   — arma y manda un lote con la cola

    El camino asincrónico. A diferencia del sincrónico, el SIFEN contesta un
    número de lote y procesa después: por eso un lote recién enviado queda en
    'enviado' y hay que volver a preguntar por su resultado.

    `POST {"consultar": true}` pide el resultado de los lotes que todavía no
    lo tienen, en vez de mandar uno nuevo.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def get(self, request):
        lotes = LoteTransmision.objects.all()[:50]
        return Response([{
            'id': l.pk,
            'numero': l.numero,
            'estado': l.estado,
            'estado_display': l.get_estado_display(),
            'cantidad': l.cantidad,
            'consultas': l.consultas,
            'fecha_envio': l.fecha_envio,
            'fecha_resultado': l.fecha_resultado,
            'codigo_respuesta': l.codigo_respuesta,
            'aprobados': l.documentos.filter(
                estado=DocumentoElectronico.ESTADO_APROBADO).count(),
            'rechazados': l.documentos.filter(
                estado=DocumentoElectronico.ESTADO_RECHAZADO).count(),
        } for l in lotes])

    def post(self, request):
        if request.data.get('consultar'):
            resumenes = []
            for lote in transmision.lotes_sin_resultado():
                try:
                    resumen = transmision.consultar_lote(lote)
                    resumen['numero'] = lote.numero
                    resumenes.append(resumen)
                except Exception as e:
                    resumenes.append({'numero': lote.numero,
                                      'detalle': f'No se pudo consultar: {e}'})
            return Response({'ok': True, 'lotes': resumenes})

        limite = min(int(request.data.get('limite') or transmision.MAXIMO_POR_LOTE),
                     transmision.MAXIMO_POR_LOTE)
        documentos = transmision.pendientes(limite)
        if not documentos:
            return Response({'error': 'No hay documentos pendientes de envío.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            lote = transmision.transmitir_lote(documentos, usuario=request.user)
        except ValueError as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception('Error al transmitir el lote')
            return Response({'error': f'No se pudo enviar el lote: {e}'},
                            status=status.HTTP_502_BAD_GATEWAY)

        return Response({'ok': True, 'numero': lote.numero,
                         'cantidad': lote.cantidad},
                        status=status.HTTP_201_CREATED)


class VentasSinDocumentoView(APIView):
    """
    GET /api/v1/facturacion/ventas-sin-documento/

    Los cobros marcados como **factura** que no tienen documento electrónico.

    Existe porque hay un punto ciego: `emisor.emitir_para_pago()` no lanza
    nunca y devuelve `None` si algo falla. Es deliberado —hay alguien
    esperando en el mostrador y un problema de facturación no puede tumbar un
    cobro ya hecho—, pero la consecuencia era que la venta se completaba, el
    ticket salía sin CDC y **nadie se enteraba**: quedaba solo en el log. Y
    después no había dónde verlo, porque la cola de documentos lista los
    `DocumentoElectronico` que existen; un cobro facturado que nunca llegó a
    generar uno era invisible para el sistema.

    La misma lista sirve para dos cosas distintas según el interruptor, y por
    eso la respuesta incluye `sifen_habilitado`:

    · **Con el SIFEN apagado** (hoy) aparecen todas, y está bien: ninguna
      emite. Es la lista de ventas a cargar a mano en el portal.
    · **Con el SIFEN prendido**, cada fila es una alarma: una venta que
      debería tener comprobante fiscal y no lo tiene.

    Solo admin: es información fiscal del negocio entero.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    # Tope de filas. Sin esto, con el SIFEN apagado la consulta arrastra el
    # historial completo de facturas del local.
    LIMITE = 200

    def get(self, request):
        from apps.caja.models import Pago

        con_documento = DocumentoElectronico.objects.filter(
            tipo_documento=codigos.TIPO_DE_FACTURA).values('pago_id')

        pagos = (Pago.objects
                 .filter(tipo_comprobante='factura',
                         estado=Pago.ESTADO_CONFIRMADO)
                 .exclude(pk__in=con_documento)
                 .select_related('pedido', 'cajero')
                 .order_by('-fecha'))

        desde = request.query_params.get('desde')
        if desde:
            pagos = pagos.filter(fecha__date__gte=desde)

        total = pagos.count()
        filas = [{
            'pago_id':        p.pk,
            'numero_ticket':  p.numero_ticket,
            'fecha':          p.fecha,
            'pedido_numero':  p.pedido.numero if p.pedido_id else '',
            'cliente_ruc':    p.cliente_ruc,
            'cliente_razon_social': p.cliente_razon_social,
            'monto':          p.monto,
            'cajero':         p.cajero.nombre_completo if p.cajero_id else '',
        } for p in pagos[:self.LIMITE]]

        return Response({
            'sifen_habilitado': sifen_activo(),
            'total':            total,
            'truncado':         total > self.LIMITE,
            'resultados':       filas,
        })


class ColaDocumentosView(APIView):
    """
    GET /api/v1/facturacion/documentos/

    Estado de los documentos electrónicos. Es lo mínimo para que alguien
    pueda ver si hay algo trabado sin entrar por SSH a correr un comando.

    Filtros: `estado`, y `pendientes=1` para los que todavía se van a
    reintentar.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def get(self, request):
        consulta = DocumentoElectronico.objects.select_related('pago').all()

        estado = request.query_params.get('estado')
        if estado:
            consulta = consulta.filter(estado=estado)
        if request.query_params.get('pendientes') == '1':
            consulta = consulta.filter(
                estado__in=DocumentoElectronico.ESTADOS_TRANSMITIBLES)

        resumen = {clave: DocumentoElectronico.objects.filter(estado=clave).count()
                   for clave, _ in DocumentoElectronico.ESTADOS}

        return Response({
            'resumen': resumen,
            'documentos': [_serializar(d) for d in consulta[:100]],
        })


# ─── Datos de traslado (nota de remisión) ────────────────────────────────────

class OpcionesTrasladoView(APIView):
    """
    GET /api/v1/facturacion/opciones-traslado/

    Las tablas de códigos que el formulario de traslado necesita para sus
    desplegables: motivos, responsables, modalidades, tipos de transporte y
    responsables del flete.

    Se sirven desde el backend por la misma razón que los motivos de nota de
    crédito: si la DNIT cambia un código se toca `codigos.py` y nada más. Una
    copia de la tabla en el frontend sería una segunda fuente de verdad que
    algún día se va a desincronizar, y un código de estos mal puesto es un
    documento rechazado.

    Incluye además los valores que el negocio usa casi siempre, para que la
    pantalla pueda abrir con el formulario ya lleno: acá el caso normal es
    traslado por venta, con el camión propio.
    """
    permission_classes = [IsAuthenticated, EsAdminVendedorODeposito]

    def get(self, request):
        def opciones(tabla):
            return [{'codigo': c, 'descripcion': d} for c, d in tabla.items()]

        return Response({
            'motivos':      opciones(codigos.MOTIVOS_TRASLADO),
            'responsables': opciones(codigos.RESPONSABLES_REMISION),
            'modalidades':  opciones(codigos.MODALIDADES_TRANSPORTE),
            'tipos_transporte': [
                {'codigo': codigos.TRANSPORTE_PROPIO,  'descripcion': 'Propio'},
                {'codigo': codigos.TRANSPORTE_TERCERO, 'descripcion': 'De terceros'},
            ],
            'responsables_flete': [
                {'codigo': codigos.FLETE_EMISOR,   'descripcion': 'Emisor de la factura'},
                {'codigo': codigos.FLETE_RECEPTOR, 'descripcion': 'Receptor'},
                {'codigo': codigos.FLETE_TERCERO,  'descripcion': 'Un tercero'},
                {'codigo': codigos.FLETE_AGENTE_INTERMEDIARIO,
                 'descripcion': 'Agente intermediario'},
                {'codigo': codigos.FLETE_TRANSPORTE_PROPIO,
                 'descripcion': 'Transporte propio'},
            ],
            # Lo que el negocio hace casi siempre: entrega su propia venta con
            # su camión. Con esto el formulario abre prácticamente completo y
            # la persona que lo carga solo pone la chapa y la dirección.
            'sugeridos': {
                'motivo':            codigos.TRASLADO_POR_VENTA,
                'responsable':       codigos.RESPONSABLE_EMISOR_FACTURA,
                'tipo_transporte':   codigos.TRANSPORTE_PROPIO,
                'modalidad':         codigos.MODALIDAD_TERRESTRE,
                'responsable_flete': codigos.FLETE_TRANSPORTE_PROPIO,
                'vehiculo_tipo':     'Camion',
                'direccion_salida':  _fiscal().get('direccion', ''),
            },
        })


class DatosTrasladoView(APIView):
    """
    GET/PUT/DELETE /api/v1/facturacion/pedidos/<pedido_id>/traslado/

    Los datos del traslado de un pedido. Es lo que faltaba para poder emitir
    la nota de remisión: el XML ya salía bien, pero nadie tenía dónde cargar
    el motivo, el vehículo y la dirección de entrega.

    Se usa PUT y no POST/PATCH separados porque hay uno solo por pedido
    (`OneToOne`): el formulario manda el estado completo y el endpoint decide
    si crea o actualiza. Para quien carga la pantalla, guardar es una sola
    acción y no tiene por qué saber si ya existía.

    Depósito puede cargarlo —es quien prepara la entrega y ve el camión— y
    también vendedor, encargada y admin.
    """
    permission_classes = [IsAuthenticated, EsAdminVendedorODeposito]

    def _pedido(self, pedido_id):
        from apps.ventas.models import NotaPedido
        return get_object_or_404(NotaPedido, pk=pedido_id)

    def get(self, request, pedido_id):
        pedido = self._pedido(pedido_id)
        traslado = getattr(pedido, 'datos_traslado', None)
        if traslado is None:
            # No es un error: la mayoría de los pedidos no se entregan con
            # remisión. La pantalla lo trata como "todavía no se cargó" y
            # abre el formulario vacío, no un cartel de error.
            return Response({'existe': False, 'pedido': pedido.pk,
                             'pedido_numero': pedido.numero})
        datos = DatosTrasladoSerializer(traslado).data
        datos['existe'] = True
        return Response(datos)

    def put(self, request, pedido_id):
        pedido = self._pedido(pedido_id)
        traslado = getattr(pedido, 'datos_traslado', None)

        serializer = DatosTrasladoSerializer(instance=traslado,
                                             data=request.data)
        serializer.is_valid(raise_exception=True)

        if traslado is None:
            traslado = serializer.save(pedido=pedido, creado_por=request.user)
            creado = True
        else:
            traslado = serializer.save()
            creado = False

        logger.info('Datos de traslado %s para el pedido %s por %s',
                    'creados' if creado else 'actualizados',
                    pedido.numero, request.user)

        datos = DatosTrasladoSerializer(traslado).data
        datos['existe'] = True
        return Response(
            datos,
            status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)

    def delete(self, request, pedido_id):
        """
        Saca los datos de traslado de un pedido.

        Sirve para el caso real de haberlos cargado en el pedido equivocado.
        No se permite si la remisión ya se emitió: ahí el documento existe ante
        el DNIT, y borrar sus datos dejaría un DE sin respaldo. Para deshacer
        eso está el evento de cancelación, que todavía no se construyó.
        """
        pedido = self._pedido(pedido_id)
        traslado = getattr(pedido, 'datos_traslado', None)
        if traslado is None:
            return Response(status=status.HTTP_204_NO_CONTENT)

        emitida = DocumentoElectronico.objects.filter(
            pago__pedido=pedido,
            tipo_documento=codigos.TIPO_DE_NOTA_REMISION,
        ).exclude(estado=DocumentoElectronico.ESTADO_RECHAZADO).exists()
        if emitida:
            return Response(
                {'detail': 'El pedido ya tiene una nota de remisión emitida. '
                           'No se pueden borrar sus datos de traslado: para '
                           'anularla hay que cancelar el documento ante el '
                           'SIFEN.'},
                status=status.HTTP_409_CONFLICT)

        traslado.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Eventos: cancelación e inutilización (Fase C) ───────────────────────────

def _serializar_evento(evento) -> dict:
    return {
        'id': evento.pk,
        'tipo': evento.tipo,
        'tipo_display': evento.get_tipo_display(),
        'estado': evento.estado,
        'estado_display': evento.get_estado_display(),
        'motivo': evento.motivo,
        'documento_numero': (evento.documento.numero_completo
                             if evento.documento_id else ''),
        'documento_cdc': evento.documento.cdc if evento.documento_id else '',
        'rango': evento.rango_legible,
        'timbrado': evento.timbrado,
        'intentos_envio': evento.intentos_envio,
        'codigo_respuesta': evento.codigo_respuesta,
        'respuesta_sifen': evento.respuesta_sifen[:500],
        'fecha_creacion': evento.fecha_creacion,
        'creado_por': evento.creado_por.nombre_completo,
    }


class CancelarDocumentoView(APIView):
    """
    POST /api/v1/facturacion/documentos/<pk>/cancelar/   {"motivo": "..."}

    Cancela un DTE aprobado. Solo admin: el documento ya está en poder del
    SIFEN y del cliente, y la cancelación es una declaración ante la DNIT,
    no un "deshacer" del mostrador.

    Se intenta transmitir en el momento porque hay un plazo corriendo (48 h
    en la factura), pero si el sidecar no contesta el evento **igual queda
    registrado** y lo manda el worker. Por eso la respuesta distingue las dos
    cosas: `registrado` siempre, `estado` es lo que dijo el SIFEN.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def post(self, request, pk):
        documento = DocumentoElectronico.objects.filter(pk=pk).first()
        if documento is None:
            return Response({'error': 'No existe ese documento.'},
                            status=status.HTTP_404_NOT_FOUND)

        try:
            evento = eventos.registrar_cancelacion(
                documento, motivo=request.data.get('motivo', ''),
                usuario=request.user)
        except eventos.EventoNoPermitido as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as e:
            return Response({'error': ' '.join(e.messages)},
                            status=status.HTTP_400_BAD_REQUEST)

        if sifen_activo():
            eventos.transmitir(evento)
            documento.refresh_from_db()

        return Response({
            'registrado': True,
            'evento': _serializar_evento(evento),
            'documento': _serializar(documento),
        }, status=status.HTTP_201_CREATED)


class InutilizacionesView(APIView):
    """
    GET  /api/v1/facturacion/inutilizaciones/  — los eventos ya registrados
    POST /api/v1/facturacion/inutilizaciones/  — declara un rango sin usar

    Body del POST: tipo_documento, establecimiento, punto_expedicion,
    desde, hasta, motivo.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def get(self, request):
        consulta = EventoDocumento.objects.select_related(
            'documento', 'creado_por').all()
        tipo = request.query_params.get('tipo')
        if tipo:
            consulta = consulta.filter(tipo=tipo)
        return Response({'eventos': [_serializar_evento(e) for e in consulta[:100]]})

    def post(self, request):
        datos = request.data
        try:
            campos = dict(
                tipo_documento=int(datos.get('tipo_documento',
                                             codigos.TIPO_DE_FACTURA)),
                establecimiento=str(datos['establecimiento']),
                punto_expedicion=str(datos['punto_expedicion']),
                desde=int(datos['desde']),
                hasta=int(datos['hasta']),
            )
        except (KeyError, TypeError, ValueError):
            return Response(
                {'error': 'Faltan datos del rango: establecimiento, punto de '
                          'expedición, desde y hasta.'},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            evento = eventos.registrar_inutilizacion(
                motivo=datos.get('motivo', ''), usuario=request.user, **campos)
        except eventos.EventoNoPermitido as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as e:
            return Response({'error': ' '.join(e.messages)},
                            status=status.HTTP_400_BAD_REQUEST)

        if sifen_activo():
            eventos.transmitir(evento)

        # El plazo de la Tabla J no impide declarar, pero quien lo hace tiene
        # que enterarse de que va fuera de término: en el log no lo ve nadie.
        cuerpo = {'registrado': True, 'evento': _serializar_evento(evento)}
        aviso = eventos.advertencia_de_plazo_inutilizacion(
            campos['tipo_documento'], campos['establecimiento'],
            campos['punto_expedicion'], campos['hasta'])
        if aviso:
            cuerpo['advertencia'] = aviso

        return Response(cuerpo, status=status.HTTP_201_CREATED)


class NumerosSinUsarView(APIView):
    """
    GET /api/v1/facturacion/numeros-sin-usar/?tipo_documento=1&establecimiento=001&punto_expedicion=001

    Los números que la secuencia ya consumió y no terminaron en un
    comprobante. Son los candidatos a inutilizar, y nadie los va a encontrar
    mirando el correlativo a ojo: por eso la pantalla los pide en vez de que
    el operador escriba un rango de memoria.
    """
    permission_classes = [IsAuthenticated, EsAdmin]

    def get(self, request):
        try:
            tipo = int(request.query_params.get('tipo_documento',
                                                codigos.TIPO_DE_FACTURA))
            establecimiento = request.query_params.get('establecimiento') or \
                _fiscal().get('establecimiento', '001')
            punto = request.query_params.get('punto_expedicion') or \
                _fiscal().get('punto_expedicion', '001')
        except (TypeError, ValueError):
            return Response({'error': 'Parámetros inválidos.'},
                            status=status.HTTP_400_BAD_REQUEST)

        sueltos = eventos.huecos_de_numeracion(tipo, establecimiento, punto)
        return Response({
            'tipo_documento': tipo,
            'establecimiento': f'{int(establecimiento):03d}',
            'punto_expedicion': f'{int(punto):03d}',
            'numeros': sueltos,
            'rangos': _agrupar_en_rangos(sueltos),
        })


def _agrupar_en_rangos(numeros):
    """
    [3, 4, 5, 9] → [{'desde': 3, 'hasta': 5}, {'desde': 9, 'hasta': 9}].

    Se agrupa acá y no en la pantalla porque el evento se declara por rango:
    cuatro números corridos son un evento, no cuatro.
    """
    rangos = []
    for numero in numeros:
        if rangos and numero == rangos[-1]['hasta'] + 1:
            rangos[-1]['hasta'] = numero
        else:
            rangos.append({'desde': numero, 'hasta': numero})
    return rangos


# ─── KuDE: la representación gráfica del DE (Fase D) ─────────────────────────

class KudeView(APIView):
    """
    GET /api/v1/facturacion/documentos/<pk>/kude/

    Devuelve el PDF del KuDE. Lo puede sacar el cajero además del admin: es
    el papel que se le entrega al cliente, y pedírselo al dueño cada vez que
    alguien quiere su factura impresa no tendría sentido.

    Se arma en el momento y no se guarda: el KuDE es una vista del documento
    electrónico, así que si el documento cambia de estado —por ejemplo, se
    cancela— la reimpresión tiene que reflejarlo.
    """
    permission_classes = [IsAuthenticated, EsAdminOCajero]

    def get(self, request, pk):
        documento = DocumentoElectronico.objects.filter(pk=pk).select_related(
            'pago__pedido').first()
        if documento is None:
            return Response({'error': 'No existe ese documento.'},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            return kude.responder(documento)
        except Exception as e:
            logger.exception('No se pudo armar el KuDE de %s', pk)
            return Response(
                {'error': f'No se pudo armar la representación gráfica: {e}'},
                status=status.HTTP_400_BAD_REQUEST)
