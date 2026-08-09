"""
cargar_demo.py
Script de carga de datos de demostración para la presentación a propietarios.

Ejecutar desde la carpeta backend con el entorno virtual activado:
    python cargar_demo.py

Qué crea:
  - 4 usuarios (admin, vendedor, cajero, depósito)
  - 24 productos representativos del rubro
  - Variantes con dimensiones, colores y acabados reales
  - Stock variado (disponible, bajo, sin stock) para mostrar alertas
  - Sin imágenes (se agregan manualmente o en el siguiente paso)

Nota: se puede ejecutar múltiples veces sin duplicar datos (usa get_or_create).
"""

import os
import sys
import django
from decimal import Decimal

# ── Setup de Django ────────────────────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.productos.models import (
    Categoria, Marca, Acabado,
    Producto, Variante,
)
from apps.inventario.models import Stock

Usuario = get_user_model()

print('\n' + '='*55)
print('  Cargando datos de demostración...')
print('='*55 + '\n')

# ── Usuarios de demo ───────────────────────────────────────────────────────────
print('▶ Creando usuarios...')

usuarios_demo = [
    {'username': 'admin',    'password': 'demo2025', 'nombre_completo': 'Administrador',     'rol': 'admin',    'is_staff': True},
    {'username': 'vendedor', 'password': 'demo2025', 'nombre_completo': 'María González',    'rol': 'vendedor', 'is_staff': False},
    {'username': 'cajero',   'password': 'demo2025', 'nombre_completo': 'Carlos Benítez',    'rol': 'cajero',   'is_staff': False},
    {'username': 'deposito', 'password': 'demo2025', 'nombre_completo': 'Roberto Villalba',  'rol': 'deposito', 'is_staff': False},
]

for u in usuarios_demo:
    usuario, creado = Usuario.objects.get_or_create(username=u['username'])
    if creado or not usuario.has_usable_password():
        usuario.set_password(u['password'])
    usuario.nombre_completo = u['nombre_completo']
    usuario.rol             = u['rol']
    usuario.is_staff        = u['is_staff']
    usuario.is_superuser    = u['rol'] == 'admin'
    usuario.save()
    estado = '  ✓ creado' if creado else '  · ya existe'
    print(f'{estado}: {u["username"]} ({u["nombre_completo"]})')

# ── Obtener catálogos cargados por initial_data ────────────────────────────────
cat  = {c.tipo: c for c in Categoria.objects.all()}
marc = {m.nombre: m for m in Marca.objects.all()}
acab = {a.nombre: a for a in Acabado.objects.all()}

# Verificar que existan
if not cat:
    print('\n  ERROR: Primero ejecutar: python manage.py loaddata initial_data.json\n')
    sys.exit(1)

admin_user = Usuario.objects.get(username='admin')

# ── Función helper ─────────────────────────────────────────────────────────────
def crear_producto_con_variantes(data):
    """Crea o actualiza un producto con sus variantes y stock."""

    producto, _ = Producto.objects.update_or_create(
        codigo=data['codigo'],
        defaults={
            'nombre':          data['nombre'],
            'descripcion':     data.get('descripcion', ''),
            'categoria':       cat[data['categoria']],
            'marca':           marc.get(data.get('marca', ''), None),
            'precio_base':     Decimal(str(data['precio_base'])),
            'precio_costo':    Decimal(str(data.get('precio_costo', 0))) if data.get('precio_costo') else None,
            'unidad_venta':    data.get('unidad', 'm2'),
            'destacado':       data.get('destacado', False),
            'visible_showroom':True,
            'activo':          True,
            'notas_internas':  data.get('notas', ''),
        }
    )

    # Variantes
    for v in data.get('variantes', []):
        acabado_obj = acab.get(v.get('acabado', ''), None)
        variante, creada = Variante.objects.get_or_create(
            producto=producto,
            color=v.get('color', ''),
            acabado=acabado_obj,
            largo_cm=Decimal(str(v['largo'])) if v.get('largo') else None,
            ancho_cm=Decimal(str(v['ancho'])) if v.get('ancho') else None,
        )
        if v.get('espesor'):
            variante.espesor_mm = Decimal(str(v['espesor']))
        if v.get('piezas'):
            variante.piezas_por_caja = v['piezas']
        if v.get('m2_caja'):
            variante.m2_por_caja = Decimal(str(v['m2_caja']))
        if v.get('precio_propio'):
            variante.precio_diferencial = Decimal(str(v['precio_propio']))
        variante.activa = True
        variante.save()

        # Stock
        stock_qty = Decimal(str(v.get('stock', 0)))
        stock_min = Decimal(str(v.get('stock_min', 5)))
        ubic      = v.get('ubicacion', '')

        stock_obj, _ = Stock.objects.get_or_create(variante=variante)
        stock_obj.cantidad      = stock_qty
        stock_obj.stock_minimo  = stock_min
        stock_obj.ubicacion     = ubic
        stock_obj.save()

    return producto


