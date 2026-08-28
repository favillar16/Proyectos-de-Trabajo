"""
Carga el lote de compras de agosto 2026 (docs/carga_final/productos_a_cargar.csv).

Es un CSV distinto al de `cargar_referencias_productos`: viene de transcribir
las 26 facturas escaneadas del lote y trae seis columnas de trazabilidad al
papel (página, proveedor, factura, fecha, código del proveedor, descripción
textual) que se guardan en `notas_internas` para poder volver al comprobante.

La diferencia importante: **el CSV no trae precio de venta**. Todos los
importes son de COSTO (lo que se le pagó al proveedor, IVA incluido). El
`precio_base` se deriva acá aplicando un margen, y sin margen el comando no
corre: cargar 184 productos con el precio equivocado es peor que no cargarlos.

Uso típico:

    python manage.py cargar_lote_facturas --margen 40 --dry-run
    python manage.py cargar_lote_facturas --margen 40 \\
        --margen-rubro ceramica=35,porcelanato=35,pastina=60

Un producto puede tener varias filas (mismo nombre, distinto color): esas se
agrupan en un solo Producto con una Variante por fila. La clave para no
duplicar es (nombre_producto, color), que es única en las 184 filas.

Idempotente: se puede correr de nuevo sin duplicar nada. Lo ya cargado se
informa como "= ya existe" y no se toca — tampoco el stock, así que repetir
el comando no infla las cantidades.

Filas que NO entran solas (ver docs/carga_final/pendientes_verificacion.md):

  · Las marcadas «no cargar al stock» (ROTO, Devolución) se dan de alta en el
    catálogo pero con stock 0: el producto existe, la mercadería no está.
  · Las marcadas «confirmar si…» son decisiones de negocio abiertas (¿ya se
    vendió?, ¿el exhibidor es mercadería?) y se saltean. Con
    --incluir-dudosos entran con su cantidad.
"""
import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.inventario.models import MovimientoStock, Stock
from apps.productos.models import Categoria, Marca, Producto, Variante
from apps.usuarios.models import Usuario

RUTA_DEFAULT = (Path(settings.BASE_DIR).parent
                / 'docs' / 'carga_final' / 'productos_a_cargar.csv')

# El nombre legible de cada tipo, para crear la Categoria que falte.
NOMBRE_CATEGORIA = dict(Categoria.TIPOS)

# Marcas en observaciones que definen qué hacer con la fila.
RE_SIN_STOCK = re.compile(r'no cargar al stock', re.IGNORECASE)
RE_DUDOSA = re.compile(r'confirmar si', re.IGNORECASE)

# Atributos de variante anotados en observaciones: "tipo_cisterna=alta".
RE_ATRIBUTO = re.compile(r'\b(tipo_grifo|tipo_ducha|tipo_cisterna)=([a-z_]+)')

REDONDEO_DEFAULT = 1000   # los precios de mostrador se manejan de a mil Gs.


class _Rollback(Exception):
    """Corta la transacción del --dry-run. No es un error."""


def _dec(valor):
    valor = (valor or '').strip()
    if not valor:
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None


def _entero(valor):
    numero = _dec(valor)
    return int(numero) if numero is not None else None


def _parsear_margenes(texto):
    """'ceramica=35,pastina=60' → {'ceramica': Decimal('35'), ...}"""
    margenes = {}
    for parte in (texto or '').split(','):
        parte = parte.strip()
        if not parte:
            continue
        if '=' not in parte:
            raise CommandError(
                f'--margen-rubro mal formado en {parte!r}. '
                f'Se espera rubro=porcentaje, por ejemplo: ceramica=35,pastina=60')
        rubro, porcentaje = parte.split('=', 1)
        rubro = rubro.strip()
        if rubro not in NOMBRE_CATEGORIA:
            raise CommandError(
                f'Rubro desconocido en --margen-rubro: {rubro!r}. '
                f'Los válidos son: {", ".join(sorted(NOMBRE_CATEGORIA))}')
        valor = _dec(porcentaje)
        if valor is None or valor < 0:
            raise CommandError(f'Margen inválido para {rubro}: {porcentaje!r}')
        margenes[rubro] = valor
    return margenes


