"""
Endpoints de sincronización. Los consume el agente de la notebook, no la app.

No usan autenticación de usuario: el `X-Sync-Token` compartido es toda la
credencial. El agente corre solo, en una tarea programada, y darle un JWT
de admin sería darle permiso sobre toda la API para hacer una sola cosa.

Son cuatro cosas:
  POST /api/v1/sync/cambios/   — recibir un lote y aplicarlo
  GET  /api/v1/sync/estado/    — qué pendientes y conflictos hay acá
  GET  /api/v1/sync/catalogo/  — volcado del catálogo, para comparar dos equipos
  POST /api/v1/sync/foto/      — subir el archivo de una foto nueva

La dirección servidor → notebook NO pasa por acá: la sigue haciendo el
`pg_dump` + `psql` del agente, que ya funciona, es atómico y arrastra también
el stock, las ventas y la caja, que son de una sola dirección. Estos endpoints
cubren únicamente lo que antes no tenía forma de volver: lo que se editó en la
notebook. Ver `docs/sync_bidireccional.md`.
"""
import logging
import os

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import (
    api_view, authentication_classes, parser_classes, permission_classes,
)
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .aplicar import aplicar_lote
from .models import CambioSync, ConflictoSync, EstadoSync
from .permissions import EsNodoSync
from .registro import MODELOS_BIDIRECCIONALES
from .serializacion import modelo_de, serializar

logger = logging.getLogger(__name__)

# Tope de cambios por pedido. Con más, un catálogo entero cargado offline
# armaría un JSON de varios MB y el agente no tendría forma de reintentar por
# partes si se corta el WiFi a mitad de camino.
MAX_POR_LOTE = 500


