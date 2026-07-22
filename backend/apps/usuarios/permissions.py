"""
apps/usuarios/permissions.py
Clases de permisos basadas en roles para usar en cualquier view.

Uso:
    from apps.usuarios.permissions import EsAdmin, EsVendedor, EsCajero, EsDeposito
    from apps.usuarios.permissions import EsAdminOVendedor, SoloLectura

    class MiView(APIView):
        permission_classes = [EsAdminOVendedor]

Cada clase tiene:
  - has_permission(request, view)  → verifica el rol antes de procesar la request
  - El mensaje de error es descriptivo para facilitar el debug

Convenciones:
  - "Es<Rol>"       → solo ese rol (+ admin siempre puede todo)
  - "EsAdminO<Rol>" → admin o ese rol específico
  - "SoloLectura"   → cualquier autenticado puede GET, solo admin puede escribir
"""
from rest_framework.permissions import BasePermission, IsAuthenticated

METODOS_ESCRITURA = ('POST', 'PUT', 'PATCH', 'DELETE')
METODOS_LECTURA   = ('GET', 'HEAD', 'OPTIONS')


def _es_rol(request, *roles):
    """Helper: retorna True si el usuario tiene uno de los roles indicados."""
    return (
        request.user
        and request.user.is_authenticated
        and request.user.rol in roles
    )


# ─── Permisos de rol único ────────────────────────────────────────────────────

class EsAdmin(BasePermission):
    message = 'Acción restringida a administradores.'

    def has_permission(self, request, view):
        return _es_rol(request, 'admin')


class EsVendedor(BasePermission):
    message = 'Acción restringida a vendedores.'

    def has_permission(self, request, view):
        return _es_rol(request, 'vendedor', 'encargada_ventas', 'admin')


class EsEncargadaVentas(BasePermission):
    """Encargada de Ventas (segundo al mando) o admin."""
    message = 'Acción restringida a la Encargada de Ventas.'

    def has_permission(self, request, view):
        return _es_rol(request, 'encargada_ventas', 'admin')


class EsCajero(BasePermission):
    message = 'Acción restringida al módulo de caja.'

    def has_permission(self, request, view):
        return _es_rol(request, 'cajero', 'admin')


class EsDeposito(BasePermission):
    message = 'Acción restringida al personal de depósito.'

    def has_permission(self, request, view):
        return _es_rol(request, 'deposito', 'admin')


# ─── Permisos combinados ──────────────────────────────────────────────────────

class EsAdminOVendedor(BasePermission):
    message = 'Acción restringida a administradores y vendedores.'

    def has_permission(self, request, view):
        return _es_rol(request, 'admin', 'vendedor', 'encargada_ventas')


class EsAdminOCajero(BasePermission):
    message = 'Acción restringida a administradores y cajeros.'

    def has_permission(self, request, view):
        return _es_rol(request, 'admin', 'cajero')


class EsAdminODeposito(BasePermission):
    message = 'Acción restringida a administradores y personal de depósito.'

    def has_permission(self, request, view):
        return _es_rol(request, 'admin', 'deposito')


class EsAdminVendedorODeposito(BasePermission):
    """Para pedidos: vendedor crea, depósito prepara, ambos ven."""
    message = 'Acción restringida a vendedores, depósito y administradores.'

    def has_permission(self, request, view):
        return _es_rol(request, 'admin', 'vendedor', 'encargada_ventas', 'deposito')


class TodosLosRoles(BasePermission):
    """Cualquier usuario autenticado con rol válido."""
    message = 'Usuario sin rol asignado.'

    def has_permission(self, request, view):
        return _es_rol(request, 'admin', 'vendedor', 'encargada_ventas', 'cajero', 'deposito')


# ─── Permiso mixto lectura/escritura ─────────────────────────────────────────

class LecturaLibreEscrituraAdmin(BasePermission):
    """
    GET: cualquier usuario autenticado
    POST/PUT/PATCH/DELETE: solo admin
    Útil para catálogos (categorías, marcas, acabados).
    """
    message = 'Solo los administradores pueden modificar este recurso.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in METODOS_LECTURA:
            return True
        return _es_rol(request, 'admin')


class LecturaLibreEscrituraAdminOVendedor(BasePermission):
    """
    GET: cualquier autenticado
    Escritura: admin o vendedor
    Útil para productos.
    """
    message = 'Solo administradores o vendedores pueden modificar productos.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in METODOS_LECTURA:
            return True
        return _es_rol(request, 'admin', 'vendedor', 'encargada_ventas')


class PuedeEditarPrecioEnPedido(BasePermission):
    """
    Facultad exclusiva de modificar el precio unitario / monto al armar una
    nota de pedido. Reservada a la Encargada de Ventas (segundo al mando) y admin.
    El vendedor común arma pedidos pero con los precios de catálogo fijos.
    """
    message = 'Solo la Encargada de Ventas o un administrador pueden modificar precios en un pedido.'

    def has_permission(self, request, view):
        return _es_rol(request, 'admin', 'encargada_ventas')


# ─── Permiso por acción de ViewSet ────────────────────────────────────────────

class PermisosPorAccion(BasePermission):
    """
    Permite definir permisos distintos por acción de ViewSet.
    Se configura con el atributo `permisos_por_accion` en la vista.

    Ejemplo:
        class ProductoViewSet(viewsets.ModelViewSet):
            permisos_por_accion = {
                'list':    [IsAuthenticated],
                'create':  [EsAdminOVendedor],
                'destroy': [EsAdmin],
            }
            permission_classes = [PermisosPorAccion]
    """
    def has_permission(self, request, view):
        accion = getattr(view, 'action', None)
        mapa   = getattr(view, 'permisos_por_accion', {})

        clases = mapa.get(accion) or mapa.get('default') or [IsAuthenticated]

        for ClasePermiso in clases:
            permiso = ClasePermiso()
            if not permiso.has_permission(request, view):
                self.message = getattr(permiso, 'message', 'Permiso denegado.')
                return False
        return True
