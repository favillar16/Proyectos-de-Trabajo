"""
App: productos
Modelos para catálogo de productos con variantes múltiples e imágenes.
Cubre: pisos, porcelanatos, cerámicas, sanitarios, accesorios, cocina.

Mejoras v2:
- Índices de BD en campos de búsqueda frecuente
- Slug con fallback numérico garantizado único
- SKU con fallback numérico garantizado único
- unique_together en Variante para evitar duplicados lógicos
- Validación cruzada largo/ancho y m2_por_caja
- m2_por_caja_calculado automático desde dimensiones
- margen_bruto en Producto
- peso_kg_caja y UNIDAD_ML agregados
- imagen_principal sin query extra cuando se usa prefetch_related
"""
import os
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from apps.sync.mixins import ModeloSincronizable


# ─── Helpers de paths ─────────────────────────────────────────────────────────

def producto_imagen_path(instance, filename):
    """media/productos/<codigo>/<filename>"""
    nombre_base = slugify(instance.producto.codigo)
    return f'productos/{nombre_base}/{filename}'


def variante_imagen_path(instance, filename):
    """media/productos/<codigo>/variantes/<sku>/<filename>"""
    nombre_base = slugify(instance.variante.producto.codigo)
    sku = slugify(instance.variante.sku or 'sin-sku')
    return f'productos/{nombre_base}/variantes/{sku}/{filename}'


# ─── Tablas de soporte ────────────────────────────────────────────────────────

class Categoria(ModeloSincronizable):
    TIPOS = [
        ('piso',             'Pisos'),
        ('porcelanato',      'Porcelanatos'),
        ('ceramica',         'Cerámicas'),
        ('sanitario',        'Sanitarios'),
        ('accesorio_bano',   'Accesorios de Baño'),
        ('cocina',           'Artículos de Cocina'),
        # ── Subtipos de sanitarios/accesorios (docs/Listado de Productos.docx) ──
        ('bacha',            'Bachas'),
        ('pileta_cocina',    'Piletas para cocina'),
        ('pileta_ropa',      'Piletas para ropa'),
        ('griferia',         'Grifería'),
        ('ducha',            'Duchas'),
        ('inodoro',          'Inodoros'),
        ('migitorio',        'Migitorios'),
        ('bide',             'Bidés'),
        ('ducha_higienica',  'Duchas higiénicas'),
        ('cisterna',         'Cisternas'),
        ('tapa_inodoro',     'Tapas para inodoro'),
        ('nicho_bano',       'Nichos para baño'),
        ('espejo',           'Espejos'),
        ('adhesivo',         'Adhesivos'),
        ('pastina',          'Pastinas'),
        ('plomeria',         'Plomería'),
        ('tira_fondo',       'Tiras de fondo con tarugo'),
        ('otro',             'Otro'),
    ]

    nombre      = models.CharField(max_length=100)
    tipo        = models.CharField(max_length=30, choices=TIPOS, default='otro', db_index=True)
    descripcion = models.TextField(blank=True)
    activa      = models.BooleanField(default=True, db_index=True)
    orden       = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table            = 'categorias'
        ordering            = ['orden', 'nombre']
        verbose_name        = 'Categoría'
        verbose_name_plural = 'Categorías'
        indexes = [
            models.Index(fields=['tipo', 'activa'], name='idx_categoria_tipo_activa'),
        ]

    def __str__(self):
        return f'{self.nombre} ({self.get_tipo_display()})'

    def clean(self):
        self.nombre = self.nombre.strip()
        if not self.nombre:
            raise ValidationError({'nombre': 'El nombre no puede estar vacío.'})


class Marca(ModeloSincronizable):
    nombre      = models.CharField(max_length=100, unique=True)
    pais_origen = models.CharField(max_length=60, blank=True)
    activa      = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table            = 'marcas'
        ordering            = ['nombre']
        verbose_name        = 'Marca'
        verbose_name_plural = 'Marcas'

    def __str__(self):
        return self.nombre

    def clean(self):
        self.nombre = self.nombre.strip()


