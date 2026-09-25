"""
App: caja — Views
Flujo completo: apertura → cobro de pedidos → cierre de sesión.

Al confirmar un pago:
  1. Registra el Pago en BD
  2. Cambia el estado del pedido a 'pagado'
  3. Descuenta el stock de cada variante (MovimientoStock tipo 'salida')
  4. Emite evento WebSocket a vendedor y admin
  5. Si es factura, genera el documento electrónico (queda encolado para el
     SIFEN; no espera a la red — ver apps/facturacion/)
  6. Retorna datos para imprimir el ticket
"""
from rest_framework import views, status
from rest_framework.response import Response
from apps.usuarios.permissions import EsAdminOCajero, EsAdmin
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.conf import settings
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

from .models import DatosCheque, DatosTarjeta, Devolucion, SesionCaja, Pago
from .printer import (imprimir_ticket, imprimir_factura, imprimir_cierre,
                      imprimir_devolucion, ticket_a_texto,
                      ticket_devolucion_a_texto)
from apps.ventas.models import NotaPedido
from apps.facturacion import codigos
from apps.facturacion import emisor as fe_emisor
from . import cheque as cheque_mod
from . import devoluciones as devoluciones_mod
from . import pos as pos_mod

# Tope de descuento que puede aplicar un cajero al cobrar. Un 100% equivaldría
# a regalar la mercadería sin ninguna aprobación adicional; 70% ya cubre
# cualquier negociación real de piso de venta.
DESCUENTO_CAJA_MAXIMO = Decimal('70')


# ─── Serializers inline ───────────────────────────────────────────────────────

from rest_framework import serializers


class SesionCajaSerializer(serializers.ModelSerializer):
    cajero_nombre = serializers.CharField(source='cajero.nombre_completo', read_only=True)
    total_ventas  = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    cantidad_pagos = serializers.SerializerMethodField()

    class Meta:
        model  = SesionCaja
        fields = [
            'id', 'cajero_nombre', 'estado',
            'monto_apertura', 'monto_cierre', 'total_ventas',
            'cantidad_pagos', 'observaciones_cierre',
            'fecha_apertura', 'fecha_cierre',
        ]

    def get_cantidad_pagos(self, obj):
        return obj.pagos.filter(estado=Pago.ESTADO_CONFIRMADO).count()


class PagoSerializer(serializers.ModelSerializer):
    pedido_numero   = serializers.CharField(source='pedido.numero',        read_only=True)
    pedido_cliente  = serializers.CharField(source='pedido.cliente_nombre',read_only=True)
    cajero_nombre   = serializers.CharField(source='cajero.nombre_completo',read_only=True)
    medio_display   = serializers.CharField(source='get_medio_pago_display', read_only=True)
    # Si este cobro es el de un cambio, el número de la devolución cuyo
    # crédito lo pagó en parte: sin eso un cobro de "Gs. 0" no se entiende.
    devolucion_aplicada = serializers.SerializerMethodField()
    # Devoluciones hechas SOBRE esta venta.
    devoluciones = serializers.SerializerMethodField()

    class Meta:
        model  = Pago
        fields = [
            'id', 'numero_ticket',
            'pedido_id', 'pedido_numero', 'pedido_cliente',
            'cajero_nombre', 'medio_pago', 'medio_display',
            'monto', 'monto_recibido', 'vuelto',
            'estado', 'referencia_externa', 'fecha',
            'tipo_comprobante', 'cliente_ruc', 'cliente_razon_social',
            'devolucion_aplicada', 'devoluciones',
        ]

    def get_devolucion_aplicada(self, obj):
        dev = getattr(obj, 'devolucion_aplicada', None)
        return dev.numero if dev is not None else None

    def get_devoluciones(self, obj):
        return [d.numero for d in obj.devoluciones.all()]


class DevolucionSerializer(serializers.ModelSerializer):
    motivo_display  = serializers.CharField(source='get_motivo_display', read_only=True)
    medio_reintegro_display = serializers.CharField(
        source='get_medio_reintegro_display', read_only=True)
    venta_ticket    = serializers.CharField(source='pago_original.numero_ticket', read_only=True)
    venta_pedido    = serializers.CharField(source='pago_original.pedido.numero', read_only=True)
    cliente         = serializers.CharField(source='pago_original.pedido.cliente_nombre', read_only=True)
    pedido_cambio_numero = serializers.CharField(
        source='pedido_cambio.numero', read_only=True, default='')
    cobrado_diferencia = serializers.SerializerMethodField()
    usuario_nombre  = serializers.CharField(source='usuario.nombre_completo', read_only=True)

    class Meta:
        model  = Devolucion
        fields = [
            'id', 'numero', 'fecha', 'motivo', 'motivo_display', 'motivo_detalle',
            'venta_ticket', 'venta_pedido', 'cliente', 'usuario_nombre',
            'total_credito', 'pedido_cambio_numero', 'cobrado_diferencia',
            'monto_reintegro', 'medio_reintegro', 'medio_reintegro_display',
        ]

    def get_cobrado_diferencia(self, obj):
        return float(obj.pago_cambio.monto) if obj.pago_cambio_id else 0.0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _sesion_activa(user):
    """Retorna la sesión de caja abierta del usuario, o None."""
    return SesionCaja.objects.filter(
        cajero=user, estado=SesionCaja.ESTADO_ABIERTA
    ).first()