# ── Productos de demostración ──────────────────────────────────────────────────
print('\n▶ Creando productos...\n')

PRODUCTOS_DEMO = [

    # ── PORCELANATOS (destacados) ──────────────────────────────────────────────
    {
        'codigo': 'POR-001', 'destacado': True,
        'nombre': 'Porcelanato Roma',
        'descripcion': 'Porcelanato rectificado de alta resistencia, ideal para ambientes de alto tráfico. Efecto piedra natural con acabado mate de fácil mantenimiento.',
        'categoria': 'porcelanato', 'marca': 'Porcelanosa',
        'precio_base': 185000, 'precio_costo': 120000, 'unidad': 'm2',
        'instalacion': ['Piso', 'Pared', 'Interior'],
        'notas': 'Producto estrella del showroom. Pedir con 2 semanas de anticipación.',
        'variantes': [
            {'color': 'Beige',       'acabado': 'Mate',        'largo': 60, 'ancho': 60, 'espesor': 9.5, 'piezas': 4, 'm2_caja': 1.44, 'stock': 48.6,  'stock_min': 10, 'ubicacion': 'Pasillo A - Estante 1'},
            {'color': 'Gris Claro',  'acabado': 'Mate',        'largo': 60, 'ancho': 60, 'espesor': 9.5, 'piezas': 4, 'm2_caja': 1.44, 'stock': 28.8,  'stock_min': 10, 'ubicacion': 'Pasillo A - Estante 2'},
            {'color': 'Blanco Nieve','acabado': 'Rectificado',  'largo': 60, 'ancho': 60, 'espesor': 9.5, 'piezas': 4, 'm2_caja': 1.44, 'stock': 4.3,   'stock_min': 10, 'ubicacion': 'Pasillo A - Estante 3'},
            {'color': 'Beige',       'acabado': 'Mate',        'largo': 30, 'ancho': 60, 'espesor': 9,   'piezas': 8, 'm2_caja': 1.44, 'stock': 0,     'stock_min': 8,  'ubicacion': 'Pasillo A - Estante 4'},
        ]
    },
    {
        'codigo': 'POR-002', 'destacado': True,
        'nombre': 'Porcelanato Cemento Industrial',
        'descripcion': 'Efecto cemento pulido de tendencia contemporánea. Superficies lisas y tonos neutros que aportan amplitud visual a cualquier espacio.',
        'categoria': 'porcelanato', 'marca': 'Gresia',
        'precio_base': 210000, 'precio_costo': 138000, 'unidad': 'm2',
        'instalacion': ['Piso', 'Pared'],
        'variantes': [
            {'color': 'Gris Cemento', 'acabado': 'Mate',    'largo': 60, 'ancho': 60, 'espesor': 10, 'piezas': 4, 'm2_caja': 1.44, 'stock': 36.0, 'stock_min': 8, 'ubicacion': 'Pasillo A - Estante 5'},
            {'color': 'Gris Oscuro',  'acabado': 'Mate',    'largo': 60, 'ancho': 60, 'espesor': 10, 'piezas': 4, 'm2_caja': 1.44, 'stock': 14.4, 'stock_min': 8, 'ubicacion': 'Pasillo A - Estante 6'},
            {'color': 'Blanco',       'acabado': 'Pulido',  'largo': 60, 'ancho': 120,'espesor': 10, 'piezas': 2, 'm2_caja': 1.44, 'stock': 7.2,  'stock_min': 6, 'ubicacion': 'Pasillo B - Estante 1'},
        ]
    },
    {
        'codigo': 'POR-003', 'destacado': True,
        'nombre': 'Porcelanato Madera Roble',
        'descripcion': 'Imitación madera de roble con venas naturales y acabado cálido. Resistencia superior al agua y a los rayones, ideal para living y dormitorios.',
        'categoria': 'porcelanato', 'marca': 'Porcelanosa',
        'precio_base': 275000, 'precio_costo': 180000, 'unidad': 'm2',
        'instalacion': ['Piso', 'Interior'],
        'variantes': [
            {'color': 'Roble Natural', 'acabado': 'Natural', 'largo': 20, 'ancho': 120, 'espesor': 10, 'piezas': 6, 'm2_caja': 1.44, 'stock': 21.6, 'stock_min': 6, 'ubicacion': 'Pasillo B - Estante 2'},
            {'color': 'Roble Gris',   'acabado': 'Natural', 'largo': 20, 'ancho': 120, 'espesor': 10, 'piezas': 6, 'm2_caja': 1.44, 'stock': 8.64, 'stock_min': 6, 'ubicacion': 'Pasillo B - Estante 3'},
            {'color': 'Roble Oscuro', 'acabado': 'Natural', 'largo': 20, 'ancho': 120, 'espesor': 10, 'piezas': 6, 'm2_caja': 1.44, 'stock': 0,    'stock_min': 6, 'ubicacion': 'Pasillo B - Estante 4'},
        ]
    },
    {
        'codigo': 'POR-004',
        'nombre': 'Porcelanato Mármol Carrara',
        'descripcion': 'Elegante imitación mármol de Carrara con venas grises sobre fondo blanco. Acabado brillante que refleja la luz para ambientes de lujo.',
        'categoria': 'porcelanato', 'marca': 'Porcelanosa',
        'precio_base': 340000, 'precio_costo': 220000, 'unidad': 'm2',
        'instalacion': ['Piso', 'Pared', 'Interior'],
        'variantes': [
            {'color': 'Blanco Carrara', 'acabado': 'Brillante', 'largo': 60, 'ancho': 60, 'espesor': 10, 'piezas': 4, 'm2_caja': 1.44, 'stock': 17.28, 'stock_min': 6, 'ubicacion': 'Pasillo B - Estante 5'},
            {'color': 'Blanco Carrara', 'acabado': 'Pulido',    'largo': 80, 'ancho': 80, 'espesor': 11, 'piezas': 2, 'm2_caja': 1.28, 'stock': 5.12,  'stock_min': 4, 'ubicacion': 'Pasillo B - Estante 6'},
        ]
    },

    # ── CERÁMICAS ──────────────────────────────────────────────────────────────
    {
        'codigo': 'CER-001',
        'nombre': 'Cerámica Baño Línea Blanca',
        'descripcion': 'Revestimiento cerámico blanco de línea clásica para baños y cocinas. Resistente a la humedad, de fácil limpieza y junta mínima.',
        'categoria': 'ceramica', 'marca': 'San Lorenzo',
        'precio_base': 65000, 'precio_costo': 40000, 'unidad': 'm2',
        'instalacion': ['Pared', 'Húmedo'],
        'variantes': [
            {'color': 'Blanco', 'acabado': 'Brillante', 'largo': 20, 'ancho': 40, 'espesor': 7, 'piezas': 12, 'm2_caja': 0.96, 'stock': 57.6, 'stock_min': 20, 'ubicacion': 'Pasillo C - Estante 1'},
            {'color': 'Blanco', 'acabado': 'Brillante', 'largo': 30, 'ancho': 60, 'espesor': 7, 'piezas': 6,  'm2_caja': 1.08, 'stock': 21.6, 'stock_min': 10, 'ubicacion': 'Pasillo C - Estante 2'},
        ]
    },
    {
        'codigo': 'CER-002',
        'nombre': 'Cerámica Hexagonal Trend',
        'descripcion': 'Mosaico hexagonal de tendencia para baños y cocinas. Diseño geométrico que aporta personalidad y modernidad al espacio.',
        'categoria': 'ceramica', 'marca': 'Gresia',
        'precio_base': 95000, 'precio_costo': 62000, 'unidad': 'm2',
        'instalacion': ['Pared', 'Piso', 'Interior'],
        'variantes': [
            {'color': 'Blanco',  'acabado': 'Mate',     'largo': 25, 'ancho': 29, 'espesor': 8, 'piezas': 14, 'm2_caja': 1.015, 'stock': 12.18, 'stock_min': 5, 'ubicacion': 'Pasillo C - Estante 3'},
            {'color': 'Negro',   'acabado': 'Mate',     'largo': 25, 'ancho': 29, 'espesor': 8, 'piezas': 14, 'm2_caja': 1.015, 'stock': 4.06,  'stock_min': 5, 'ubicacion': 'Pasillo C - Estante 4'},
            {'color': 'Cemento', 'acabado': 'Satinado', 'largo': 25, 'ancho': 29, 'espesor': 8, 'piezas': 14, 'm2_caja': 1.015, 'stock': 0,     'stock_min': 5, 'ubicacion': 'Pasillo C - Estante 5'},
        ]
    },
    {
        'codigo': 'CER-003',
        'nombre': 'Cerámica Exterior Antideslizante',
        'descripcion': 'Cerámica de alto tráfico con acabado antideslizante para exteriores, terrazas, bordes de piscina y zonas húmedas expuestas.',
        'categoria': 'ceramica', 'marca': 'Celima',
        'precio_base': 78000, 'precio_costo': 50000, 'unidad': 'm2',
        'instalacion': ['Piso', 'Exterior', 'Húmedo'],
        'variantes': [
            {'color': 'Gris',   'acabado': 'Antideslizante', 'largo': 33, 'ancho': 33, 'espesor': 8, 'piezas': 9, 'm2_caja': 0.98, 'stock': 29.4, 'stock_min': 10, 'ubicacion': 'Pasillo D - Estante 1'},
            {'color': 'Piedra', 'acabado': 'Antideslizante', 'largo': 33, 'ancho': 33, 'espesor': 8, 'piezas': 9, 'm2_caja': 0.98, 'stock': 9.8,  'stock_min': 10, 'ubicacion': 'Pasillo D - Estante 2'},
        ]
    },

    # ── PISOS ──────────────────────────────────────────────────────────────────
    {
        'codigo': 'PIS-001', 'destacado': True,
        'nombre': 'Piso Vinílico Flotante SPC',
        'descripcion': 'Piso vinílico SPC (Stone Plastic Composite) de máxima durabilidad. Resistente al agua, al impacto y a los rayones. Instalación flotante sin pegamento.',
        'categoria': 'piso', 'marca': 'Cortines',
        'precio_base': 165000, 'precio_costo': 108000, 'unidad': 'm2',
        'instalacion': ['Piso', 'Interior'],
        'variantes': [
            {'color': 'Roble Champagne', 'acabado': 'Natural', 'largo': 18, 'ancho': 122, 'espesor': 5, 'piezas': 8, 'm2_caja': 1.76, 'stock': 35.2, 'stock_min': 10, 'ubicacion': 'Pasillo D - Estante 3'},
            {'color': 'Roble Gris',      'acabado': 'Natural', 'largo': 18, 'ancho': 122, 'espesor': 5, 'piezas': 8, 'm2_caja': 1.76, 'stock': 17.6, 'stock_min': 10, 'ubicacion': 'Pasillo D - Estante 4'},
            {'color': 'Nogal Oscuro',    'acabado': 'Natural', 'largo': 18, 'ancho': 122, 'espesor': 5, 'piezas': 8, 'm2_caja': 1.76, 'stock': 3.52, 'stock_min': 8,  'ubicacion': 'Pasillo D - Estante 5'},
        ]
    },
    {
        'codigo': 'PIS-002',
        'nombre': 'Piso Cerámico Pulido Beige',
        'descripcion': 'Clásico piso cerámico pulido en tono beige cálido. Ideal para ambientes residenciales, combina con cualquier estilo de decoración.',
        'categoria': 'piso', 'marca': 'San Lorenzo',
        'precio_base': 55000, 'precio_costo': 35000, 'unidad': 'm2',
        'instalacion': ['Piso', 'Interior'],
        'variantes': [
            {'color': 'Beige', 'acabado': 'Pulido', 'largo': 45, 'ancho': 45, 'espesor': 8, 'piezas': 5, 'm2_caja': 1.0125, 'stock': 60.75, 'stock_min': 15, 'ubicacion': 'Pasillo E - Estante 1'},
            {'color': 'Arena', 'acabado': 'Pulido', 'largo': 45, 'ancho': 45, 'espesor': 8, 'piezas': 5, 'm2_caja': 1.0125, 'stock': 20.25, 'stock_min': 15, 'ubicacion': 'Pasillo E - Estante 2'},
        ]
    },

    # ── SANITARIOS ─────────────────────────────────────────────────────────────
    {
        'codigo': 'SAN-001', 'destacado': True,
        'nombre': 'Inodoro con Bidet Línea Moderna',
        'descripcion': 'Juego de baño completo con inodoro al piso y bidet de línea moderna. Descarga dual 3/6 litros para ahorro de agua. Incluye asiento de cierre suave.',
        'categoria': 'sanitario', 'marca': 'Roca',
        'precio_base': 980000, 'precio_costo': 650000, 'unidad': 'juego',
        'instalacion': ['Interior', 'Húmedo'],
        'notas': 'Stock limitado. Confirmar disponibilidad antes de ofrecer al cliente.',
        'variantes': [
            {'color': 'Blanco', 'stock': 8,  'stock_min': 3, 'ubicacion': 'Depósito - Sanitarios A'},
            {'color': 'Hueso',  'stock': 3,  'stock_min': 2, 'ubicacion': 'Depósito - Sanitarios A'},
        ]
    },
    {
        'codigo': 'SAN-002',
        'nombre': 'Lavatorio Mural Minimalista',
        'descripcion': 'Lavatorio de colgar con líneas limpias y diseño minimalista. Ideal para baños pequeños y de diseño contemporáneo. Sin pedestal.',
        'categoria': 'sanitario', 'marca': 'Roca',
        'precio_base': 420000, 'precio_costo': 280000, 'unidad': 'pieza',
        'instalacion': ['Interior', 'Húmedo'],
        'variantes': [
            {'color': 'Blanco', 'stock': 12, 'stock_min': 3, 'ubicacion': 'Depósito - Sanitarios B'},
        ]
    },
    {
        'codigo': 'SAN-003',
        'nombre': 'Ducha Empotrada Cromo',
        'descripcion': 'Sistema de ducha empotrada con lluvia superior y salida lateral. Terminación cromada de alta durabilidad. Incluye termostato.',
        'categoria': 'sanitario', 'marca': 'Roca',
        'precio_base': 650000, 'precio_costo': 430000, 'unidad': 'juego',
        'instalacion': ['Interior', 'Húmedo'],
        'variantes': [
            {'color': 'Cromo',    'stock': 5,  'stock_min': 2, 'ubicacion': 'Depósito - Sanitarios C'},
            {'color': 'Negro Mat','stock': 2,  'stock_min': 2, 'ubicacion': 'Depósito - Sanitarios C'},
        ]
    },
    {
        'codigo': 'SAN-004',
        'nombre': 'Pileta de Cocina Doble',
        'descripcion': 'Pileta de acero inoxidable con dos pozas de diferente profundidad. Incluye escurridor y tapón automático.',
        'categoria': 'sanitario',
        'precio_base': 380000, 'precio_costo': 240000, 'unidad': 'pieza',
        'instalacion': ['Interior'],
        'variantes': [
            {'color': 'Acero Inox', 'stock': 7, 'stock_min': 2, 'ubicacion': 'Depósito - Cocinas A'},
        ]
    },

    # ── ACCESORIOS DE BAÑO ─────────────────────────────────────────────────────
    {
        'codigo': 'ACC-001',
        'nombre': 'Espejo Baño con Luz LED',
        'descripcion': 'Espejo de baño retroiluminado con luz LED fría. Marco de aluminio sin tornillos visibles. Interruptor táctil. Varios tamaños disponibles.',
        'categoria': 'accesorio_bano',
        'precio_base': 320000, 'precio_costo': 210000, 'unidad': 'pieza',
        'instalacion': ['Interior', 'Húmedo'],
        'variantes': [
            {'color': 'Marco Plata', 'largo': 60, 'ancho': 80, 'stock': 8,  'stock_min': 2, 'precio_propio': 320000, 'ubicacion': 'Exhibición - Espejos'},
            {'color': 'Marco Plata', 'largo': 80, 'ancho': 100,'stock': 5,  'stock_min': 2, 'precio_propio': 420000, 'ubicacion': 'Exhibición - Espejos'},
            {'color': 'Marco Negro', 'largo': 60, 'ancho': 80, 'stock': 3,  'stock_min': 2, 'precio_propio': 350000, 'ubicacion': 'Exhibición - Espejos'},
        ]
    },
    {
        'codigo': 'ACC-002',
        'nombre': 'Set Accesorios Baño 5 Piezas',
        'descripcion': 'Set completo: porta rollo, toallero simple, toallero doble, jabonera y gancho. Disponible en cromo y negro mate.',
        'categoria': 'accesorio_bano',
        'precio_base': 185000, 'precio_costo': 118000, 'unidad': 'juego',
        'instalacion': ['Interior'],
        'variantes': [
            {'color': 'Cromo',      'stock': 14, 'stock_min': 3, 'ubicacion': 'Pasillo F - Estante 1'},
            {'color': 'Negro Mate', 'stock': 9,  'stock_min': 3, 'ubicacion': 'Pasillo F - Estante 2'},
            {'color': 'Dorado',     'stock': 4,  'stock_min': 2, 'precio_propio': 235000, 'ubicacion': 'Pasillo F - Estante 3'},
        ]
    },
    {
        'codigo': 'ACC-003',
        'nombre': 'Mampara de Ducha Vidrio Templado',
        'descripcion': 'Mampara fija de vidrio templado 8mm con perfil de aluminio. Cierre magnético silencioso. Incluye kit de instalación.',
        'categoria': 'accesorio_bano',
        'precio_base': 890000, 'precio_costo': 590000, 'unidad': 'pieza',
        'instalacion': ['Interior', 'Húmedo'],
        'variantes': [
            {'color': 'Perfil Cromo', 'largo': 80,  'ancho': 195, 'stock': 4, 'stock_min': 1, 'precio_propio': 890000, 'ubicacion': 'Depósito - Mamparas'},
            {'color': 'Perfil Cromo', 'largo': 100, 'ancho': 195, 'stock': 3, 'stock_min': 1, 'precio_propio': 980000, 'ubicacion': 'Depósito - Mamparas'},
            {'color': 'Perfil Negro', 'largo': 80,  'ancho': 195, 'stock': 2, 'stock_min': 1, 'precio_propio': 950000, 'ubicacion': 'Depósito - Mamparas'},
        ]
    },

    # ── ARTÍCULOS DE COCINA ────────────────────────────────────────────────────
    {
        'codigo': 'COC-001',
        'nombre': 'Grifería Cocina Cuello de Ganso',
        'descripcion': 'Grifería monocomando con caño cuello de ganso de alto alcance. Cartucho cerámico de larga duración. Incluye flexibles de conexión.',
        'categoria': 'cocina',
        'precio_base': 285000, 'precio_costo': 185000, 'unidad': 'pieza',
        'instalacion': ['Interior'],
        'variantes': [
            {'color': 'Cromo',      'stock': 11, 'stock_min': 3, 'ubicacion': 'Pasillo G - Estante 1'},
            {'color': 'Negro Mate', 'stock': 6,  'stock_min': 2, 'precio_propio': 310000, 'ubicacion': 'Pasillo G - Estante 2'},
            {'color': 'Dorado',     'stock': 3,  'stock_min': 2, 'precio_propio': 345000, 'ubicacion': 'Pasillo G - Estante 3'},
        ]
    },
    {
        'codigo': 'COC-002',
        'nombre': 'Bajo Mesada Modular',
        'descripcion': 'Mueble bajo mesada de MDF melamínico con puerta y cajón. Bisagras de cierre suave. Medidas estándar compatibles con piletas de 60cm.',
        'categoria': 'cocina',
        'precio_base': 450000, 'precio_costo': 290000, 'unidad': 'pieza',
        'instalacion': ['Interior'],
        'variantes': [
            {'color': 'Blanco',   'stock': 6, 'stock_min': 2, 'ubicacion': 'Depósito - Muebles A'},
            {'color': 'Roble',    'stock': 4, 'stock_min': 2, 'precio_propio': 490000, 'ubicacion': 'Depósito - Muebles A'},
            {'color': 'Antracita','stock': 2, 'stock_min': 2, 'precio_propio': 490000, 'ubicacion': 'Depósito - Muebles A'},
        ]
    },
]