class Acabado(ModeloSincronizable):
    """Mate, brillante, antideslizante, natural, pulido, rectificado, rústico..."""
    nombre      = models.CharField(max_length=80, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table            = 'acabados'
        ordering            = ['nombre']
        verbose_name        = 'Acabado'
        verbose_name_plural = 'Acabados'

    def __str__(self):
        return self.nombre


# ─── Producto ─────────────────────────────────────────────────────────────────

class Producto(ModeloSincronizable):
    UNIDAD_M2    = 'm2'
    UNIDAD_PIEZA = 'pieza'
    UNIDAD_JUEGO = 'juego'
    UNIDAD_CAJA  = 'caja'
    UNIDAD_ML    = 'ml'       # metros lineales: zócalos, molduras

    UNIDADES = [
        (UNIDAD_M2,    'Metro cuadrado'),
        (UNIDAD_PIEZA, 'Pieza'),
        (UNIDAD_JUEGO, 'Juego'),
        (UNIDAD_CAJA,  'Caja'),
        (UNIDAD_ML,    'Metro lineal'),
    ]

    # ── Identificación ────────────────────────────────────────
    codigo      = models.CharField(max_length=50, unique=True, db_index=True)
    nombre      = models.CharField(max_length=200, db_index=True)
    descripcion = models.TextField(blank=True)
    slug        = models.SlugField(max_length=240, unique=True, blank=True, editable=False)

    # ── Clasificación ─────────────────────────────────────────
    categoria         = models.ForeignKey(
        Categoria, on_delete=models.PROTECT,
        related_name='productos', db_index=True
    )
    marca             = models.ForeignKey(
        Marca, on_delete=models.PROTECT,
        related_name='productos', null=True, blank=True, db_index=True
    )

    # ── Precios ───────────────────────────────────────────────
    precio_base = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Precio de venta base en Gs. (puede diferir por variante)'
    )
    precio_costo = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        help_text='Precio de costo — solo visible para administradores'
    )
    unidad_venta = models.CharField(max_length=10, choices=UNIDADES, default=UNIDAD_M2)

    # ── IVA ───────────────────────────────────────────────────
    # El SIFEN exige la afectación y la tasa de IVA por ítem, no un IVA
    # global del comprobante. Hasta ahora la factura calculaba el IVA como
    # total/11 asumiendo 10% para todo (apps/caja/views.py), lo cual era
    # correcto en la práctica porque el rubro entero va al 10%, pero no
    # sirve para emitir un DE ni para vender algo exento.
    #
    # Los precios que carga la encargada son SIEMPRE con IVA incluido, que
    # es como se muestran en el mostrador; el desglose se hace al facturar
    # (apps/facturacion/codigos.py, desglosar_iva).
    IVA_10 = 10
    IVA_5 = 5
    IVA_EXENTO = 0
    TASAS_IVA = [
        (IVA_10,     'Gravado 10%'),
        (IVA_5,      'Gravado 5%'),
        (IVA_EXENTO, 'Exento'),
    ]
    tasa_iva = models.PositiveSmallIntegerField(
        choices=TASAS_IVA, default=IVA_10,
        help_text='Tasa de IVA incluida en el precio. El rubro (pisos, '
                  'cerámicos, sanitarios) va al 10%.'
    )

    # ── Showroom ──────────────────────────────────────────────
    destacado        = models.BooleanField(
        default=False, db_index=True,
        help_text='Aparece primero en el showroom y catálogo'
    )
    activo           = models.BooleanField(default=True, db_index=True)
    visible_showroom = models.BooleanField(
        default=True,
        help_text='Visible para vendedores en el showroom de tablets'
    )
    notas_internas   = models.TextField(
        blank=True,
        help_text='Solo visible para el personal, no aparece en el showroom'
    )

    # ── Timestamps ────────────────────────────────────────────
    fecha_creacion      = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'productos'
        ordering            = ['-destacado', 'categoria', 'nombre']
        verbose_name        = 'Producto'
        verbose_name_plural = 'Productos'
        indexes = [
            models.Index(fields=['activo', 'visible_showroom'], name='idx_producto_showroom'),
            models.Index(fields=['categoria', 'activo'],        name='idx_producto_categoria'),
            models.Index(fields=['marca', 'activo'],            name='idx_producto_marca'),
            models.Index(fields=['-destacado', 'nombre'],       name='idx_producto_orden'),
        ]

    # Prefijos de código por tipo de categoría (3 letras, legibles)
    PREFIJOS_TIPO = {
        'piso':            'PIS',
        'porcelanato':     'POR',
        'ceramica':        'CER',
        'sanitario':       'SAN',
        'accesorio_bano':  'ACC',
        'cocina':          'COC',
        'bacha':           'BAC',
        'pileta_cocina':   'PIC',
        'pileta_ropa':     'PIR',
        'griferia':        'GRI',
        'ducha':           'DUC',
        'inodoro':         'INO',
        'migitorio':       'MIG',
        'bide':            'BID',
        'ducha_higienica': 'DUH',
        'cisterna':        'CIS',
        'tapa_inodoro':    'TAP',
        'nicho_bano':      'NIC',
        'espejo':          'ESP',
        'adhesivo':        'ADH',
        'pastina':         'PAS',
        'plomeria':        'PLO',
        'tira_fondo':      'TIR',
        'otro':            'GEN',
    }
    SUFIJO_CODIGO = 'OG'   # identifica a Oga Porã

    def _prefijo_codigo(self):
        """
        Prefijo de 3 letras. Sale del tipo de la categoría (normalizado);
        si no hubiera, usa las primeras letras del nombre como respaldo.
        """
        if self.categoria_id:
            tipo = self.categoria.tipo
            prefijo = self.PREFIJOS_TIPO.get(tipo)
            if prefijo:
                return prefijo
        # Respaldo: primeras 3 letras alfabéticas del nombre
        letras = ''.join(c for c in (self.nombre or '') if c.isalpha())
        return (letras[:3].upper() or 'GEN').ljust(3, 'X')

    def _generar_codigo(self):
        """
        Genera un código único con formato PREFIJO-NNN-OG.
        El correlativo es por prefijo (POR-001, POR-002...).
        Maneja huecos y concurrencia: busca el mayor correlativo existente
        para ese prefijo y suma 1; reintenta si hubiera colisión.
        """
        import re
        prefijo = self._prefijo_codigo()
        patron = re.compile(rf'^{re.escape(prefijo)}-(\d+)-{self.SUFIJO_CODIGO}$')

        maximo = 0
        for cod in Producto.objects.filter(
            codigo__startswith=f'{prefijo}-',
            codigo__endswith=f'-{self.SUFIJO_CODIGO}',
        ).values_list('codigo', flat=True):
            m = patron.match(cod)
            if m:
                maximo = max(maximo, int(m.group(1)))

        # Buscar el primer correlativo libre a partir de maximo+1
        n = maximo + 1
        while Producto.objects.filter(
            codigo=f'{prefijo}-{str(n).zfill(3)}-{self.SUFIJO_CODIGO}'
        ).exists():
            n += 1
        return f'{prefijo}-{str(n).zfill(3)}-{self.SUFIJO_CODIGO}'

    def _generar_slug(self):
        base = slugify(f'{self.codigo}-{self.nombre}')[:230]
        slug, n = base, 1
        qs = Producto.objects.exclude(pk=self.pk)
        while qs.filter(slug=slug).exists():
            slug = f'{base}-{n}'
            n += 1
        return slug

    def save(self, *args, **kwargs):
        from django.db import IntegrityError, transaction
        self.nombre = (self.nombre or '').strip()

        # Generar código automáticamente si no fue provisto
        if not (self.codigo or '').strip():
            # Reintentar ante colisión por concurrencia (dos altas simultáneas)
            for _ in range(5):
                self.codigo = self._generar_codigo()
                if not self.slug:
                    self.slug = self._generar_slug()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.codigo = ''   # forzar regeneración en el siguiente intento
                    continue
            # Último intento sin capturar (que propague el error real si persiste)
            self.codigo = self._generar_codigo()

        self.codigo = self.codigo.strip().upper()
        if not self.slug:
            self.slug = self._generar_slug()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'[{self.codigo}] {self.nombre}'

    @property
    def imagen_principal(self):
        """Sin query extra cuando las imágenes ya fueron prefetched."""
        cache = getattr(self, '_prefetched_objects_cache', {})
        if 'imagenes' in cache:
            imgs = cache['imagenes']
            return next((i for i in imgs if i.es_principal), None) or (imgs[0] if imgs else None)
        return self.imagenes.filter(es_principal=True).first() or self.imagenes.first()

    @property
    def stock_total(self):
        """Suma del stock real de todas las variantes activas."""
        from apps.inventario.models import Stock
        resultado = Stock.objects.filter(
            variante__producto=self,
            variante__activa=True
        ).aggregate(total=models.Sum('cantidad'))
        return resultado['total'] or 0

    @property
    def margen_bruto(self):
        """Margen bruto en % si existe precio de costo."""
        if self.precio_costo and self.precio_costo > 0:
            return round(
                float((self.precio_base - self.precio_costo) / self.precio_base) * 100, 2
            )
        return None