@api_view(['POST'])
@authentication_classes([])
@permission_classes([EsNodoSync])
def recibir_cambios(request):
    """
    Recibe un lote de cambios del otro nodo y lo aplica.

    Cuerpo:  {"nodo": "NOTEBOOK-ANA", "cambios": [ ... ]}
    Devuelve el recuento y, si hubo, los conflictos que quedaron anotados.
    """
    cambios = request.data.get('cambios')
    nodo = (request.data.get('nodo') or '').strip()

    if not isinstance(cambios, list):
        return Response({'detalle': 'Falta la lista "cambios".'},
                        status=status.HTTP_400_BAD_REQUEST)
    if not nodo:
        return Response({'detalle': 'Falta "nodo": hay que decir quién manda el lote.'},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(cambios) > MAX_POR_LOTE:
        return Response(
            {'detalle': f'Máximo {MAX_POR_LOTE} cambios por lote, llegaron {len(cambios)}.'},
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    faltan = [c for c in cambios if not all(k in c for k in ('modelo', 'uid', 'operacion'))]
    if faltan:
        return Response({'detalle': 'Hay cambios sin modelo, uid u operacion.'},
                        status=status.HTTP_400_BAD_REQUEST)

    resultado = aplicar_lote(cambios)

    estado, _ = EstadoSync.objects.get_or_create(nodo=nodo)
    estado.ultimo_intento = timezone.now()
    estado.ultimo_exito = estado.ultimo_intento
    estado.cambios_recibidos += resultado.aplicados
    estado.conflictos += resultado.conflictos
    estado.detalle = (f'{resultado.aplicados} aplicados, '
                      f'{resultado.conflictos} en conflicto, '
                      f'{resultado.omitidos} omitidos')
    estado.save()

    logger.info('Sync desde %s: %s', nodo, estado.detalle)

    respuesta = resultado.como_dict()
    respuesta['nodo_receptor'] = settings.NODO['nombre']
    return Response(respuesta)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([EsNodoSync])
def estado_sync(request):
    """Diagnóstico: qué quedó pendiente y qué conflictos hay sin revisar."""
    return Response({
        'nodo':                settings.NODO['nombre'],
        'rol':                 settings.NODO['rol'],
        'cambios_pendientes':  CambioSync.objects.filter(empujado_en__isnull=True).count(),
        'conflictos_sin_ver':  ConflictoSync.objects.filter(revisado=False).count(),
        'nodos': [
            {
                'nodo':      e.nodo,
                'ultimo_exito': e.ultimo_exito,
                'recibidos': e.cambios_recibidos,
                'enviados':  e.cambios_enviados,
                'conflictos': e.conflictos,
                'detalle':   e.detalle,
            }
            for e in EstadoSync.objects.all()
        ],
    })


@api_view(['GET'])
@authentication_classes([])
@permission_classes([EsNodoSync])
def catalogo(request):
    """
    Volcado del catálogo de este equipo, para poder compararlo con el del otro.

    Existe por un problema concreto: el registro de cambios solo tiene lo que
    pasó **desde que el sync está instalado**. Todo lo que la notebook editó
    antes de eso es invisible para el sync y el primer `pg_dump` se lo lleva
    puesto — que es exactamente lo que ya pasó una vez (ver
    `docs/traspaso_pendientes.md`).

    Con esto, `manage.py sync_comparar` puede encontrar esas diferencias
    viejas y marcarlas para que se manden.

        GET /api/v1/sync/catalogo/?modelo=productos.Producto&desde=0&limite=200
    """
    etiqueta_ = request.query_params.get('modelo', '')
    if etiqueta_ not in MODELOS_BIDIRECCIONALES:
        return Response(
            {'detalle': f'"modelo" tiene que ser uno de: {", ".join(MODELOS_BIDIRECCIONALES)}'},
            status=status.HTTP_400_BAD_REQUEST)

    try:
        desde = max(0, int(request.query_params.get('desde', 0)))
        limite = min(500, max(1, int(request.query_params.get('limite', 200))))
    except ValueError:
        return Response({'detalle': '"desde" y "limite" tienen que ser números.'},
                        status=status.HTTP_400_BAD_REQUEST)

    modelo = modelo_de(etiqueta_)
    total = modelo.objects.count()
    # Orden estable por uid: sin esto, dos páginas pueden repetir u omitir filas.
    filas = modelo.objects.order_by('uid')[desde:desde + limite]

    return Response({
        'modelo': etiqueta_,
        'total':  total,
        'desde':  desde,
        'filas': [
            {
                'uid':            str(f.uid),
                'actualizado_en': f.actualizado_en.isoformat(),
                'datos':          serializar(f),
            }
            for f in filas
        ],
    })


@api_view(['POST'])
@authentication_classes([])
@permission_classes([EsNodoSync])
@parser_classes([MultiPartParser, FormParser])
def subir_foto(request):
    """
    Recibe el archivo de una foto cargada en el otro nodo.

    La fila de `ImagenProducto` viaja con los cambios normales; acá viene el
    archivo en sí. Van por separado a propósito: una foto pesa cientos de KB y
    meterla en base64 dentro del lote haría que un corte de WiFi obligara a
    reenviar todo el catálogo.

    La ruta la manda el emisor y es la que quedó guardada en la fila, así que
    los dos lados terminan apuntando al mismo lugar.
    """
    archivo = request.FILES.get('archivo')
    ruta = (request.data.get('ruta') or '').strip().replace('\\', '/').lstrip('/')

    if not archivo or not ruta:
        return Response({'detalle': 'Faltan "archivo" y/o "ruta".'},
                        status=status.HTTP_400_BAD_REQUEST)

    # La ruta viene del otro equipo: se normaliza y se verifica que caiga
    # adentro de MEDIA_ROOT. Sin esto, un "../../config/settings.py" escribiría
    # donde no debe.
    destino_abs = os.path.abspath(os.path.join(settings.MEDIA_ROOT, ruta))
    if os.path.commonpath([destino_abs, os.path.abspath(settings.MEDIA_ROOT)]) != \
            os.path.abspath(settings.MEDIA_ROOT):
        return Response({'detalle': 'Ruta fuera de la carpeta de fotos.'},
                        status=status.HTTP_400_BAD_REQUEST)

    if default_storage.exists(ruta):
        # Ya la tenemos. No se pisa: las fotos no se editan, se reemplazan por
        # otra fila, así que un archivo con la misma ruta es el mismo archivo.
        return Response({'ruta': ruta, 'estado': 'ya_estaba'})

    default_storage.save(ruta, archivo)
    return Response({'ruta': ruta, 'estado': 'guardada'}, status=status.HTTP_201_CREATED)