# Crear todos los productos
creados = 0
for p in PRODUCTOS_DEMO:
    try:
        prod = crear_producto_con_variantes(p)
        nvars = prod.variantes.count()
        stock_t = sum(
            float(v.stock.cantidad) for v in prod.variantes.all()
            if hasattr(v, 'stock')
        )
        print(f'  ✓ [{prod.codigo}] {prod.nombre[:45]} — {nvars} var. | {stock_t:.1f} uds.')
        creados += 1
    except Exception as e:
        print(f'  ✗ ERROR en {p["codigo"]}: {e}')

# ── Resumen ────────────────────────────────────────────────────────────────────
total_variantes = Variante.objects.filter(activa=True).count()
con_stock  = Stock.objects.filter(cantidad__gt=0).count()
sin_stock  = Stock.objects.filter(cantidad=0).count()
from django.db.models import F as _F
critico    = Stock.objects.filter(cantidad__gt=0).filter(cantidad__lte=_F('stock_minimo')).count()

print('\n' + '='*55)
print(f'  Productos creados:   {creados}')
print(f'  Total variantes:     {total_variantes}')
print(f'  Con stock:           {con_stock}')
print(f'  Sin stock:           {sin_stock}')
print()
print('  Usuarios disponibles:')
for u in usuarios_demo:
    print(f'    {u["username"]:12} / {u["password"]}  ({u["nombre_completo"]})')
print()
print('  Sistema listo para la demo.')
print('='*55 + '\n')

