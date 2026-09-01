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
from django.conf import settings
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

from .models import SesionCaja, Pago
from .printer import imprimir_ticket, imprimir_factura, imprimir_cierre, ticket_a_texto
from apps.ventas.models import NotaPedido
from apps.facturacion import emisor as fe_emisor

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

    class Meta:
        model  = Pago
        fields = [
            'id', 'numero_ticket',
            'pedido_id', 'pedido_numero', 'pedido_cliente',
            'cajero_nombre', 'medio_pago', 'medio_display',
            'monto', 'monto_recibido', 'vuelto',
            'estado', 'referencia_externa', 'fecha',
        ]


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
        sesion.monto_cierre       = request.data.get('monto_cierre', sesion.total_ventas + sesion.monto_apertura)
        sesion.observaciones_cierre = request.data.get('observaciones_cierre', '')
        sesion.fecha_cierre       = timezone.now()
        sesion.save()

        # Resumen para el ticket de cierre
        pagos = sesion.pagos.filter(estado=Pago.ESTADO_CONFIRMADO)
        resumen_medios = {}
        for p in pagos:
            resumen_medios[p.medio_pago] = resumen_medios.get(p.medio_pago, 0) + float(p.monto)

        # La diferencia de arqueo compara el efectivo físico contado contra lo
        # que debería haber en el cajón (apertura + ventas en efectivo). Ventas
        # con tarjeta/transferencia nunca entran al cajón, así que no deben
        # restarse acá o cualquier turno con ventas no-efectivo muestra un
        # faltante ficticio.
        total_efectivo = resumen_medios.get(Pago.MEDIO_EFECTIVO, 0)

        resumen_completo = {
            'resumen_medios': resumen_medios,
            'total_pagos':    pagos.count(),
            'total_ventas':   float(sesion.total_ventas),
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

    Flujo atómico:
      1. Valida que el pedido esté en estado 'listo'
      2. Crea el Pago
      3. Cambia el pedido a 'pagado'
      4. Descuenta el stock de cada ítem
      5. Emite WebSocket
    """
    permission_classes = [EsAdminOCajero]

    @transaction.atomic
    def post(self, request):
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
        )
        pago.save()

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
                },
                condicion_venta=condicion_venta,
            )

        # ── Generar datos del comprobante ─────────────────────
        datos_ticket = _datos_ticket(pedido, pago, sesion,
                                     tipo_comprobante=tipo_comprobante,
                                     cliente_ruc=cliente_ruc,
                                     cliente_razon_social=cliente_razon_social,
                                     cliente_telefono=cliente_telefono,
                                     cliente_direccion=cliente_direccion,
                                     condicion_venta=condicion_venta,
                                     documento=documento_electronico)
        texto_ticket = ticket_a_texto(datos_ticket)

        # ── Imprimir automáticamente según tipo ───────────────
        if tipo_comprobante == 'factura':
            resultado_impresion = imprimir_factura(datos_ticket)
        else:
            resultado_impresion = imprimir_ticket(datos_ticket)
        if not resultado_impresion['ok']:
            logger.warning(
                f'Impresión fallida para {tipo_comprobante} {pago.numero_ticket}: '
                f'{resultado_impresion.get("error")}'
            )

        # ── Respuesta con datos del comprobante ───────────────
        return Response({
            'ok':              True,
            'pago':            PagoSerializer(pago).data,
            'tipo_comprobante':tipo_comprobante,
            'ticket':          datos_ticket,
            'ticket_texto':    texto_ticket,
            'impresion':       resultado_impresion,
            'errores_stock':   errores_stock,
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


class ListaPagosView(views.APIView):
    """
    GET /caja/pagos/lista/?sesion=<id>
    Lista los pagos de la sesión activa o de una sesión específica.
    """
    permission_classes = [EsAdminOCajero]

    def get(self, request):
        sesion_id = request.query_params.get('sesion')
        if sesion_id:
            qs = Pago.objects.filter(sesion_caja_id=sesion_id)
            if request.user.rol != 'admin':
                qs = qs.filter(sesion_caja__cajero=request.user)
        else:
            sesion = _sesion_activa(request.user)
            qs = Pago.objects.filter(sesion_caja=sesion) if sesion else Pago.objects.none()

        qs = qs.select_related('pedido', 'cajero').order_by('-fecha')
        return Response({
            'results': PagoSerializer(qs, many=True).data,
            'count':   qs.count(),
        })


class ReimprimirTicketView(views.APIView):
    """
    POST /caja/pagos/<id>/reimprimir/
    Reimprime el comprobante de un pago ya procesado.
    Útil cuando el papel se atasca o el cliente pide otra copia.

    Si el pago tenía documento electrónico, se reimprime la FACTURA con su
    CDC y su timbrado originales — no un ticket. Reimprimir un ticket en
    lugar de la factura le daría al cliente un papel sin valor fiscal, y
    reconstruir los datos desde settings sacaría el timbrado de hoy en vez
    del que estaba vigente cuando se emitió.
    """
    permission_classes = [EsAdminOCajero]

    def post(self, request, pk):
        pago = get_object_or_404(
            Pago.objects.select_related('pedido', 'cajero', 'sesion_caja',
                                        'documento_electronico')
                        .prefetch_related('pedido__items__variante__producto'),
            pk=pk
        )

        documento = getattr(pago, 'documento_electronico', None)
        if documento is not None:
            datos_ticket = _datos_ticket(
                pago.pedido, pago, pago.sesion_caja,
                tipo_comprobante='factura',
                cliente_ruc=documento.receptor_ruc,
                cliente_razon_social=documento.receptor_razon_social,
                cliente_telefono=documento.receptor_telefono,
                cliente_direccion=documento.receptor_direccion,
                documento=documento,
            )
            resultado = imprimir_factura(datos_ticket)
        else:
            datos_ticket = _datos_ticket(pago.pedido, pago, pago.sesion_caja)
            resultado    = imprimir_ticket(datos_ticket)
        texto = ticket_a_texto(datos_ticket)

        return Response({
            'ok':           resultado['ok'],
            'impresion':    resultado,
            'ticket_texto': texto,
            'ticket':       datos_ticket,
            # Qué se imprimió realmente. Sin esto el frontend no puede saber
            # si salió un ticket o una factura, y avisaría cualquier cosa.
            'tipo_comprobante': 'factura' if documento is not None else 'ticket',
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


# ─── Helper de ticket ─────────────────────────────────────────────────────────

def _datos_ticket(pedido, pago, sesion, tipo_comprobante='ticket',
                  cliente_ruc='', cliente_razon_social='', cliente_telefono='',
                  cliente_direccion='', condicion_venta='Contado', documento=None):
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

    datos = {
        'numero_ticket':   pago.numero_ticket,
        'fecha':           pago.fecha.strftime('%d/%m/%Y %H:%M'),
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
        'monto_recibido':  float(pago.monto_recibido) if pago.monto_recibido else None,
        'vuelto':          float(pago.vuelto),
        'negocio':         'Oga Porã',
        'pie':             'Gracias por su compra',
    }

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