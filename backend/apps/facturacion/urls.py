"""Rutas de facturación electrónica."""
from django.urls import path

from .views import (AutofacturaView, CancelarDocumentoView, ColaDocumentosView,
                    ConsultaRucView, GeografiaView,
                    DatosTrasladoView, EmitirNotaCreditoView,
                    EmitirNotaDebitoView, EmitirRemisionView,
                    EventosReceptorView, InutilizacionesView, KudeView,
                    LotesView,
                    MotivosDebitoView, MotivosNotaView, NumerosSinUsarView,
                    OpcionesTrasladoView, VentasSinDocumentoView)

urlpatterns = [
    path('documentos/', ColaDocumentosView.as_view(), name='fe-documentos'),
    # El punto ciego de la cola: los cobros facturados que NO llegaron a
    # generar un documento. No aparecen arriba porque arriba se listan
    # documentos que existen.
    path('ventas-sin-documento/', VentasSinDocumentoView.as_view(),
         name='fe-ventas-sin-documento'),
    path('documentos/<int:pk>/nota-credito/', EmitirNotaCreditoView.as_view(),
         name='fe-nota-credito'),
    # KuDE: el PDF que se le entrega al cliente (Manual §13).
    path('documentos/<int:pk>/kude/', KudeView.as_view(), name='fe-kude'),
    path('motivos-nota/', MotivosNotaView.as_view(), name='fe-motivos-nota'),
    # Nota de débito: el espejo de la de crédito — suma un importe en vez de
    # revertirlo. Comparte la rama del XML pero nunca toca stock.
    path('documentos/<int:pk>/nota-debito/', EmitirNotaDebitoView.as_view(),
         name='fe-nota-debito'),
    path('motivos-debito/', MotivosDebitoView.as_view(),
         name='fe-motivos-debito'),

    # Camino asincrónico y consulta de RUC: los tres web services que
    # faltaban de los que exige la Guia de Pruebas.
    path('lotes/', LotesView.as_view(), name='fe-lotes'),
    path('consulta-ruc/', ConsultaRucView.as_view(), name='fe-consulta-ruc'),

    # Eventos del rol RECEPTOR: lo que el local declara sobre un DTE que le
    # emitio otro. Van por CDC porque ese documento no esta en esta base.
    path('eventos-receptor/', EventosReceptorView.as_view(),
         name='fe-eventos-receptor'),

    # Autofactura: el unico tipo que documenta una COMPRA, no una venta.
    # Por eso no va por documento ni por pedido: no cuelga de un cobro.
    path('autofacturas/', AutofacturaView.as_view(), name='fe-autofacturas'),
    # Tablas geograficas de la DNIT, para el domicilio codificado que pide
    # la autofactura. Salen del sidecar y no necesitan certificado.
    path('geografia/', GeografiaView.as_view(), name='fe-geografia'),

    # Eventos del emisor (Fase C). La cancelación cuelga del documento
    # —cancela ese DTE— y la inutilización no, porque declara números que
    # nunca llegaron a ser un documento.
    path('documentos/<int:pk>/cancelar/', CancelarDocumentoView.as_view(),
         name='fe-cancelar'),
    path('inutilizaciones/', InutilizacionesView.as_view(),
         name='fe-inutilizaciones'),
    path('numeros-sin-usar/', NumerosSinUsarView.as_view(),
         name='fe-numeros-sin-usar'),

    # Datos del traslado, para la nota de remisión. Cuelgan del pedido y no
    # del cobro: una remisión describe un movimiento de mercadería, no una
    # venta. Por eso la ruta va por pedido y no por documento.
    path('opciones-traslado/', OpcionesTrasladoView.as_view(),
         name='fe-opciones-traslado'),
    path('pedidos/<int:pedido_id>/traslado/', DatosTrasladoView.as_view(),
         name='fe-traslado'),

    # Emitir la remisión y consultar si ya está emitida. Va por pedido por lo
    # mismo que el traslado, y es una acción aparte del cobro: la remisión
    # respalda el traslado de la mercadería, no la venta (Decreto 6.539/2005
    # art. 30), y no toda venta se despacha.
    path('pedidos/<int:pedido_id>/remision/', EmitirRemisionView.as_view(),
         name='fe-remision'),
]