# ─── Variante ─────────────────────────────────────────────────────────────────

class Variante(ModeloSincronizable):
    """
    Unidad mínima vendible. Cada variante es una combinación única de
    atributos de un producto y tiene su propio stock.

    Ej: Porcelanato Roma — 60×60 cm — Beige — Mate  →  SKU: POR-001-60x60-BEIGE-MATE
    """

    producto = models.ForeignKey(
        Producto, on_delete=models.CASCADE,
        related_name='variantes', db_index=True
    )

    # ── Atributos diferenciadores ─────────────────────────────
    color   = models.CharField(
        max_length=80, blank=True,
        help_text='Ej: Beige, Gris Cemento, Blanco Nieve'
    )
    calidad = models.CharField(
        max_length=20, blank=True,
        help_text='Calidad/clase comercial. Ej: TP.A, Primera, Comercial'
    )
    acabado = models.ForeignKey(
        Acabado, on_delete=models.SET_NULL,
        null=True, blank=True, db_index=True
    )

    # ── Dimensiones ───────────────────────────────────────────
    largo_cm   = models.DecimalField(
        max_digits=7, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0.01)],
        help_text='Largo de la pieza en centímetros'
    )
    ancho_cm   = models.DecimalField(
        max_digits=7, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0.01)],
        help_text='Ancho de la pieza en centímetros'
    )
    espesor_mm = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0.01)],
        help_text='Espesor en milímetros'
    )

    # ── Rendimiento por caja ──────────────────────────────────
    piezas_por_caja = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Cantidad de piezas por caja o paquete'
    )
    m2_por_caja = models.DecimalField(
        max_digits=7, decimal_places=4,
        null=True, blank=True,
        help_text='M² que cubre una caja completa (se calcula si se dejan las dimensiones)'
    )
    peso_kg_caja = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text='Peso de la caja en kg'
    )
    cajas_por_pallet = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Cantidad de cajas por pallet (para cargar stock en pallets)'
    )

    # ── Precio propio ─────────────────────────────────────────
    precio_diferencial = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text='Precio propio de esta variante. Si es nulo, hereda el precio base del producto.'
    )

    # ── Atributos específicos por tipo de producto ────────────
    # Solo aplican según la categoría (ver camposPorTipo.js en el frontend):
    # grifería usa tipo_grifo/posicion_grifo/montaje_grifo, duchas usa
    # tipo_ducha, inodoros usa tipo_cisterna. El resto de las categorías
    # los deja en blanco.
    TIPO_GRIFO_CHOICES = [('frio', 'Frío'), ('monocomando', 'Monocomando')]
    POSICION_GRIFO_CHOICES = [('alta', 'Alta'), ('baja', 'Baja')]
    MONTAJE_GRIFO_CHOICES = [('mesa', 'De mesa'), ('pared', 'De pared')]
    TIPO_DUCHA_CHOICES = [
        ('frio', 'Frío'), ('electrico', 'Eléctrico'), ('monocomando', 'Monocomando'),
    ]
    TIPO_CISTERNA_CHOICES = [('alta', 'Alta'), ('baja', 'Baja')]

    tipo_grifo     = models.CharField(max_length=20, choices=TIPO_GRIFO_CHOICES, blank=True)
    posicion_grifo = models.CharField(max_length=20, choices=POSICION_GRIFO_CHOICES, blank=True)
    montaje_grifo  = models.CharField(max_length=20, choices=MONTAJE_GRIFO_CHOICES, blank=True)
    tipo_ducha     = models.CharField(max_length=20, choices=TIPO_DUCHA_CHOICES, blank=True)
    tipo_cisterna  = models.CharField(max_length=20, choices=TIPO_CISTERNA_CHOICES, blank=True)

    # ── Identificación ────────────────────────────────────────
    sku    = models.CharField(max_length=100, unique=True, blank=True, db_index=True)
    # Código de barras que se lee con el lector (FTX LC123BH5). Es el de la caja
    # del fabricante (EAN-13 y similares) o, para la mercadería que viene sin
    # código, una etiqueta impresa por el negocio.
    #
    # Va en la variante y no en el producto porque la variante es la que tiene
    # caja física: el Roma Beige 60×60 y el Roma Gris 60×60 son dos cajas
    # distintas, con dos códigos distintos y dos stocks distintos.
    #
    # unique=True con null: dos variantes sin código no chocan entre sí (para la
    # base, cada vacío es distinto de los demás), pero un código cargado no se
    # puede repetir. Por eso el campo guarda NULL y no cadena vacía cuando no
    # hay código — ver save().
    codigo_barras = models.CharField(
        max_length=64, unique=True, null=True, blank=True, db_index=True,
        help_text='Código de barras de la caja. Se completa con el lector.'
    )
    activa = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table            = 'variantes'
        verbose_name        = 'Variante'
        verbose_name_plural = 'Variantes'
        unique_together = [
            # Previene registrar dos veces la misma combinación para el mismo producto
            ('producto', 'color', 'acabado', 'largo_cm', 'ancho_cm'),
        ]
        indexes = [
            models.Index(fields=['producto', 'activa'], name='idx_variante_producto'),
        ]

    def _generar_sku(self):
        partes = [self.producto.codigo]
        if self.largo_cm and self.ancho_cm:
            partes.append(f'{int(self.largo_cm)}x{int(self.ancho_cm)}')
        if self.color:
            partes.append(slugify(self.color)[:12].upper())
        if self.acabado:
            partes.append(slugify(self.acabado.nombre)[:8].upper())
        base = '-'.join(partes)[:90]
        sku, n = base, 1
        qs = Variante.objects.exclude(pk=self.pk)
        while qs.filter(sku=sku).exists():
            sku = f'{base}-{n}'
            n += 1
        return sku

    def save(self, *args, **kwargs):
        from django.db import IntegrityError, transaction

        # Sin código de barras se guarda NULL, nunca cadena vacía: si se
        # guardaran vacíos, la segunda variante sin código chocaría contra la
        # restricción de unicidad. La mayoría de los porcelanatos no traen
        # código de fábrica, así que ese es el caso normal, no el raro.
        if self.codigo_barras is not None:
            self.codigo_barras = self.codigo_barras.strip() or None

        if not self.sku:
            # Reintentar ante colisión por concurrencia (dos altas simultáneas
            # generando el mismo SKU base) — mismo patrón que Producto.save().
            for _ in range(5):
                self.sku = self._generar_sku()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.sku = ''   # forzar regeneración en el siguiente intento
                    continue
            # Último intento sin capturar (que propague el error real si persiste)
            self.sku = self._generar_sku()

        super().save(*args, **kwargs)

    def clean(self):
        # Largo y ancho deben ir juntos
        if bool(self.largo_cm) != bool(self.ancho_cm):
            raise ValidationError(
                'Debe indicar tanto el largo como el ancho, o dejar ambos en blanco.'
            )
        # Validar coherencia de m2_por_caja vs dimensiones
        if self.largo_cm and self.ancho_cm and self.piezas_por_caja and self.m2_por_caja:
            calculado = (float(self.largo_cm) / 100) * (float(self.ancho_cm) / 100) * self.piezas_por_caja
            if abs(float(self.m2_por_caja) - calculado) > 0.05:
                raise ValidationError({
                    'm2_por_caja': (
                        f'El valor ingresado ({self.m2_por_caja} m²) no coincide con el calculado '
                        f'({calculado:.4f} m²). Verificar dimensiones o piezas por caja.'
                    )
                })

    def __str__(self):
        partes = [self.producto.nombre]
        if self.largo_cm and self.ancho_cm:
            partes.append(f'{self.largo_cm:.0f}×{self.ancho_cm:.0f} cm')
        if self.color:
            partes.append(self.color)
        if self.acabado:
            partes.append(self.acabado.nombre)
        return ' — '.join(partes)

    @property
    def precio_venta(self):
        """Precio efectivo: propio si existe, si no hereda del producto."""
        return self.precio_diferencial \
               if self.precio_diferencial is not None \
               else self.producto.precio_base

    @property
    def dimension_display(self):
        """Ej: '60×60 cm'."""
        if self.largo_cm and self.ancho_cm:
            return f'{self.largo_cm:.0f}×{self.ancho_cm:.0f} cm'
        return ''

    @property
    def m2_por_caja_calculado(self):
        """M²/caja: usa el campo si existe, si no lo calcula desde dimensiones."""
        if self.m2_por_caja:
            return float(self.m2_por_caja)
        if self.largo_cm and self.ancho_cm and self.piezas_por_caja:
            return round(
                float(self.largo_cm / 100) * float(self.ancho_cm / 100) * self.piezas_por_caja, 4
            )
        return None

    def convertir_a_unidad_venta(self, cantidad, unidad='venta'):
        """
        Convierte una cantidad ingresada en 'venta' (m²/unidad tal cual),
        'caja' o 'pallet' a la unidad de venta de esta variante (m²
        normalmente). Único punto de conversión — lo usan tanto el ajuste
        manual de stock (apps.inventario) como la recepción de pedidos a
        proveedor (apps.costos), para no repetir la cuenta en dos lugares.
        Lanza ValueError con un mensaje legible si a la variante le faltan
        los datos necesarios para la conversión pedida.
        """
        from decimal import Decimal
        cantidad = Decimal(str(cantidad))
        if unidad == 'venta':
            return cantidad

        m2_caja = self.m2_por_caja_calculado
        if not m2_caja or m2_caja <= 0:
            raise ValueError('Esta variante no tiene m² por caja definido; no se puede cargar en cajas.')

        if unidad == 'caja':
            return (cantidad * Decimal(str(m2_caja))).quantize(Decimal('0.0001'))

        if unidad == 'pallet':
            if not self.cajas_por_pallet or self.cajas_por_pallet <= 0:
                raise ValueError('Esta variante no tiene cajas por pallet definidas; no se puede cargar en pallets.')
            cajas = cantidad * self.cajas_por_pallet
            return (cajas * Decimal(str(m2_caja))).quantize(Decimal('0.0001'))

        raise ValueError(f'Unidad de ingreso desconocida: {unidad}')

    @property
    def stock_actual(self):
        """Stock disponible (real - reservado)."""
        try:
            return float(self.stock.cantidad_disponible)
        except Exception:
            return 0.0

    @property
    def tiene_stock(self):
        try:
            return self.stock.cantidad_disponible > 0
        except Exception:
            return False


