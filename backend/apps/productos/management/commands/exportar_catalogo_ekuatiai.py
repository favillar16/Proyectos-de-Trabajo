"""
Exporta el catálogo de productos al formato de importación masiva de
e-Kuatia'i (Catálogo de Productos/Servicios).

    python manage.py exportar_catalogo_ekuatiai
    python manage.py exportar_catalogo_ekuatiai --salida catalogo.csv

Formato exigido por la "Guía paso a paso: Catálogo de productos y servicios
(Sistema e-kuatia'i)" (DNIT, enero/2026) — no es un formato inventado, es el
que el portal valida al importar:

    1. Código Interno del Producto   — hasta 50 caracteres alfanuméricos
    2. Descripción del Producto      — hasta 2000 caracteres alfanuméricos
    3. Precio Unitario (con IVA)     — numérico, punto como separador decimal
    4. Forma de Afectación Tributaria — literal "Gravado IVA" o "Exento"
    5. Tasa de Impuestos             — literal "IVA 10%", "IVA 5%" o "EXENTO"

SIN encabezados, columnas exactamente en ese orden. El catálogo de
e-Kuatia'i admite un máximo de 1.000 registros en total (carga manual +
importada); si esto se acerca a ese límite hay que revisar qué se sigue
exportando.

El precio ya sale con IVA incluido: Producto.precio_base (o
Variante.precio_diferencial si la variante tiene precio propio) se carga
así en todo el sistema — ver el comentario en apps/productos/models.py.

DELIMITADOR ";", NO ",": la guía dice ".CSV (delimitado por comas)", pero
una primera exportación con coma real (RFC 4180, la que produce
csv.writer con delimiter=",") fue rechazada por el portal: las 658 filas
volvieron con "Campo no informado" en TODAS, y el CSV de excepciones que
devuelve e-Kuatia'i viene delimitado por ";" — señal de que el parser del
importador separa por ";", no por ",". Eso coincide con un problema
conocido de Excel: en Windows con configuración regional en español
(donde la coma es el separador decimal), el diálogo "Guardar como → CSV
(delimitado por comas)" en realidad escribe con el separador de lista del
sistema, que en esa configuración es ";" — la etiqueta del diálogo no
cambia según el idioma, pero el separador real sí. La guía del DNIT casi
seguro se escribió así, y el backend del portal se probó contra ese
archivo real, no contra el texto de la etiqueta. Por eso este comando
genera ";" a propósito.

CODIFICACIÓN Windows-1252 ("ANSI"), NO UTF-8: por el mismo motivo — es lo
que ese mismo diálogo de Excel produce en Windows. El archivo de
excepciones devuelto por el portal ya venía con los acentos y la "ñ"
perdidos (`Baño` → `Bao`), consistente con que el importador no está
leyendo UTF-8. Se verificó que todo el catálogo actual entra en
Windows-1252 sin pérdida (alfabeto latino: sin caracteres fuera de ese
rango); si en el futuro entra un producto con un carácter que no sea
representable ahí, este comando corta con UnicodeEncodeError en vez de
guardar el archivo con datos corrompidos en silencio.
"""
import csv

from django.core.management.base import BaseCommand

from apps.productos.models import Variante

LIMITE_CATALOGO = 1000
LONGITUD_MAX_CODIGO = 50


class Command(BaseCommand):
    help = (
        "Genera el CSV de importación masiva de productos/servicios para "
        "el portal e-Kuatia'i (Catálogo de Productos)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--salida', default='catalogo_ekuatiai.csv',
            help='Ruta del archivo .csv a generar (default: catalogo_ekuatiai.csv '
                 'en el directorio actual).',
        )

    def handle(self, *args, **opciones):
        salida = opciones['salida']

        variantes = (
            Variante.objects
            .filter(activa=True, producto__activo=True)
            .select_related('producto', 'acabado')
            .order_by('producto__codigo', 'sku')
        )

        filas = []
        omitidas = []
        for variante in variantes:
            codigo = variante.sku
            if not codigo or len(codigo) > LONGITUD_MAX_CODIGO:
                omitidas.append(variante)
                continue

            descripcion = self._descripcion(variante)
            precio = self._precio(variante)
            afectacion, tasa = self._impuesto(variante.producto.tasa_iva)

            filas.append([codigo, descripcion, precio, afectacion, tasa])

        if len(filas) > LIMITE_CATALOGO:
            self.stdout.write(self.style.WARNING(
                f'  AVISO: {len(filas)} filas superan el limite de '
                f'{LIMITE_CATALOGO} registros que admite el catalogo de '
                f'e-Kuatia\'i. El portal va a rechazar el archivo completo.'
            ))

        with open(salida, 'w', newline='', encoding='cp1252') as archivo:
            escritor = csv.writer(archivo, delimiter=';')
            escritor.writerows(filas)

        self.stdout.write(self.style.SUCCESS(
            f'  {len(filas)} productos exportados a {salida}'
        ))
        if omitidas:
            self.stdout.write(self.style.WARNING(
                f'  {len(omitidas)} variantes omitidas por no tener SKU '
                f'valido (revisar manualmente): '
                + ', '.join(v.sku or f'id={v.pk}' for v in omitidas)
            ))

    @staticmethod
    def _descripcion(variante):
        partes = [variante.producto.nombre]
        if variante.largo_cm and variante.ancho_cm:
            partes.append(f'{variante.largo_cm:.0f}x{variante.ancho_cm:.0f} cm')
        if variante.color:
            partes.append(variante.color)
        if variante.acabado:
            partes.append(variante.acabado.nombre)
        return ' - '.join(partes)[:2000]

    @staticmethod
    def _precio(variante):
        precio = variante.precio_venta
        if precio == precio.to_integral_value():
            return str(int(precio))
        return str(precio.normalize())

    @staticmethod
    def _impuesto(tasa_iva):
        if tasa_iva == 0:
            return 'Exento', 'EXENTO'
        return 'Gravado IVA', f'IVA {tasa_iva}%'
