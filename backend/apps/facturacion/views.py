"""
API de facturación electrónica.

Poco y concreto: emitir una nota de crédito, y mirar el estado de la cola de
documentos. La emisión de facturas no está acá — sale sola al confirmar un
cobro, desde `apps/caja/views.py`.
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.permissions import EsAdmin, EsAdminOCajero

from . import cdc as cdc_mod
from . import codigos, nota_credito
from .models import DocumentoElectronico

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