def _emitir_pago_ws(pedido, pago):
    """Notifica via WebSocket que el pedido fue pagado."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer # type: ignore
        from apps.ventas.serializers import NotaPedidoReadSerializer

        layer = get_channel_layer()
        if not layer:
            return

        data = {
            'tipo':   'pedido_pagado',
            'pedido': NotaPedidoReadSerializer(pedido).data,
            'ticket': pago.numero_ticket,
        }
        for room in [f'pedido_{pedido.id}', 'rol_vendedor', 'rol_admin']:
            async_to_sync(layer.group_send)(
                room, {'type': 'pedido_actualizado', 'data': data}
            )
    except Exception:
        pass  # WS no bloquea el flujo de pago


# ─── Views ────────────────────────────────────────────────────────────────────

class SesionActualView(views.APIView):
    """
    GET /caja/sesion-actual/
    Retorna la sesión abierta del cajero, o null si no hay ninguna.
    """
    permission_classes = [EsAdminOCajero]

    def get(self, request):
        sesion = _sesion_activa(request.user)
        if not sesion:
            return Response({'sesion': None, 'tiene_sesion': False})
        return Response({
            'sesion':      SesionCajaSerializer(sesion).data,
            'tiene_sesion': True,
        })


class AbrirCajaView(views.APIView):
    """
    POST /caja/sesiones/
    Body: {"monto_apertura": 500000}
    Abre una nueva sesión de caja.
    """
    permission_classes = [EsAdminOCajero]

    def post(self, request):
        if _sesion_activa(request.user):
            return Response(
                {'error': 'Ya tenés una sesión de caja abierta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        monto = request.data.get('monto_apertura', 0)
        try:
            sesion = SesionCaja.objects.create(
                cajero=request.user,
                monto_apertura=monto,
            )
        except IntegrityError:
            return Response(
                {'error': 'Ya tenés una sesión de caja abierta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(SesionCajaSerializer(sesion).data, status=status.HTTP_201_CREATED)


class CerrarCajaView(views.APIView):
    """
    POST /caja/sesiones/<id>/cerrar/
    Body: {"monto_cierre": 1250000, "observaciones_cierre": "..."}
    Cierra la sesión y retorna el resumen del día.
    """
    permission_classes = [EsAdminOCajero]

    def post(self, request, pk):
        sesion = get_object_or_404(SesionCaja, pk=pk, cajero=request.user)

        if sesion.estado == SesionCaja.ESTADO_CERRADA:
            return Response({'error': 'La sesión ya está cerrada.'}, status=status.HTTP_400_BAD_REQUEST)

        sesion.estado             = SesionCaja.ESTADO_CERRADA
        sesion.monto_cierre       = request.data.get(
            'monto_cierre',
            sesion.total_ventas + sesion.monto_apertura - sesion.total_reintegros())
        sesion.observaciones_cierre = request.data.get('observaciones_cierre', '')
        sesion.fecha_cierre       = timezone.now()
        sesion.save()

        # Resumen para el ticket de cierre
        pagos = sesion.pagos.filter(estado=Pago.ESTADO_CONFIRMADO)
        resumen_medios = {}
        for p in pagos:
            resumen_medios[p.medio_pago] = resumen_medios.get(p.medio_pago, 0) + float(p.monto)

        # Reintegros por devolución: plata que salió de la caja en el turno.
        reintegros_medios = {}
        for d in sesion.devoluciones.filter(monto_reintegro__gt=0):
            reintegros_medios[d.medio_reintegro] = (
                reintegros_medios.get(d.medio_reintegro, 0) + float(d.monto_reintegro))
        total_reintegros = sum(reintegros_medios.values())

        # La diferencia de arqueo compara el efectivo físico contado contra lo
        # que debería haber en el cajón (apertura + ventas en efectivo −
        # reintegros en efectivo). Ventas con tarjeta/transferencia nunca
        # entran al cajón, así que no deben restarse acá o cualquier turno con
        # ventas no-efectivo muestra un faltante ficticio. Por lo mismo, solo
        # el reintegro en efectivo sale del cajón.
        total_efectivo = (resumen_medios.get(Pago.MEDIO_EFECTIVO, 0)
                          - reintegros_medios.get(Pago.MEDIO_EFECTIVO, 0))

        resumen_completo = {
            'resumen_medios': resumen_medios,
            'total_pagos':    pagos.count(),
            'total_ventas':   float(sesion.total_ventas),
            'reintegros_medios': reintegros_medios,
            'total_reintegros':  total_reintegros,
            'total_neto':     float(sesion.total_ventas) - total_reintegros,
            'total_efectivo': total_efectivo,
        }

        # Imprimir ticket de cierre
        resultado_impresion = imprimir_cierre(sesion, resumen_completo)
        if not resultado_impresion['ok']:
            logger.warning(f'No se pudo imprimir el cierre de caja: {resultado_impresion.get("error")}')

        return Response({
            'sesion':           SesionCajaSerializer(sesion).data,
            **resumen_completo,
            'diferencia':       float(sesion.monto_cierre or 0) - float(sesion.monto_apertura or 0) - total_efectivo,
            'impresion_cierre': resultado_impresion,
        })

class RegistrarPagoView(views.APIView):
    """
    POST /caja/pagos/
    Body:
      {
        "pedido_id": 42,
        "medio_pago": "efectivo",
        "monto_recibido": 200000,   // solo para efectivo
        "referencia_externa": ""    // para tarjeta/transferencia
      }

    Flujo atómico (`_registrar`):
      1. Valida que el pedido esté en estado 'listo'
      2. Crea el Pago
      3. Cambia el pedido a 'pagado'
      4. Descuenta el stock de cada ítem
      5. Emite WebSocket
      6. Emite el documento electrónico si corresponde

    Y **fuera** de la transacción (`post`): arma el comprobante y lo imprime.

    Esa separación no es cosmética. `_registrar` toma el pedido con
    `select_for_update()`, así que mientras la transacción esté abierta ese
    pedido queda bloqueado y la conexión ocupada. Imprimir adentro metía una
    llamada a `win32print` —que no tiene timeout— dentro de ese bloqueo: una
    impresora colgada (apagada no, eso devuelve error enseguida; colgada, con
    el spooler sin contestar) mantenía la transacción viva indefinidamente.
    Con varias tablets cobrando a la vez, un cobro trabado podía frenar a los
    demás.

    El papel no es parte de la consistencia de la venta: si la impresión
    falla, el cobro ya ocurrió igual y se reimprime desde "Cobros del turno".
    Por eso puede —y debe— quedar afuera.
    """
    permission_classes = [EsAdminOCajero]

    def post(self, request):
        resultado = self._registrar(request)

        # Validación fallida: `_registrar` ya devolvió la respuesta de error.
        if isinstance(resultado, Response):
            return resultado

        pago = resultado['pago']
        datos_ticket = _datos_ticket(
            resultado['pedido'], pago, resultado['sesion'],
            tipo_comprobante=resultado['tipo_comprobante'],
            cliente_ruc=resultado['cliente_ruc'],
            cliente_razon_social=resultado['cliente_razon_social'],
            cliente_telefono=resultado['cliente_telefono'],
            cliente_direccion=resultado['cliente_direccion'],
            cliente_email=resultado['cliente_email'],
            condicion_venta=resultado['condicion_venta'],
            documento=resultado['documento_electronico'],
        )
        texto_ticket = ticket_a_texto(datos_ticket)

        # ── Imprimir, ya con la transacción cerrada ───────────
        if resultado['tipo_comprobante'] == 'factura':
            resultado_impresion = imprimir_factura(datos_ticket)
        else:
            resultado_impresion = imprimir_ticket(datos_ticket)
        if not resultado_impresion['ok']:
            logger.warning(
                f'Impresión fallida para {resultado["tipo_comprobante"]} '
                f'{pago.numero_ticket}: {resultado_impresion.get("error")}'
            )

        documento_electronico = resultado['documento_electronico']
        return Response({
            'ok':              True,
            'pago':            PagoSerializer(pago).data,
            'tipo_comprobante':resultado['tipo_comprobante'],
            'ticket':          datos_ticket,
            'ticket_texto':    texto_ticket,
            'impresion':       resultado_impresion,
            'errores_stock':   resultado['errores_stock'],
            # null cuando no se emitió DE (ticket, o SIFEN apagado). El
            # frontend lo usa para mostrar el número legal y el estado
            # frente al SIFEN; no debe asumir que siempre viene.
            'documento_electronico': ({
                'cdc':             documento_electronico.cdc,
                'numero':          documento_electronico.numero_completo,
                'estado':          documento_electronico.estado,
                'estado_display':  documento_electronico.get_estado_display(),
            } if documento_electronico is not None else None),
        }, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def _registrar(self, request):
        # ── Validar sesión activa ─────────────────────────────
        sesion = _sesion_activa(request.user)
        if not sesion:
            return Response(
                {'error': 'No hay una sesión de caja abierta. Abrí la caja primero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Validar pedido ────────────────────────────────────
        pedido_id = request.data.get('pedido_id')
        if not pedido_id:
            return Response({'error': 'pedido_id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        pedido = get_object_or_404(
            NotaPedido.objects.select_for_update().prefetch_related('items__variante__stock'),
            pk=pedido_id,
        )

        if pedido.estado != NotaPedido.ESTADO_LISTO:
            return Response(
                {'error': f'El pedido está en estado "{pedido.get_estado_display()}". '
                          f'Solo se pueden cobrar pedidos en estado "Listo para cobrar".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Validar medio de pago ─────────────────────────────
        medio = request.data.get('medio_pago', '')
        medios_validos = [m[0] for m in Pago.MEDIOS]
        if medio not in medios_validos:
            return Response(
                {'error': f'Medio de pago inválido. Opciones: {medios_validos}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        monto_recibido_raw = request.data.get('monto_recibido')
        try:
            monto_recibido = Decimal(str(monto_recibido_raw)) if monto_recibido_raw not in (None, '') else None
        except Exception:
            return Response({'error': 'monto_recibido inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        ref_externa      = request.data.get('referencia_externa', '')

        # Tipo de comprobante: 'ticket' (default) o 'factura'
        tipo_comprobante = request.data.get('tipo_comprobante', 'ticket')
        # Datos fiscales del cliente para la factura
        cliente_ruc          = request.data.get('cliente_ruc', '')
        cliente_razon_social = request.data.get('cliente_razon_social', '')
        cliente_telefono     = request.data.get('cliente_telefono', '')
        cliente_direccion    = request.data.get('cliente_direccion', '')
        condicion_venta      = request.data.get('condicion_venta', 'Contado')
        guardar_cliente      = bool(request.data.get('guardar_cliente', False))

        # El correo viaja al SIFEN en el campo D216 y es por donde el
        # comprobante le llega al cliente. Se valida acá, con el cliente
        # todavía en el mostrador: uno mal escrito descubierto por el worker
        # al otro día es un documento rechazado y nadie a quien preguntarle.
        # `validar_email_receptor` también recorta en la primera coma, porque
        # el SIFEN no las acepta en ese campo.
        try:
            cliente_email = codigos.validar_email_receptor(
                request.data.get('cliente_email', ''))
        except ValueError as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        # La factura es un documento fiscal: RUC y razón social son
        # obligatorios acá, no solo en el frontend (que puede saltearse con
        # una llamada directa a la API).
        if tipo_comprobante == 'factura' and not ((cliente_ruc or '').strip() and (cliente_razon_social or '').strip()):
            return Response(
                {'error': 'Para emitir factura debés cargar RUC y razón social del cliente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Si es factura y el cliente tiene RUC + razón social, guardarlo o
        # actualizarlo en el padrón para que en la próxima compra se autocomplete.
        if tipo_comprobante == 'factura' and guardar_cliente and cliente_ruc and cliente_razon_social:
            try:
                from apps.ventas.models import Cliente
                cliente_obj, creado = Cliente.objects.get_or_create(
                    ruc=cliente_ruc,
                    defaults={
                        'razon_social': cliente_razon_social,
                        'telefono': cliente_telefono,
                        'email': cliente_email,
                        'direccion': cliente_direccion,
                        'condicion_venta': 'credito' if condicion_venta.lower().startswith('cr') else 'contado',
                    },
                )
                if not creado:
                    # Completar datos que estuvieran vacíos, sin pisar lo existente
                    cambios = False
                    if cliente_razon_social and not cliente_obj.razon_social:
                        cliente_obj.razon_social = cliente_razon_social; cambios = True
                    if cliente_telefono and not cliente_obj.telefono:
                        cliente_obj.telefono = cliente_telefono; cambios = True
                    if cliente_email and not cliente_obj.email:
                        cliente_obj.email = cliente_email; cambios = True
                    if cliente_direccion and not cliente_obj.direccion:
                        cliente_obj.direccion = cliente_direccion; cambios = True
                    if cambios:
                        cliente_obj.save()
            except Exception:
                # Guardar el cliente es un extra; si falla, el cobro continúa igual.
                pass

        # ── Descuento porcentual aplicado en caja ─────────────
        # (Decimal ya está importado a nivel de módulo — importarlo también acá
        # rompería con UnboundLocalError el uso más arriba, en monto_recibido.)
        from decimal import ROUND_HALF_UP
        try:
            desc_pct = Decimal(str(request.data.get('descuento_porcentaje', 0) or 0))
        except Exception:
            desc_pct = Decimal('0')
        if desc_pct < 0 or desc_pct > DESCUENTO_CAJA_MAXIMO:
            return Response(
                {'error': f'El descuento debe estar entre 0 y {DESCUENTO_CAJA_MAXIMO} por ciento.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        monto_base  = pedido.monto_a_cobrar                       # monto antes del descuento de caja
        monto_final = (monto_base * (Decimal('100') - desc_pct) / Decimal('100')).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP)                  # guaraníes sin decimales

        # ── Validar que el efectivo alcance ────────────────────
        if medio == Pago.MEDIO_EFECTIVO:
            if monto_recibido is None:
                return Response(
                    {'error': 'Para pagos en efectivo debés indicar el monto recibido.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if monto_recibido < monto_final:
                return Response(
                    {'error': f'El monto recibido (Gs. {monto_recibido:,.0f}) es menor al total '
                              f'a cobrar (Gs. {monto_final:,.0f}).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ── Tarjeta: pasar por la terminal POS ────────────────
        # Solo si es factura Y el SIFEN está prendido. Con ticket o con el
        # SIFEN apagado el cobro con tarjeta sigue funcionando exactamente
        # como siempre — no se le agrega un requisito a la cajera por una
        # obligación fiscal que todavía no rige.
        #
        # Se hace ANTES de crear el pago a propósito: si faltan los datos que
        # el SIFEN exige, es mejor frenar acá, con el cliente todavía en el
        # mostrador, que emitir la factura y descubrirlo cuando el documento
        # vuelva rechazado al otro día.
        resultado_pos = None
        if (tipo_comprobante == 'factura'
                and fe_emisor.sifen_activo()
                and pos_mod.requiere_datos_de_tarjeta(medio)):
            terminal = pos_mod.obtener_terminal()
            try:
                resultado_pos = terminal.cobrar(
                    monto_final, medio=medio,
                    datos=request.data.get('datos_tarjeta') or {})
            except pos_mod.ErrorPOS as e:
                return Response({'error': str(e)},
                                status=status.HTTP_400_BAD_REQUEST)
            if not resultado_pos.aprobado:
                return Response(
                    {'error': f'La terminal rechazó el cobro: '
                              f'{resultado_pos.mensaje or "sin detalle"}'},
                    status=status.HTTP_400_BAD_REQUEST)

        # ── Cheque: banco y número, siempre ───────────────────
        # A diferencia de la tarjeta, acá no se espera a que el SIFEN esté
        # prendido: un cheque sin banco ni número es un papel que el local
        # después no puede cruzar contra nada. La razón completa está en
        # apps/caja/cheque.py.
        datos_cheque = None
        if cheque_mod.requiere_datos_de_cheque(medio):
            try:
                datos_cheque = cheque_mod.validar(
                    request.data.get('datos_cheque') or {})
            except cheque_mod.ErrorCheque as e:
                return Response({'error': str(e)},
                                status=status.HTTP_400_BAD_REQUEST)

        # ── Crear pago ────────────────────────────────────────
        pago = Pago(
            pedido           = pedido,
            sesion_caja      = sesion,
            cajero           = request.user,
            medio_pago       = medio,
            monto            = monto_final,
            descuento_porcentaje = desc_pct,
            monto_sin_descuento  = monto_base,
            monto_recibido   = monto_recibido,
            referencia_externa = ref_externa,
            estado           = Pago.ESTADO_CONFIRMADO,
            # Sin esto, reimprimir un pago viejo (o buscarlo por RUC) no
            # tenía de dónde sacar los datos de la factura — ver el
            # comentario en el modelo.
            tipo_comprobante     = tipo_comprobante,
            cliente_ruc          = cliente_ruc if tipo_comprobante == 'factura' else '',
            cliente_razon_social = cliente_razon_social if tipo_comprobante == 'factura' else '',
            cliente_telefono     = cliente_telefono if tipo_comprobante == 'factura' else '',
            cliente_direccion    = cliente_direccion if tipo_comprobante == 'factura' else '',
            cliente_email        = cliente_email if tipo_comprobante == 'factura' else '',
            condicion_venta      = condicion_venta if tipo_comprobante == 'factura' else 'Contado',
        )
        pago.save()

        if resultado_pos is not None:
            DatosTarjeta.objects.create(
                pago=pago,
                denominacion=resultado_pos.denominacion,
                denominacion_descripcion=resultado_pos.denominacion_descripcion,
                forma_procesamiento=resultado_pos.forma_procesamiento,
                codigo_autorizacion=resultado_pos.codigo_autorizacion,
                titular=resultado_pos.titular,
                ultimos_digitos=resultado_pos.ultimos_digitos,
                procesadora_ruc=resultado_pos.procesadora_ruc,
                procesadora_razon_social=resultado_pos.procesadora_razon_social,
                numero_boleta=resultado_pos.numero_boleta,
                origen=pos_mod.obtener_terminal().nombre,
            )

        if datos_cheque is not None:
            DatosCheque.objects.create(
                pago=pago,
                numero=datos_cheque.numero,
                banco=datos_cheque.banco,
                titular=datos_cheque.titular,
                fecha_cobro=datos_cheque.fecha_cobro,
            )

        # ── Cambiar estado del pedido ─────────────────────────
        pedido.estado = NotaPedido.ESTADO_PAGADO
        pedido.save(update_fields=['estado', 'fecha_actualizacion'])

        # ── Descontar stock (libera reserva + descuenta cantidad) ─
        errores_stock = pedido.descontar_stock(
            usuario=request.user,
            numero_ticket=pago.numero_ticket,
        )

        # ── Notificar via WebSocket ───────────────────────────
        _emitir_pago_ws(pedido, pago)

        # ── Documento electrónico (SIFEN) ─────────────────────
        # Solo para facturas: un ticket interno no es un comprobante fiscal.
        #
        # emitir_para_pago() no lanza nunca y devuelve None si el SIFEN está
        # apagado (que es el estado actual, SIFEN_HABILITADO=False) o si algo
        # falla. Es deliberado: acá la venta ya ocurrió, el stock ya se
        # descontó y el cliente está esperando el comprobante — un problema
        # de facturación electrónica no puede tumbar un cobro consumado.
        #
        # crear_documento() tiene su propio transaction.atomic, así que
        # dentro de esta vista (que también es atómica) funciona como
        # savepoint: si el DE falla se revierte solo, incluido el número de
        # comprobante, y el cobro sigue su curso sin dejar un salto en el
        # correlativo.
        documento_electronico = None
        if tipo_comprobante == 'factura':
            documento_electronico = fe_emisor.emitir_para_pago(
                pago,
                receptor={
                    'ruc':          cliente_ruc,
                    'razon_social': cliente_razon_social,
                    'telefono':     cliente_telefono,
                    'direccion':    cliente_direccion,
                    # Campo D216 del DE: por acá el SIFEN le manda el
                    # comprobante al cliente.
                    'email':        cliente_email,
                },
                condicion_venta=condicion_venta,
            )

        # Todo lo que `post` necesita para armar el comprobante e imprimirlo,
        # ya fuera de la transacción. No se devuelve una Response acá a
        # propósito: mientras esta función no termine, el pedido sigue
        # bloqueado por el `select_for_update()` de más arriba.
        return {
            'pedido':               pedido,
            'pago':                 pago,
            'sesion':               sesion,
            'tipo_comprobante':     tipo_comprobante,
            'cliente_ruc':          cliente_ruc,
            'cliente_razon_social': cliente_razon_social,
            'cliente_telefono':     cliente_telefono,
            'cliente_direccion':    cliente_direccion,
            'cliente_email':        cliente_email,
            'condicion_venta':      condicion_venta,
            'errores_stock':        errores_stock,
            'documento_electronico': documento_electronico,
        }


# Tope de resultados cuando se busca fuera del turno abierto. Sin esto una
# búsqueda histórica sin criterio arrastraría la tabla de pagos entera; con
# esto la respuesta avisa que quedó recortada ("truncado") y la UI puede
# pedir que afinen la búsqueda.
LIMITE_HISTORICO = 50


class ListaPagosView(views.APIView):
    """
    GET /caja/pagos/lista/?sesion=<id>&q=<texto>&ruc=<texto>&historico=1

    Por defecto lista los pagos de la sesión activa (o de una sesión puntual
    con `sesion`): es el "Cobros del turno" de la pantalla de caja.

    `q` busca por nombre del cliente, RUC/CI o número de comprobante. El
    nombre se busca en DOS campos a propósito: `cliente_razon_social` solo se
    completa al cobrar como factura, mientras que `pedido.cliente_nombre`
    está en todos los cobros — mirar uno solo dejaría la mitad afuera. Es lo
    que piden los usuarios finales: buscan por nombre, no por RUC.

    `ruc` sigue existiendo como filtro propio por compatibilidad con quien ya
    lo usa; equivale a `q` restringido al RUC.

    `historico=1` deja de recortar al turno. Sirve para cargar al portal de
    e-Kuatia'i facturas cobradas en turnos ya cerrados, que de otro modo son
    inalcanzables: la pantalla de caja ni se abre sin sesión, así que un
    cobro de ayer no tenía forma de volver a mirarse. Los resultados se
    acotan a LIMITE_HISTORICO por fecha descendente.

    En los tres casos rige la misma regla de visibilidad que ya valía para
    una sesión explícita: quien no es admin solo ve cobros de sus propias
    sesiones.
    """
    permission_classes = [EsAdminOCajero]

    def get(self, request):
        historico = request.query_params.get('historico') in ('1', 'true', 'True')

        if historico:
            qs = Pago.objects.all()
        else:
            sesion_id = request.query_params.get('sesion')
            if sesion_id:
                qs = Pago.objects.filter(sesion_caja_id=sesion_id)
            else:
                sesion = _sesion_activa(request.user)
                qs = Pago.objects.filter(sesion_caja=sesion) if sesion else Pago.objects.none()

        # Para la sesión activa es redundante (esa sesión ya es suya), pero
        # aplicarlo siempre evita que el alcance histórico se vuelva un
        # agujero por el que un cajero vea los cobros de otro.
        if request.user.rol != 'admin':
            qs = qs.filter(sesion_caja__cajero=request.user)

        ruc = (request.query_params.get('ruc') or '').strip()
        if ruc:
            qs = qs.filter(cliente_ruc__icontains=ruc)

        texto = (request.query_params.get('q') or '').strip()
        if texto:
            qs = qs.filter(
                Q(cliente_razon_social__icontains=texto) |
                Q(pedido__cliente_nombre__icontains=texto) |
                Q(cliente_ruc__icontains=texto) |
                Q(numero_ticket__icontains=texto)
            )

        qs = (qs.select_related('pedido', 'cajero', 'devolucion_aplicada')
                .prefetch_related('devoluciones')
                .order_by('-fecha'))

        # count() antes de recortar: el frontend necesita saber cuántos hay
        # en total para avisar que la lista quedó cortada.
        total = qs.count()
        if historico:
            qs = qs[:LIMITE_HISTORICO]

        return Response({
            'results':  PagoSerializer(qs, many=True).data,
            'count':    total,
            'alcance':  'historico' if historico else 'turno',
            'truncado': bool(historico and total > LIMITE_HISTORICO),
        })


class ReimprimirTicketView(views.APIView):
    """
    POST /caja/pagos/<id>/reimprimir/
    Reimprime el comprobante de un pago ya procesado y manda el papel a la
    impresora. Útil cuando el papel se atasca o el cliente pide otra copia.

    Qué se reimprime (factura con su CDC y timbrado originales, factura sin
    documento electrónico, o ticket) lo decide _reconstruir_comprobante().

    Para solo VER los datos sin imprimir —el caso de cargar la factura en el
    portal del DNIT más tarde— está ComprobanteView, que no toca la
    impresora.
    """
    permission_classes = [EsAdminOCajero]

    def post(self, request, pk):
        pago = _pago_para_comprobante(pk)
        tipo_comprobante, datos_ticket = _reconstruir_comprobante(pago)

        if tipo_comprobante == 'factura':
            resultado = imprimir_factura(datos_ticket)
        else:
            resultado = imprimir_ticket(datos_ticket)

        return Response({
            'ok':           resultado['ok'],
            'impresion':    resultado,
            'ticket_texto': ticket_a_texto(datos_ticket),
            'ticket':       datos_ticket,
            # Qué se imprimió realmente. Sin esto el frontend no puede saber
            # si salió un ticket o una factura, y avisaría cualquier cosa.
            'tipo_comprobante': tipo_comprobante,
        })


class ComprobanteView(views.APIView):
    """
    GET /caja/pagos/<id>/comprobante/
    Devuelve el comprobante reconstruido de un pago ya cobrado, SIN imprimir
    nada. Misma forma de respuesta que reimprimir y que el cobro, para que el
    frontend pueda renderizarlo con el mismo componente.

    Existe por el flujo de e-Kuatia'i: bajo Solución Gratuita la factura
    legal se carga a mano en el portal del DNIT, con el cuadro "Datos para
    cargar en e-Kuatia'i" que el frontend arma desde esta misma respuesta.
    Ese cuadro solo aparecía en el instante del cobro, y la única forma de
    volver a abrirlo era reimprimir: un papel gastado por cada factura a
    cargar.

    Es GET y no un POST con bandera a propósito: sobre un GET, un reintento
    de red o un refetch del frontend no puede escupir papel por accidente.
    """
    permission_classes = [EsAdminOCajero]

    def get(self, request, pk):
        pago = _pago_para_comprobante(pk)
        tipo_comprobante, datos_ticket = _reconstruir_comprobante(pago)

        return Response({
            'ok':               True,
            'ticket':           datos_ticket,
            'ticket_texto':     ticket_a_texto(datos_ticket),
            'tipo_comprobante': tipo_comprobante,
        })


class EstadoImpresora(views.APIView):
    """
    GET /caja/impresora/estado/
    Verifica si la impresora térmica está disponible.
    Útil para mostrar un indicador en la UI de caja.
    """
    permission_classes = [EsAdminOCajero]

    def get(self, request):
        cfg = settings.IMPRESORA_TERMICA

        resultado = {
            'configurada':   bool(cfg.get('nombre_windows') or cfg.get('puerto_directo')),
            'nombre':        cfg.get('nombre_windows', ''),
            'puerto':        cfg.get('puerto_directo', ''),
            'auto_imprimir': cfg.get('auto_imprimir', True),
            'disponible':    False,
            'error':         None,
        }

        if not resultado['configurada']:
            resultado['error'] = 'No hay impresora configurada en el .env'
            return Response(resultado)

        # Intentar detectar la impresora en Windows
        try:
            import win32print
            impresoras = [p[2] for p in win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )]
            nombre = cfg.get('nombre_windows', '')
            resultado['disponible'] = nombre in impresoras
            resultado['impresoras_disponibles'] = impresoras
            if not resultado['disponible']:
                resultado['error'] = (
                    f'Impresora "{nombre}" no encontrada. '
                    f'Disponibles: {", ".join(impresoras)}'
                )
            else:
                # Que Windows la liste no significa que vaya a imprimir: si
                # está en "Usar impresora sin conexión", win32print igual
                # acepta el trabajo sin error — se apila en la cola y nunca
                # sale nada físicamente. Chequear el bit de atributo, no solo
                # la presencia en EnumPrinters.
                PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x400
                hprinter = win32print.OpenPrinter(nombre)
                try:
                    info = win32print.GetPrinter(hprinter, 2)
                finally:
                    win32print.ClosePrinter(hprinter)
                if info['Attributes'] & PRINTER_ATTRIBUTE_WORK_OFFLINE:
                    resultado['disponible'] = False
                    resultado['error'] = (
                        f'Impresora "{nombre}" está en modo "sin conexión" en Windows — '
                        f'los tickets se acumulan en la cola pero no salen. '
                        f'Clic derecho sobre la impresora → destildar "Usar impresora sin conexión".'
                    )
        except ImportError:
            resultado['disponible'] = True   # En desarrollo no hay win32print
            resultado['error'] = 'win32print no disponible (entorno no-Windows)'
        except Exception as e:
            resultado['error'] = str(e)

        return Response(resultado)


# ─── Devoluciones y cambios ───────────────────────────────────────────────────

class DevolucionResumenView(views.APIView):
    """
    GET /caja/pagos/<id>/devolucion/

    Qué se puede devolver de esa venta: cada ítem con lo vendido, lo que ya
    volvió en devoluciones anteriores y lo que vale a precio cobrado. Si la
    venta no se puede devolver por acá (factura electrónica viva), `bloqueo`
    trae el motivo y la pantalla no deja seguir.
    """
    permission_classes = [EsAdminOCajero]

    def get(self, request, pk):
        pago = get_object_or_404(
            Pago.objects.select_related('pedido').prefetch_related('documentos_electronicos'),
            pk=pk, estado=Pago.ESTADO_CONFIRMADO)
        return Response(devoluciones_mod.resumen(pago))


class DevolucionesView(views.APIView):
    """
    GET  /caja/devoluciones/?sesion=<id>   — las del turno (default: el abierto)
    POST /caja/devoluciones/               — registrar una

    Body del POST:
      {
        "pago_id": 42,                          // la venta original
        "motivo": "cambio" | "estado_inadecuado" | "otro",
        "motivo_detalle": "...",                // obligatorio con "otro"
        "items": [{"item_id": 7, "cantidad": 2.52, "reingresa_stock": true}],
        "pedido_cambio_id": 51,                 // opcional: lo que se lleva
        "medio_pago": "efectivo",               // de la diferencia, si la hay
        "monto_recibido": 100000,               // si se cobra en efectivo
        "referencia_externa": "",
        "observaciones": ""
      }

    Igual que el cobro, la transacción y el papel van separados: se imprime
    con la transacción ya cerrada, porque una impresora colgada no puede
    dejar bloqueados el pago original y el pedido de cambio.
    """
    permission_classes = [EsAdminOCajero]

    def get(self, request):
        sesion_id = request.query_params.get('sesion')
        if sesion_id:
            qs = Devolucion.objects.filter(sesion_caja_id=sesion_id)
        else:
            sesion = _sesion_activa(request.user)
            qs = Devolucion.objects.filter(sesion_caja=sesion) if sesion else Devolucion.objects.none()
        if request.user.rol != 'admin':
            qs = qs.filter(sesion_caja__cajero=request.user)
        qs = qs.select_related('pago_original__pedido', 'pedido_cambio',
                               'pago_cambio', 'usuario')
        return Response({'results': DevolucionSerializer(qs, many=True).data})

    def post(self, request):
        resultado = self._registrar(request)
        if isinstance(resultado, Response):
            return resultado

        devolucion = resultado.devolucion
        datos = devoluciones_mod.datos_comprobante(devolucion)
        impresion = imprimir_devolucion(datos)
        if not impresion['ok']:
            logger.warning(f'No se pudo imprimir la devolución {devolucion.numero}: '
                           f'{impresion.get("error")}')

        if devolucion.pago_cambio_id:
            _emitir_pago_ws(devolucion.pedido_cambio, devolucion.pago_cambio)

        return Response({
            'ok':            True,
            'devolucion':    DevolucionSerializer(devolucion).data,
            'comprobante':   datos,
            'texto':         ticket_devolucion_a_texto(datos),
            'impresion':     impresion,
            'errores_stock': resultado.errores_stock,
        }, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def _registrar(self, request):
        sesion = _sesion_activa(request.user)
        if not sesion:
            return Response(
                {'error': 'No hay una sesión de caja abierta. Abrí la caja primero.'},
                status=status.HTTP_400_BAD_REQUEST)

        pago = get_object_or_404(Pago, pk=request.data.get('pago_id') or 0)

        pedido_cambio = None
        pedido_cambio_id = request.data.get('pedido_cambio_id')
        if pedido_cambio_id:
            pedido_cambio = get_object_or_404(NotaPedido, pk=pedido_cambio_id)

        items = request.data.get('items') or []
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            return Response({'error': 'items tiene que ser una lista de productos.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            return devoluciones_mod.registrar(
                pago_original=pago,
                sesion=sesion,
                usuario=request.user,
                motivo=request.data.get('motivo', ''),
                motivo_detalle=request.data.get('motivo_detalle', ''),
                observaciones=request.data.get('observaciones', ''),
                items=items,
                pedido_cambio=pedido_cambio,
                medio_pago=request.data.get('medio_pago', ''),
                monto_recibido=request.data.get('monto_recibido'),
                referencia_externa=request.data.get('referencia_externa', ''),
            )
        except devoluciones_mod.DevolucionInvalida as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReimprimirDevolucionView(views.APIView):
    """POST /caja/devoluciones/<id>/reimprimir/"""
    permission_classes = [EsAdminOCajero]

    def post(self, request, pk):
        qs = Devolucion.objects.all()
        if request.user.rol != 'admin':
            qs = qs.filter(sesion_caja__cajero=request.user)
        devolucion = get_object_or_404(qs, pk=pk)
        datos = devoluciones_mod.datos_comprobante(devolucion)
        impresion = imprimir_devolucion(datos)
        return Response({
            'ok':          impresion['ok'],
            'comprobante': datos,
            'texto':       ticket_devolucion_a_texto(datos),
            'impresion':   impresion,
        })


# ─── Helper de ticket ─────────────────────────────────────────────────────────

def _pago_para_comprobante(pk):
    """
    Trae un pago con todo lo que necesita _reconstruir_comprobante en una
    sola consulta.

    Los documentos electrónicos van por prefetch y no por select_related:
    desde que un cobro puede tener factura y nota de crédito, la relación
    es de varios (ver DocumentoElectronico.pago).
    """
    return get_object_or_404(
        Pago.objects.select_related('pedido', 'cajero', 'sesion_caja')
                    .prefetch_related('documentos_electronicos',
                                      'pedido__items__variante__producto'),
        pk=pk
    )


def _reconstruir_comprobante(pago):
    """
    Reconstruye el comprobante de un pago ya cobrado.
    Devuelve (tipo_comprobante, datos_ticket).

    La precedencia es la parte delicada, y vive solo acá:

    1. Con DocumentoElectronico, el receptor y todo lo fiscal salen de ÉL.
       El DE guarda el snapshot del timbrado vigente al emitir, así que
       reconstruir desde settings sacaría el timbrado de hoy en vez del que
       correspondía a esa venta.
    2. Cobrado como factura pero sin DE (Solución Gratuita / e-Kuatia'i, el
       caso de hoy): los datos del cliente salen de lo que quedó guardado en
       el propio Pago al cobrar.
    3. Cualquier otro caso es un ticket.

    El orden importa: reimprimir un ticket en lugar de la factura le daría al
    cliente un papel sin valor fiscal.
    """
    documento = getattr(pago, 'documento_electronico', None)
    if documento is not None:
        return 'factura', _datos_ticket(
            pago.pedido, pago, pago.sesion_caja,
            tipo_comprobante='factura',
            cliente_ruc=documento.receptor_ruc,
            cliente_razon_social=documento.receptor_razon_social,
            cliente_telefono=documento.receptor_telefono,
            cliente_direccion=documento.receptor_direccion,
            cliente_email=documento.receptor_email,
            documento=documento,
        )

    if pago.tipo_comprobante == Pago.COMPROBANTE_FACTURA:
        return 'factura', _datos_ticket(
            pago.pedido, pago, pago.sesion_caja,
            tipo_comprobante='factura',
            cliente_ruc=pago.cliente_ruc,
            cliente_razon_social=pago.cliente_razon_social,
            cliente_telefono=pago.cliente_telefono,
            cliente_direccion=pago.cliente_direccion,
            cliente_email=pago.cliente_email,
            condicion_venta=pago.condicion_venta or 'Contado',
        )

    return 'ticket', _datos_ticket(pago.pedido, pago, pago.sesion_caja)


def _detalle_medio_pago(pago):
    """
    Línea extra bajo "Medio de pago", cuando el papel la necesita.

    Hoy solo el cheque: el ticket es el único registro que le queda al local
    de qué papel entró en la caja, y "Cheque" a secas no alcanza para
    cruzarlo después contra el extracto del banco.
    """
    datos = getattr(pago, 'datos_cheque', None)
    if datos is not None:
        return datos.descripcion_corta
    return ''


def _datos_ticket(pedido, pago, sesion, tipo_comprobante='ticket',
                  cliente_ruc='', cliente_razon_social='', cliente_telefono='',
                  cliente_direccion='', cliente_email='',
                  condicion_venta='Contado', documento=None):
    """
    Estructura los datos necesarios para imprimir el ticket o la factura.

    `documento` es el DocumentoElectronico si se emitió uno. Cuando existe,
    los datos fiscales salen de ÉL y no de settings: el DE guarda el snapshot
    del timbrado vigente al emitir, así que una reimpresión vieja sale con el
    timbrado que tenía entonces y no con el de hoy.
    """
    from django.conf import settings as dj_settings

    items = []
    for item in pedido.items.all():
        items.append({
            'descripcion':   item.variante.producto.nombre,
            'detalle':       str(item.variante),
            # SKU de la variante: es el mismo "Código Interno del Producto"
            # con el que se cargó el catálogo en e-Kuatia'i (ver manage.py
            # exportar_catalogo_ekuatiai), así que sirve para pegarlo tal
            # cual en el buscador de ítems del portal en vez de escribir la
            # descripción a mano.
            'codigo':        item.variante.sku,
            'cantidad':      float(item.cantidad),
            'precio_unit':   float(item.precio_unitario),
            'subtotal':      float(item.subtotal),
            'tasa_iva':      getattr(item.variante.producto, 'tasa_iva', 10),
        })

    total = float(pago.monto)   # monto efectivamente cobrado (ya con descuento de caja)

    # Si hubo precio negociado en el pedido, o descuento porcentual en caja, registrarlo
    hubo_ajuste = pedido.total_ajustado is not None and float(pedido.total_ajustado) != float(pedido.total)
    desc_pct_caja = float(getattr(pago, 'descuento_porcentaje', 0) or 0)

    # Nombre del cliente para el comprobante: prioriza el ingresado en la
    # factura (razón social), luego el del pedido, y por último el genérico.
    nombre_cliente = (cliente_razon_social or pedido.cliente_nombre or 'Consumidor Final')

    # Dirección/teléfono/email de contacto del negocio (no los fiscales: ver
    # CONTACTO_COMERCIAL en settings). En la factura, direccion/telefono se
    # pisan más abajo con los datos de la DNIT — el email no tiene
    # equivalente fiscal y queda igual en los dos tipos de comprobante.
    contacto = getattr(dj_settings, 'CONTACTO_COMERCIAL', {})

    datos = {
        'numero_ticket':   pago.numero_ticket,
        # localtime: el campo se guarda en UTC (USE_TZ=True) y el ticket
        # salía con la hora corrida cuatro horas.
        'fecha':           timezone.localtime(pago.fecha).strftime('%d/%m/%Y %H:%M'),
        'cajero':          pago.cajero.nombre_completo,
        'pedido_numero':   pedido.numero,
        'cliente':         nombre_cliente,
        'items':           items,
        'subtotal':        float(pedido.subtotal),
        'descuento':       float(pedido.descuento),
        'total':           total,
        'monto_ajustado':  hubo_ajuste,
        'total_original':  float(pedido.total),
        'descuento_caja_pct': desc_pct_caja,
        'monto_sin_descuento_caja': float(getattr(pago, 'monto_sin_descuento', 0) or total),
        'medio_pago':      pago.get_medio_pago_display(),
        'detalle_pago':    _detalle_medio_pago(pago),
        'monto_recibido':  float(pago.monto_recibido) if pago.monto_recibido else None,
        'vuelto':          float(pago.vuelto),
        'negocio':         'Oga Porã',
        'direccion':       contacto.get('direccion', ''),
        'telefono':        contacto.get('telefono', ''),
        'email':           contacto.get('email', ''),
        'pie':             'Gracias por su compra',
    }

    # Cobro de un cambio: el pedido vale más de lo que se cobró porque la
    # mercadería devuelta se tomó a cuenta. Sin esta línea el ticket muestra
    # ítems que suman más que el total y no se entiende por qué.
    aplicada = getattr(pago, 'devolucion_aplicada', None)
    if aplicada is not None:
        datos['credito_devolucion'] = float(aplicada.credito_aplicado)
        datos['devolucion_numero']  = aplicada.numero

    # Datos extra solo para factura
    if tipo_comprobante == 'factura':
        fiscal = getattr(dj_settings, 'DATOS_FISCALES', {})

        # Desglose real de IVA por tasa (10% / 5% / exento), ítem por ítem
        # — la misma cuenta que usa apps/facturacion/emisor.py para el DE.
        # No depende de que el SIFEN esté prendido: es aritmética pura sobre
        # el pedido, y es la que necesita el ayudante de carga para que la
        # cajera no transcriba "10% para todo" cuando hay ítems al 5% o
        # exentos.
        totales_iva = fe_emisor.calcular_totales_iva(pedido, total)

        datos.update({
            'factura_numero':  pago.numero_ticket,
            'ruc_negocio':     fiscal.get('ruc', ''),
            'direccion':       fiscal.get('direccion', ''),
            'telefono':        fiscal.get('telefono', ''),
            # OJO: 'timbrado' NO sale de fiscal.get() acá a propósito. Ese
            # timbrado es el que la DNIT habilitó para los documentos que
            # emite el PORTAL (Solución Gratuita / e-Kuatia'i), no este
            # papel. Imprimirlo sin que exista un DocumentoElectronico real
            # detrás sería un papel que se hace pasar por la factura legal
            # sin serlo. Por eso solo se completa más abajo, desde el
            # snapshot del DE, cuando ese DE existe de verdad.
            'cliente_ruc':     cliente_ruc or 'Sin especificar',
            'cliente_razon_social': nombre_cliente,
            'cliente_telefono': cliente_telefono or '',
            'cliente_direccion': cliente_direccion or '',
            'cliente_email': cliente_email or '',
            'condicion_venta': condicion_venta,
            'iva_10':          float(totales_iva['iva_10']),
            'iva_5':           float(totales_iva['iva_5']),
            'exento':          float(totales_iva['total_exento']),
            'base_gravada_10': float(totales_iva['total_gravado_10']),
            'base_gravada_5':  float(totales_iva['total_gravado_5']),
        })

        # Con documento electrónico, todo lo fiscal se pisa con el snapshot
        # del DE. Dos motivos: el número pasa a ser el correlativo legal
        # (EEE-PPP-NNNNNNN) en vez del ticket interno, y el timbrado es el
        # que estaba vigente al emitir, no el que haya en settings hoy.
        if documento is not None:
            from apps.facturacion import cdc as cdc_mod
            datos.update({
                'factura_numero':  documento.numero_completo,
                'ruc_negocio':     documento.emisor_ruc,
                'direccion':       documento.emisor_direccion,
                'telefono':        documento.emisor_telefono,
                'timbrado':        documento.emisor_timbrado,
                'timbrado_vto':    documento.emisor_timbrado_vto,
                'cdc':             documento.cdc,
                'cdc_legible':     cdc_mod.formatear_legible(documento.cdc),
                'url_consulta_qr': documento.url_consulta_qr,
                # El snapshot del DE pisa el desglose recién calculado: es
                # el mismo cálculo (calcular_totales_iva), pero el que
                # efectivamente quedó registrado al emitir.
                'iva_10':          float(documento.iva_10),
                'iva_5':           float(documento.iva_5),
                'exento':          float(documento.total_exento),
                'base_gravada_10': float(documento.total_gravado_10),
                'base_gravada_5':  float(documento.total_gravado_5),
            })

    return datos


# ════════════════════════════════════════════════════════
# REPORTES (PDF / Excel) — solo admin
# ════════════════════════════════════════════════════════
from datetime import datetime, date
from . import reportes as rep


def _parse_rango(request):
    """Lee ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD; default: mes actual."""
    hoy = date.today()
    desde_str = request.query_params.get('desde')
    hasta_str = request.query_params.get('hasta')
    try:
        desde = datetime.strptime(desde_str, '%Y-%m-%d').date() if desde_str else hoy.replace(day=1)
    except ValueError:
        desde = hoy.replace(day=1)
    try:
        hasta = datetime.strptime(hasta_str, '%Y-%m-%d').date() if hasta_str else hoy
    except ValueError:
        hasta = hoy
    return desde, hasta


def _formato(request):
    f = request.query_params.get('formato', 'pdf').lower()
    return 'xlsx' if f in ('xlsx', 'excel', 'csv') else 'pdf'


def _tamanio(request):
    """Tamaño de hoja para el PDF: 'a4' (default) u 'oficio'. Sin efecto en xlsx."""
    t = request.query_params.get('tamano', request.query_params.get('tamanio', 'a4')).lower()
    return 'oficio' if t in ('oficio', 'legal', 'ofic') else 'a4'


class ReporteStockView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request):
        reporte = rep.reporte_stock()
        return rep.responder_reporte(reporte, _formato(request), 'reporte_stock', tamanio=_tamanio(request))


class ReporteVentasView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request):
        desde, hasta = _parse_rango(request)
        reporte = rep.reporte_ventas(desde, hasta)
        return rep.responder_reporte(reporte, _formato(request), 'balance_ventas', tamanio=_tamanio(request))


class ReporteCajaView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request):
        desde, hasta = _parse_rango(request)
        reporte = rep.reporte_caja(desde, hasta)
        return rep.responder_reporte(reporte, _formato(request), 'extracto_caja', tamanio=_tamanio(request))


class ReporteProductosView(views.APIView):
    """
    Qué se vendió, producto por producto.

    ?detalle=1 devuelve una fila por venta con su fecha; sin el parámetro,
    el acumulado por variante del período. Son el mismo dato mirado de dos
    maneras, así que van en un solo endpoint y no en dos.
    """
    permission_classes = [EsAdmin]

    def get(self, request):
        desde, hasta = _parse_rango(request)
        detalle = request.query_params.get('detalle', '') in ('1', 'true', 'True', 'si')
        reporte = rep.reporte_productos(desde, hasta, detalle=detalle)
        nombre = 'productos_detalle' if detalle else 'productos_vendidos'
        return rep.responder_reporte(reporte, _formato(request), nombre,
                                     tamanio=_tamanio(request))


class ReporteArqueoView(views.APIView):
    """
    Arqueo de un día concreto (?dia=YYYY-MM-DD, por defecto hoy).

    Va por día y no por rango como los demás: un arqueo compara el efectivo
    contado contra el esperado en un momento dado. Sumar una semana daría un
    número que no se puede contar contra nada.
    """
    permission_classes = [EsAdmin]

    def get(self, request):
        dia_str = request.query_params.get('dia') or request.query_params.get('hasta')
        try:
            dia = datetime.strptime(dia_str, '%Y-%m-%d').date() if dia_str else date.today()
        except ValueError:
            dia = date.today()
        reporte = rep.reporte_arqueo(dia)
        return rep.responder_reporte(reporte, _formato(request),
                                     f'arqueo_caja_{dia.strftime("%Y%m%d")}',
                                     tamanio=_tamanio(request))