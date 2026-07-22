from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    model = Usuario
    list_display = ['username', 'nombre_completo', 'rol', 'activo', 'fecha_creacion']
    list_filter = ['rol', 'activo']
    search_fields = ['username', 'nombre_completo']
    list_editable = ['activo']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Información personal', {'fields': ('nombre_completo',)}),
        ('Rol y permisos', {'fields': ('rol', 'activo', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas', {'fields': ('last_login', 'fecha_creacion', 'ultimo_acceso')}),
    )
    readonly_fields = ['fecha_creacion', 'ultimo_acceso', 'last_login']

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'nombre_completo', 'rol', 'password1', 'password2'),
        }),
    )
    ordering = ['username']
