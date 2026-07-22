from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/pedidos/(?P<pedido_id>\d+)/$', consumers.PedidoConsumer.as_asgi()),
    re_path(r'ws/pedidos/rol/(?P<rol>\w+)/$', consumers.RolConsumer.as_asgi()),
]
