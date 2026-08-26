"""
Resolver choques de unicidad al aplicar una fila del otro nodo.

El `uid` resuelve la identidad, pero no alcanza: los modelos tienen además
campos únicos que cada base llena por su cuenta, y dos equipos trabajando sin
verse llegan a los mismos valores. Hay dos casos y se resuelven al revés uno
del otro.

**Fusionar** — `Marca.nombre`, `Acabado.nombre`, la combinación que identifica
a una `Variante`. Si la notebook cargó la marca "KLAUKOL" y el local también,
no son dos marcas: es la misma escrita dos veces. Se adopta la fila que ya
está acá y se le pone el uid que viene, así los dos equipos quedan hablando de
la misma fila de ahora en adelante.

**Regenerar** — `Producto.codigo`, `Producto.slug`, `Variante.sku`. Los genera
`save()` buscando el primer correlativo libre, así que dos equipos offline
sacan POR-004 los dos. Acá sí son productos distintos: se le vacía el campo a
la fila que llega y el modelo le da uno nuevo.

`Variante.codigo_barras` no entra en ninguno de los dos: es el EAN impreso en
la caja. Si dos variantes distintas dicen tener el mismo, hay un error de
carga que ningún automatismo puede resolver — se deja en NULL y se anota.
"""
import logging

logger = logging.getLogger(__name__)

# Campos que identifican a la misma cosa del mundo real. Si coinciden, las dos
# filas son la misma y hay que fusionarlas.
CLAVES_NATURALES = {
    'productos.Marca':    ['nombre'],
    'productos.Acabado':  ['nombre'],
    'productos.Categoria': ['nombre'],
    'productos.Variante': ['producto', 'color', 'acabado', 'largo_cm', 'ancho_cm'],
}

# Campos únicos que el modelo sabe regenerar solo si se los deja vacíos.
CAMPOS_REGENERABLES = {
    'productos.Producto': ['codigo', 'slug'],
    'productos.Variante': ['sku'],
}

def buscar_equivalente(modelo, etiqueta_, instancia, uid_entrante):
    """
    La fila local que representa la misma cosa que `instancia`, si existe.

    Devuelve None si el modelo no tiene clave natural o si no hay coincidencia.
    """
    campos = CLAVES_NATURALES.get(etiqueta_)
    if not campos:
        return None

    filtro = {}
    for nombre in campos:
        campo = modelo._meta.get_field(nombre)
        valor = getattr(instancia, campo.attname if campo.is_relation else nombre, None)
        if valor in (None, ''):
            # Un campo vacío no identifica nada: sin él la clave no sirve.
            if campo.null or campo.blank:
                filtro[nombre] = valor
                continue
            return None
        filtro[campo.attname if campo.is_relation else nombre] = valor

    return modelo.objects.filter(**filtro).exclude(uid=uid_entrante).first()

def resolver_choques_unicos(modelo, etiqueta_, instancia, uid_entrante):
    """
    Deja `instancia` en condiciones de guardarse sin violar ningún UNIQUE.

    Devuelve la lista de ajustes hechos, para poder informarlos: que un
    producto haya entrado con otro código es algo que alguien tiene que poder
    ver, aunque el sync no se haya roto.
    """
    ajustes = []
    regenerables = set(CAMPOS_REGENERABLES.get(etiqueta_, ()))

    for campo in modelo._meta.concrete_fields:
        if not campo.unique or campo.primary_key or campo.name == 'uid':
            continue

        valor = getattr(instancia, campo.attname, None)
        if valor in (None, ''):
            continue

        otras = modelo.objects.filter(**{campo.name: valor}).exclude(uid=uid_entrante)
        if instancia.pk:
            # La fila puede ser una local que estamos adoptando: su uid nuevo
            # todavía no está en la base, así que excluirla por uid no alcanza
            # y se detectaría a sí misma como choque.
            otras = otras.exclude(pk=instancia.pk)
        if not otras.exists():
            continue

        if campo.name in regenerables:
            # Vacío → `save()` le asigna el próximo libre de esta base.
            setattr(instancia, campo.attname, '')
            ajustes.append(
                f'"{campo.name}" venía como "{valor}", que ya estaba usado acá; '
                f'se le asignó uno nuevo.')
        elif campo.null:
            setattr(instancia, campo.attname, None)
            ajustes.append(
                f'"{campo.name}"="{valor}" ya pertenece a otra fila; se dejó vacío '
                f'para no pisarla. Hay que corregirlo a mano.')
        else:
            # Único, obligatorio y no regenerable. No hay salida automática:
            # que reviente y quede como conflicto, con el dato completo.
            raise ValueError(
                f'"{campo.name}"="{valor}" ya existe en otra fila y no se puede '
                f'regenerar automáticamente.')

    if ajustes:
        logger.info('Sync — ajustes de unicidad en %s %s: %s',
                    etiqueta_, uid_entrante, '; '.join(ajustes))
    return ajustes
