"""
App: usuarios
Modelo de usuario personalizado con sistema de roles
"""
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models


class UsuarioManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('El username es obligatorio')
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('rol', Usuario.ROL_ADMIN)
        return self.create_user(username, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    ROL_ADMIN = 'admin'
    ROL_ENCARGADA_VENTAS = 'encargada_ventas'
    ROL_VENDEDOR = 'vendedor'
    ROL_CAJERO = 'cajero'
    ROL_DEPOSITO = 'deposito'

    ROLES = [
        (ROL_ADMIN, 'Administrador'),
        (ROL_ENCARGADA_VENTAS, 'Encargada de Ventas'),
        (ROL_VENDEDOR, 'Vendedor'),
        (ROL_CAJERO, 'Cajero'),
        (ROL_DEPOSITO, 'Depósito'),
    ]

    username = models.CharField(max_length=50, unique=True)
    nombre_completo = models.CharField(max_length=150)
    rol = models.CharField(max_length=20, choices=ROLES, default=ROL_VENDEDOR)
    activo = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultimo_acceso = models.DateTimeField(null=True, blank=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['nombre_completo']

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f'{self.nombre_completo} ({self.get_rol_display()})'

    @property
    def is_active(self):
        return self.activo

    def puede_ver_caja(self):
        return self.rol in [self.ROL_ADMIN, self.ROL_CAJERO]

    def puede_ver_deposito(self):
        return self.rol in [self.ROL_ADMIN, self.ROL_DEPOSITO]

    def puede_crear_pedido(self):
        return self.rol in [self.ROL_ADMIN, self.ROL_ENCARGADA_VENTAS, self.ROL_VENDEDOR]

    def puede_editar_precio_pedido(self):
        """Solo admin y Encargada de Ventas pueden modificar precios al armar un pedido."""
        return self.rol in [self.ROL_ADMIN, self.ROL_ENCARGADA_VENTAS]
