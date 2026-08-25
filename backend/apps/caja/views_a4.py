"""
apps/caja/views_a4.py
Endpoints de la Epson EcoTank L1250 (hoja A4).

**La L1250 no imprime facturas.** El comprobante fiscal sale por otro equipo;
acá está solo lo que necesita hoja A4 común — hoy, la planilla de etiquetas de
código de barras que le da algo que leer al lector FTX-LC123BH5.

Van aparte de views.py porque son otro dispositivo con otra salida: views.py
manda bytes ESC/POS a la térmica y responde JSON, y acá se devuelve un PDF o
se lo manda a la cola de Windows.
"""
import logging

from django.http import HttpResponse
from rest_framework import views, status
from rest_framework.response import Response

from apps.usuarios.permissions import EsAdminODeposito
from apps.productos.models import Variante

from . import impresora_a4

logger = logging.getLogger(__name__)


class EtiquetasCodigoBarrasView(views.APIView):
    """
    GET  /caja/etiquetas/?variantes=1,2,3[&desde=4][&imprimir=1]
    POST /caja/etiquetas/   {"variantes": [1,2,3], "desde": 4, "imprimir": false}

    Planilla A4 de etiquetas con código de barras para pegar en la mercadería.
    Es la contraparte física del lector: sin etiqueta no hay nada que escanear.

    `desde` saltea las primeras N celdas de la primera hoja, para reusar una
    planilla ya empezada.

    Sin `variantes` toma todas las variantes activas que tengan código de
    barras cargado — útil para etiquetar el catálogo entero de una vez.
    """
    permission_classes = [EsAdminODeposito]

    def get(self, request):
        ids = [x for x in (request.query_params.get('variantes', '') or '').split(',') if x.strip()]
        desde = request.query_params.get('desde', 0)
        imprimir = bool(request.query_params.get('imprimir'))
        return self._planilla(request, ids, desde, imprimir)

    def post(self, request):
        ids = request.data.get('variantes') or []
        desde = request.data.get('desde', 0)
        imprimir = bool(request.data.get('imprimir'))
        return self._planilla(request, ids, desde, imprimir)

    def _planilla(self, request, ids, desde, imprimir):
        try:
            desde = max(0, int(desde or 0))
        except (TypeError, ValueError):
            desde = 0

        qs = (Variante.objects
              .select_related('producto', 'acabado')
              .filter(activa=True, producto__activo=True)
              .exclude(codigo_barras=''))

        if ids:
            try:
                ids_int = [int(x) for x in ids]
            except (TypeError, ValueError):
                return Response({'error': 'La lista de variantes tiene valores no numéricos.'},
                                status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(pk__in=ids_int)

        qs = qs.order_by('producto__codigo', 'sku')
        variantes = list(qs[:500])

        if not variantes:
            return Response({
                'error': (
                    'Ninguna de las variantes pedidas tiene código de barras '
                    'cargado. Asignalos primero con '
                    '`python manage.py asignar_codigos_barras`, o escaneando '
                    'el EAN de la caja desde la ficha del producto.'
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        etiquetas = [{
            'codigo':  v.codigo_barras,
            'sku':     v.sku,
            'nombre':  v.producto.nombre,
            'detalle': ' · '.join(p for p in [v.dimension_display, v.color,
                                              v.acabado.nombre if v.acabado else ''] if p),
            'precio':  v.precio_venta,
        } for v in variantes]

        pdf = impresora_a4.etiquetas_pdf(etiquetas, desde_posicion=desde)

        if imprimir:
            resultado = impresora_a4.imprimir_pdf(pdf, titulo='etiquetas')
            if not resultado['ok']:
                logger.warning('Impresión de etiquetas fallida: %s',
                               resultado.get('error'))
            return Response({
                'ok':        resultado['ok'],
                'impresion': resultado,
                'etiquetas': len(etiquetas),
            }, status=status.HTTP_200_OK if resultado['ok']
               else status.HTTP_503_SERVICE_UNAVAILABLE)

        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = 'inline; filename="etiquetas.pdf"'
        return resp
