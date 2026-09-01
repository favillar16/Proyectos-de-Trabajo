"""
Router que manda la app `sync` a su propia base SQLite.

Por qué: la sincronización servidor → notebook usa `pg_dump` + `psql`, que
borra y rehace `ceramica_db` completa. El registro de cambios pendientes de
empujar tiene que sobrevivir a eso — si viviera en `ceramica_db`, el primer
sync exitoso borraría justamente las ediciones que la notebook hizo estando
afuera del local, antes de alcanzar a mandarlas.

Va en SQLite y no en otra base Postgres para que no haya un segundo servicio
que configurar, respaldar ni arrancar: es un archivo al lado del proyecto.
El volumen es bajo (unos pocos miles de filas entre sync y sync) y todos los
accesos son de un solo proceso.
"""

APP = 'sync'
BASE = 'sync'


class SyncRouter:

    def db_for_read(self, model, **hints):
        return BASE if model._meta.app_label == APP else None

    def db_for_write(self, model, **hints):
        return BASE if model._meta.app_label == APP else None

    def allow_relation(self, obj1, obj2, **hints):
        """
        Las tablas de sync no tienen claves foráneas hacia el catálogo a
        propósito: guardan `modelo` + `uid` como texto. Si tuvieran FK reales,
        Django exigiría que todo viviera en la misma base y el borrado de un
        producto se llevaría puesto su historial de cambios.
        """
        etiquetas = {obj1._meta.app_label, obj2._meta.app_label}
        if APP in etiquetas:
            return len(etiquetas) == 1
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == APP:
            return db == BASE
        # Ninguna otra app entra en la base de sync.
        return None if db != BASE else False
