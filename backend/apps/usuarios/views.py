"""
apps/usuarios/views.py
CRUD completo de usuarios para el administrador.
Incluye cambio de contraseña y gestión de roles.
"""
from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Usuario
from .permissions import EsAdmin, TodosLosRoles


# ─── Serializers ──────────────────────────────────────────────────────────────

class UsuarioSerializer(serializers.ModelSerializer):
    rol_display              = serializers.CharField(source='get_rol_display', read_only=True)
    puede_editar_precio      = serializers.SerializerMethodField()
    puede_crear_pedido       = serializers.SerializerMethodField()

    class Meta:
        model  = Usuario
        fields = ['id', 'username', 'nombre_completo', 'rol', 'rol_display', 'activo',
                  'puede_editar_precio', 'puede_crear_pedido',
                  'fecha_creacion', 'ultimo_acceso']
        read_only_fields = ['id', 'fecha_creacion', 'ultimo_acceso']

    def get_puede_editar_precio(self, obj):
        return obj.puede_editar_precio_pedido()

    def get_puede_crear_pedido(self, obj):
        return obj.puede_crear_pedido()


class UsuarioCreateSerializer(serializers.Serializer):
    username        = serializers.CharField(max_length=50)
    nombre_completo = serializers.CharField(max_length=150)
    rol             = serializers.ChoiceField(choices=Usuario.ROLES)
    password        = serializers.CharField(min_length=6, write_only=True)

    def validate_username(self, value):
        if Usuario.objects.filter(username=value.strip().lower()).exists():
            raise serializers.ValidationError(f'El usuario "{value}" ya existe.')
        return value.strip().lower()

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def create(self, validated_data):
        return Usuario.objects.create_user(
            username        = validated_data['username'],
            password        = validated_data['password'],
            nombre_completo = validated_data['nombre_completo'],
            rol             = validated_data['rol'],
        )


class UsuarioUpdateSerializer(serializers.Serializer):
    nombre_completo = serializers.CharField(max_length=150, required=False)
    rol             = serializers.ChoiceField(choices=Usuario.ROLES, required=False)
    activo          = serializers.BooleanField(required=False)

    def update(self, instance, validated_data):
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        return instance


class CambiarPasswordSerializer(serializers.Serializer):
    password_nuevo      = serializers.CharField(min_length=6, write_only=True)
    password_confirmar  = serializers.CharField(min_length=6, write_only=True)

    def validate(self, attrs):
        if attrs['password_nuevo'] != attrs['password_confirmar']:
            raise serializers.ValidationError('Las contraseñas no coinciden.')
        try:
            validate_password(attrs['password_nuevo'])
        except ValidationError as e:
            raise serializers.ValidationError({'password_nuevo': list(e.messages)})
        return attrs


# ─── Views ────────────────────────────────────────────────────────────────────

class MeView(views.APIView):
    """GET /usuarios/me/ — datos del usuario autenticado."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Actualizar último acceso
        Usuario.objects.filter(pk=request.user.pk).update(ultimo_acceso=timezone.now())
        return Response(UsuarioSerializer(request.user).data)


class UsuarioListCreateView(views.APIView):
    """
    GET  /usuarios/      — listado de usuarios (solo admin)
    POST /usuarios/      — crear usuario      (solo admin)
    """

    def get_permissions(self):
        return [EsAdmin()]

    def get(self, request):
        activo = request.query_params.get('activo')
        rol    = request.query_params.get('rol')

        qs = Usuario.objects.order_by('nombre_completo')
        if activo is not None:
            qs = qs.filter(activo=activo.lower() in ('1', 'true', 'yes'))
        if rol:
            qs = qs.filter(rol=rol)

        return Response({
            'results': UsuarioSerializer(qs, many=True).data,
            'count':   qs.count(),
        })

    def post(self, request):
        serializer = UsuarioCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        usuario = serializer.save()
        return Response(UsuarioSerializer(usuario).data, status=status.HTTP_201_CREATED)


class UsuarioDetailView(views.APIView):
    """
    GET    /usuarios/<id>/  — detalle
    PATCH  /usuarios/<id>/  — actualizar nombre, rol, activo
    DELETE /usuarios/<id>/  — desactivar (no eliminar físicamente)
    """
    permission_classes = [EsAdmin]

    def _get_usuario(self, pk):
        try:
            return Usuario.objects.get(pk=pk)
        except Usuario.DoesNotExist:
            return None

    def get(self, request, pk):
        usuario = self._get_usuario(pk)
        if not usuario:
            return Response({'error': 'Usuario no encontrado.'}, status=404)
        return Response(UsuarioSerializer(usuario).data)

    def patch(self, request, pk):
        usuario = self._get_usuario(pk)
        if not usuario:
            return Response({'error': 'Usuario no encontrado.'}, status=404)

        # No permitir que el admin se quite el rol a sí mismo
        if usuario.pk == request.user.pk and 'rol' in request.data:
            nuevo_rol = request.data['rol']
            if nuevo_rol != Usuario.ROL_ADMIN:
                return Response(
                    {'error': 'No podés cambiar tu propio rol de administrador.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Mismo resguardo que DELETE: no permitir que se desactive a sí
        # mismo por acá (el switch "Usuario activo" del modal de edición
        # llega por PATCH, no por DELETE).
        if usuario.pk == request.user.pk and 'activo' in request.data:
            activo_nuevo = request.data['activo']
            if activo_nuevo in (False, 'false', '0', 0):
                return Response(
                    {'error': 'No podés desactivar tu propia cuenta.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = UsuarioUpdateSerializer(usuario, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        usuario = serializer.save()
        return Response(UsuarioSerializer(usuario).data)

    def delete(self, request, pk):
        usuario = self._get_usuario(pk)
        if not usuario:
            return Response({'error': 'Usuario no encontrado.'}, status=404)

        if usuario.pk == request.user.pk:
            return Response(
                {'error': 'No podés desactivar tu propia cuenta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Desactivar en lugar de eliminar para preservar el historial
        usuario.activo = False
        usuario.save(update_fields=['activo'])
        return Response({'detail': f'Usuario {usuario.username} desactivado.'})


class CambiarPasswordView(views.APIView):
    """
    POST /usuarios/<id>/password/
    Admin puede cambiar la contraseña de cualquier usuario.
    El usuario puede cambiar la suya (requiere password actual).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            usuario = Usuario.objects.get(pk=pk)
        except Usuario.DoesNotExist:
            return Response({'error': 'Usuario no encontrado.'}, status=404)

        # Solo el mismo usuario o un admin puede cambiar contraseñas
        es_propio = usuario.pk == request.user.pk
        es_admin  = request.user.rol == Usuario.ROL_ADMIN

        if not (es_propio or es_admin):
            return Response(
                {'error': 'Solo podés cambiar tu propia contraseña.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Si es el propio usuario, verificar la contraseña actual
        if es_propio and not es_admin:
            password_actual = request.data.get('password_actual', '')
            if not usuario.check_password(password_actual):
                return Response(
                    {'error': 'La contraseña actual es incorrecta.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = CambiarPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        usuario.set_password(serializer.validated_data['password_nuevo'])
        usuario.save(update_fields=['password'])

        return Response({'detail': 'Contraseña actualizada correctamente.'})