class Command(BaseCommand):
    help = ('Carga docs/carga_final/productos_a_cargar.csv (lote de facturas '
            'de agosto 2026), derivando el precio de venta del costo.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--archivo', default=str(RUTA_DEFAULT),
            help='Ruta del CSV (default: docs/carga_final/productos_a_cargar.csv)')
        parser.add_argument(
            '--margen', type=str, default=None,
            help='Margen general en %% sobre el costo. Ej: --margen 40')
        parser.add_argument(
            '--margen-rubro', type=str, default='',
            help='Margen por rubro, pisa al general. Ej: ceramica=35,pastina=60')
        parser.add_argument(
            '--redondeo', type=int, default=REDONDEO_DEFAULT,
            help=f'Redondea el precio de venta hacia arriba al múltiplo indicado '
                 f'(default {REDONDEO_DEFAULT}; 0 = sin redondeo)')
        parser.add_argument(
            '--incluir-dudosos', action='store_true',
            help='Carga también las filas con decisiones de negocio abiertas')
        parser.add_argument(
            '--sin-stock', action='store_true',
            help='Solo el catálogo: no registra ningún movimiento de stock')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra qué haría sin escribir nada en la base')

    # ── precio ────────────────────────────────────────────────────────────────

    def _precio_venta(self, costo, rubro):
        margen = self.margenes_rubro.get(rubro, self.margen_general)
        precio = costo * (Decimal('100') + margen) / Decimal('100')
        if self.redondeo > 0:
            paso = Decimal(self.redondeo)
            precio = (precio / paso).to_integral_value(rounding='ROUND_CEILING') * paso
        return precio.quantize(Decimal('1'))

    # ── handle ────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        ruta = Path(options['archivo'])
        if not ruta.exists():
            raise CommandError(f'No se encontró el archivo {ruta}')

        self.margenes_rubro = _parsear_margenes(options['margen_rubro'])
        self.margen_general = _dec(options['margen'])
        self.redondeo = max(0, options['redondeo'])

        if self.margen_general is None and not self.margenes_rubro:
            raise CommandError(
                'Falta el margen de venta. El CSV solo trae precios de COSTO y '
                'Producto.precio_base es obligatorio.\n'
                '  Margen parejo:   --margen 40\n'
                '  Por rubro:       --margen 40 --margen-rubro ceramica=35,pastina=60\n'
                'Ver docs/carga_final/pendientes_verificacion.md §4.')

        if self.margen_general is None:
            self.margen_general = Decimal('0')

        dry = options['dry_run']
        sin_stock_global = options['sin_stock']

        usuario = None
        if not sin_stock_global:
            usuario = Usuario.objects.filter(rol=Usuario.ROL_ADMIN, activo=True).first()
            if not usuario:
                raise CommandError(
                    'No hay ningún usuario admin activo para firmar el movimiento de '
                    'stock inicial. Crear uno con createsuperuser, o correr con '
                    '--sin-stock para cargar solo el catálogo.')

        with open(ruta, encoding='utf-8-sig') as f:
            filas = list(csv.DictReader(f, delimiter=';'))

        if not filas:
            raise CommandError(f'{ruta} no tiene filas.')

        # El --dry-run recorre exactamente el mismo camino que la carga real y
        # deshace todo al final. Así valida de verdad (full_clean, unicidad de
        # SKU, movimientos de stock) en vez de adivinar, y cuenta bien los
        # productos que se repiten entre filas del propio lote.
        self._reset_contadores()
        try:
            with transaction.atomic():
                self._procesar(filas, usuario=usuario,
                               sin_stock=sin_stock_global,
                               incluir_dudosos=options['incluir_dudosos'])
                if dry:
                    raise _Rollback
        except _Rollback:
            pass

        self._resumen(dry=dry, sin_stock_global=sin_stock_global)

    # ── contadores ────────────────────────────────────────────────────────────

    def _reset_contadores(self):
        self.productos_nuevos = 0
        self.variantes_nuevas = 0
        self.ya_existian = 0
        self.salteadas = 0
        self.con_error = 0
        self.sin_stock_marcadas = []
        self.dudosas = []
        self.costos_distintos = []
        self.ajustes = []

    # ── adaptar la fila a lo que valida el modelo ─────────────────────────────

    def _normalizar_medidas(self, variante, nombre, origen):
        """
        El CSV describe la factura; Variante.clean() es más estricto. Las dos
        diferencias reales del lote se resuelven acá, avisando, en vez de
        perder la fila.
        """
        # 1. Una sola dimensión. Pasa en los conjuntos de baño, donde el
        #    "65cm" de la factura es el ancho del mueble, no una pieza de dos
        #    lados. El dato ya está en el nombre del producto; la medida
        #    suelta se descarta porque el modelo exige largo y ancho juntos.
        if bool(variante.largo_cm) != bool(variante.ancho_cm):
            suelta = variante.largo_cm or variante.ancho_cm
            variante.largo_cm = variante.ancho_cm = None
            self.ajustes.append(
                f'{nombre}: venía una sola medida ({suelta} cm) y el modelo pide '
                f'largo y ancho juntos — se cargó sin dimensiones ({origen})')

        # 2. m2_por_caja del fabricante contra el cálculo geométrico. El
        #    README del lote verificó m2_por_caja contra las cantidades
        #    facturadas, así que ese es el dato bueno: se conserva y se suelta
        #    piezas_por_caja, que es el que no cierra.
        if (variante.largo_cm and variante.ancho_cm
                and variante.piezas_por_caja and variante.m2_por_caja):
            calculado = (float(variante.largo_cm) / 100
                         * float(variante.ancho_cm) / 100
                         * variante.piezas_por_caja)
            if abs(float(variante.m2_por_caja) - calculado) > 0.05:
                piezas = variante.piezas_por_caja
                variante.piezas_por_caja = None
                self.ajustes.append(
                    f'{nombre}: {variante.m2_por_caja} m²/caja no cierra con '
                    f'{piezas} piezas de {variante.largo_cm}×{variante.ancho_cm} '
                    f'({calculado:.4f} m²) — se conservó el m²/caja de la factura '
                    f'y se dejó las piezas por caja en blanco ({origen})')

    # ── recorrido del CSV ─────────────────────────────────────────────────────

    def _procesar(self, filas, *, usuario, sin_stock, incluir_dudosos):
        for n, fila in enumerate(filas, start=2):   # 2 = primera fila de datos
            origen = (f'pág. {fila.get("pagina", "?")} · '
                      f'{(fila.get("cod_proveedor") or "s/cód").strip()}')
            nombre = (fila.get('nombre_producto') or '').strip()
            color = (fila.get('color') or '').strip()
            obs = fila.get('observaciones') or ''

            if not nombre:
                self.stderr.write(self.style.ERROR(
                    f'  ! línea {n} sin nombre_producto — se saltea ({origen})'))
                self.con_error += 1
                continue

            if RE_DUDOSA.search(obs) and not incluir_dudosos:
                self.stdout.write(self.style.WARNING(
                    f'  ? decisión pendiente, se saltea: {nombre} ({origen})'))
                self.dudosas.append(f'{nombre} — {origen}')
                self.salteadas += 1
                continue

            costo = _dec(fila.get('costo_unitario_gs'))
            if costo is None or costo <= 0:
                self.stderr.write(self.style.ERROR(
                    f'  ! línea {n} sin costo_unitario_gs — se saltea: {nombre}'))
                self.con_error += 1
                continue

            rubro = (fila.get('categoria_sugerida') or 'otro').strip()
            if rubro not in NOMBRE_CATEGORIA:
                self.stderr.write(self.style.ERROR(
                    f'  ! línea {n} categoría desconocida {rubro!r} — se saltea: {nombre}'))
                self.con_error += 1
                continue

            precio_base = self._precio_venta(costo, rubro)

            # Cantidad a dar de alta. Las filas marcadas «no cargar al stock»
            # (ROTO, devolución) entran al catálogo pero sin mercadería.
            marcada_sin_stock = bool(RE_SIN_STOCK.search(obs))
            cantidad = Decimal('0') if marcada_sin_stock else (
                _dec(fila.get('cantidad_factura')) or Decimal('0'))
            if marcada_sin_stock:
                self.sin_stock_marcadas.append(f'{nombre} — {origen}')

            existente = Variante.objects.filter(
                producto__nombre=nombre, color=color).first()
            if existente:
                self.stdout.write(f'  = ya existe: {nombre} [{color or "sin color"}] '
                                  f'— SKU {existente.sku}')
                self.ya_existian += 1
                continue

            producto_previo = Producto.objects.filter(nombre=nombre).first()
            if (producto_previo and producto_previo.precio_costo is not None
                    and producto_previo.precio_costo != costo):
                self.costos_distintos.append(
                    f'{nombre}: ya cargado a {producto_previo.precio_costo:,.0f} Gs, '
                    f'esta fila dice {costo:,.0f} Gs ({origen})')

            try:
                creo_producto = self._cargar_fila(
                    fila, nombre=nombre, color=color, rubro=rubro,
                    costo=costo, precio_base=precio_base, cantidad=cantidad,
                    usuario=usuario, sin_stock=sin_stock, origen=origen)
            except ValidationError as e:
                detalle = '; '.join(
                    f'{campo}: {" ".join(msgs)}'
                    for campo, msgs in e.message_dict.items()
                ) if hasattr(e, 'message_dict') else '; '.join(e.messages)
                self.stderr.write(self.style.ERROR(
                    f'  ! línea {n} rechazada por validación — {nombre}: {detalle}'))
                self.con_error += 1
                continue

            self.variantes_nuevas += 1
            if creo_producto:
                self.productos_nuevos += 1

    # ── una fila ──────────────────────────────────────────────────────────────

    @transaction.atomic
    def _cargar_fila(self, fila, *, nombre, color, rubro, costo, precio_base,
                     cantidad, usuario, sin_stock, origen):
        categoria, _ = Categoria.objects.get_or_create(
            tipo=rubro,
            defaults={'nombre': NOMBRE_CATEGORIA.get(rubro, rubro.title())},
        )

        marca = None
        nombre_marca = (fila.get('marca') or '').strip()
        if nombre_marca:
            marca, _ = Marca.objects.get_or_create(nombre=nombre_marca)

        trazabilidad = (
            f'Lote agosto 2026 — pág. {fila.get("pagina", "?")} · '
            f'{(fila.get("proveedor") or "").strip()} · '
            f'factura {(fila.get("factura") or "").strip()} '
            f'({(fila.get("fecha") or "").strip()}) · '
            f'código proveedor {(fila.get("cod_proveedor") or "s/cód").strip()} · '
            f'"{(fila.get("descripcion_factura") or "").strip()}"'
        )
        observaciones = (fila.get('observaciones') or '').strip()
        if observaciones:
            trazabilidad += f'\n{observaciones}'

        producto = Producto.objects.filter(nombre=nombre).first()
        creo_producto = producto is None
        if creo_producto:
            producto = Producto(
                nombre=nombre,
                categoria=categoria,
                marca=marca,
                precio_base=precio_base,
                precio_costo=costo,
                unidad_venta=(fila.get('unidad_venta') or '').strip() or Producto.UNIDAD_PIEZA,
                notas_internas=trazabilidad,
            )
            producto.full_clean(exclude=['codigo'])
            producto.save()

        variante = Variante(
            producto=producto,
            color=color,
            largo_cm=_dec(fila.get('largo_cm')),
            ancho_cm=_dec(fila.get('ancho_cm')),
            m2_por_caja=_dec(fila.get('m2_por_caja')),
            piezas_por_caja=_entero(fila.get('piezas_por_caja')),
        )
        # Atributos anotados en observaciones ("tipo_cisterna=alta"): el
        # frontend los usa para filtrar sanitarios y grifería.
        for campo, valor in RE_ATRIBUTO.findall(observaciones):
            setattr(variante, campo, valor)

        self._normalizar_medidas(variante, nombre, origen)
        variante.full_clean(exclude=['sku'])
        variante.save()

        if not sin_stock and cantidad > 0:
            stock = Stock.objects.get(variante=variante)
            stock.registrar_movimiento(
                tipo=MovimientoStock.TIPO_ENTRADA,
                cantidad=cantidad,
                usuario=usuario,
                referencia_tipo='carga_lote_agosto_2026',
                observaciones=(
                    f'Carga del lote de facturas de agosto 2026 — '
                    f'factura {(fila.get("factura") or "").strip()} — {origen}'),
            )

        self.stdout.write(self.style.SUCCESS(
            f'  + {producto.codigo} / {variante.sku} — {nombre} '
            f'[{color or "sin color"}] — venta {precio_base:,.0f} Gs — '
            f'stock {cantidad}'))
        return creo_producto

    # ── resumen ───────────────────────────────────────────────────────────────

    def _resumen(self, *, dry, sin_stock_global):
        productos_nuevos = self.productos_nuevos
        variantes_nuevas = self.variantes_nuevas
        ya_existian = self.ya_existian
        salteadas = self.salteadas
        con_error = self.con_error
        sin_stock_marcadas = self.sin_stock_marcadas
        dudosas = self.dudosas
        costos_distintos = self.costos_distintos

        self.stdout.write('')
        titulo = 'DRY-RUN — no se escribió nada' if dry else 'Carga terminada'
        self.stdout.write(self.style.MIGRATE_HEADING(titulo))
        verbo = 'se crearían' if dry else 'creadas'
        self.stdout.write(
            f'  {variantes_nuevas} variantes {verbo} '
            f'({productos_nuevos} productos nuevos), '
            f'{ya_existian} ya existían, {salteadas} salteadas, '
            f'{con_error} con error.')

        if sin_stock_global:
            self.stdout.write(self.style.WARNING(
                '  --sin-stock: no se registró ningún movimiento de inventario.'))

        if sin_stock_marcadas:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'  {len(sin_stock_marcadas)} al catálogo con stock 0 '
                f'(marcadas ROTO o devolución en la factura):'))
            for linea in sin_stock_marcadas:
                self.stdout.write(f'    · {linea}')

        if dudosas:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'  {len(dudosas)} salteadas por decisión de negocio pendiente '
                f'(--incluir-dudosos para cargarlas):'))
            for linea in dudosas:
                self.stdout.write(f'    · {linea}')

        if self.ajustes:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'  {len(self.ajustes)} filas se ajustaron para poder cargarlas:'))
            for linea in self.ajustes:
                self.stdout.write(f'    · {linea}')

        if costos_distintos:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'  {len(costos_distintos)} filas comparten producto con otro costo '
                f'(quedó el de la primera fila; revisar el precio a mano):'))
            for linea in costos_distintos:
                self.stdout.write(f'    · {linea}')

        if not dry:
            self.stdout.write('')
            self.stdout.write(
                '  Recordatorios: los precios de venta salen del margen aplicado sobre\n'
                '  el costo — repasarlos en la pantalla de Productos antes de vender.\n'
                '  Las fotos no se vinculan acá: subirlas por variante desde esa misma\n'
                '  pantalla, usando el código de proveedor guardado en "notas internas".')
