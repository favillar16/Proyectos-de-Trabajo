"""
Admin de facturación electrónica.

Es la ventana para diagnosticar cuando algo no cierra con el SIFEN: ver qué
documentos quedaron sin transmitir, con qué error volvieron y en qué número
va cada punto de expedición.

Todo es de solo lectura salvo el rango del timbrado. Un documento electrónico
emitido no se edita: si está mal, se cancela con un evento o se emite una
nota de crédito. Editarlo a mano dejaría el sistema diciendo una cosa y el
SIFEN otra.
"""
from django.contrib import admin

from .models import DocumentoElectronico, SecuenciaComprobante


@admin.register(SecuenciaComprobante)
class SecuenciaComprobanteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'ultimo_numero', 'numero_hasta',
                    'numeros_restantes', 'activa')
    list_filter = ('activa', 'tipo_documento')
    # ultimo_numero NO se edita acá: se toca solo desde
    # SecuenciaComprobante.siguiente(), que es lo que garantiza que no haya
    # saltos ni duplicados. Cambiarlo a mano rompe esa garantía.
    readonly_fields = ('ultimo_numero', 'fecha_actualizacion')

    @admin.display(description='Números restantes')
    def numeros_restantes(self, obj):
        return obj.numeros_restantes


@admin.register(DocumentoElectronico)
class DocumentoElectronicoAdmin(admin.ModelAdmin):
    list_display = ('numero_completo', 'fecha_emision', 'estado',
                    'receptor_razon_social', 'total', 'intentos_envio')
    list_filter = ('estado', 'tipo_documento', 'fecha_emision')
    search_fields = ('numero_completo', 'cdc', 'receptor_ruc',
                     'receptor_razon_social')
    date_hierarchy = 'fecha_emision'
    ordering = ('-fecha_emision',)

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        # Un DE nace de un cobro, nunca de una carga manual: crearlo acá
        # saltearía la numeración y el CDC.
        return False

    def has_delete_permission(self, request, obj=None):
        # Borrar un DE dejaría un hueco en el correlativo que hay que
        # justificar ante la DNIT.
        return False