# ─── Imágenes ─────────────────────────────────────────────────────────────────

class ImagenProducto(ModeloSincronizable):
    """
    Imágenes del producto en general.
    Una sola puede marcarse como principal (aparece en el showroom).
    """
    producto     = models.ForeignKey(
        Producto, on_delete=models.CASCADE, related_name='imagenes'
    )
    imagen       = models.ImageField(
        upload_to=producto_imagen_path,
        help_text='Formatos: JPG, PNG, WEBP. Máximo 5 MB. Recomendado: 1200×1200 px.'
    )
    es_principal = models.BooleanField(
        default=False,
        help_text='Esta imagen se muestra en el showroom y listados'
    )
    titulo       = models.CharField(
        max_length=150, blank=True,
        help_text='Descripción breve de la imagen (texto alternativo)'
    )
    orden        = models.PositiveSmallIntegerField(
        default=0,
        help_text='Orden en la galería del producto (menor número = primero)'
    )
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'imagenes_producto'
        ordering            = ['-es_principal', 'orden']
        verbose_name        = 'Imagen de producto'
        verbose_name_plural = 'Imágenes de producto'
        indexes = [
            models.Index(fields=['producto', 'es_principal'], name='idx_img_prod_principal'),
        ]

    def save(self, *args, **kwargs):
        # Solo una imagen principal por producto
        if self.es_principal:
            ImagenProducto.objects.filter(
                producto=self.producto, es_principal=True
            ).exclude(pk=self.pk).update(es_principal=False)
        super().save(*args, **kwargs)

    def clean(self):
        if self.imagen and hasattr(self.imagen, 'size'):
            max_bytes = 5 * 1024 * 1024  # 5 MB
            if self.imagen.size > max_bytes:
                raise ValidationError(
                    f'La imagen supera el límite de 5 MB '
                    f'({self.imagen.size / 1024 / 1024:.1f} MB). '
                    f'Comprimirla antes de subir.'
                )

    def __str__(self):
        label = 'principal' if self.es_principal else f'#{self.orden}'
        return f'{self.producto.codigo} — imagen {label}'


class ImagenVariante(ModeloSincronizable):
    """
    Imagen específica de una variante.
    Muestra cómo se ve ese color o acabado en particular.
    """
    variante     = models.ForeignKey(
        Variante, on_delete=models.CASCADE, related_name='imagenes'
    )
    imagen       = models.ImageField(
        upload_to=variante_imagen_path,
        help_text='Imagen que muestra el color/acabado real de esta variante'
    )
    es_principal = models.BooleanField(default=False)
    orden        = models.PositiveSmallIntegerField(default=0)
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'imagenes_variante'
        ordering            = ['-es_principal', 'orden']
        verbose_name        = 'Imagen de variante'
        verbose_name_plural = 'Imágenes de variante'
        indexes = [
            models.Index(fields=['variante', 'es_principal'], name='idx_img_var_principal'),
        ]

    def save(self, *args, **kwargs):
        if self.es_principal:
            ImagenVariante.objects.filter(
                variante=self.variante, es_principal=True
            ).exclude(pk=self.pk).update(es_principal=False)
        super().save(*args, **kwargs)

    def __str__(self):
        label = 'principal' if self.es_principal else f'#{self.orden}'
        return f'{self.variante.sku} — imagen {label}'
