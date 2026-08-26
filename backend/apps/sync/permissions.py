"""
Autenticación entre nodos.

No usa JWT de usuario a propósito: el agente de sync corre solo, en una tarea
programada, sin nadie que escriba una contraseña, y darle un token de admin
sería darle permiso sobre toda la API para hacer una sola cosa. Un secreto
compartido, exclusivo del sync, hace exactamente lo necesario y nada más.

Se configura con `SYNC_TOKEN` en el `.env` de los dos equipos. Si está vacío,
los endpoints de sync quedan cerrados: es mejor que no anden a que anden
abiertos.
"""
import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class EsNodoSync(BasePermission):
    message = 'Token de sincronización ausente o inválido.'

    def has_permission(self, request, view):
        esperado = settings.SYNC['token']
        if not esperado:
            self.message = (
                'La sincronización está deshabilitada: falta SYNC_TOKEN en el .env '
                'de este equipo.'
            )
            return False

        recibido = request.headers.get('X-Sync-Token', '')
        # compare_digest y no ==: el tiempo que tarda una comparación normal
        # depende de cuántos caracteres coinciden y filtra el secreto de a poco.
        return hmac.compare_digest(str(recibido), str(esperado))
