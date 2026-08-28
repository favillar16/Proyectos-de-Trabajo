# Carga final de productos — lote agosto 2026

Extraído de `docs/pdf de carga final de productos.pdf` (30 páginas escaneadas,
sin capa de texto: se leyeron como imagen, página por página).

## Qué hay acá

| Archivo | Qué es |
|---------|--------|
| `productos_a_cargar.csv` | **184 líneas** de mercadería, una por variante a dar de alta. Separador `;`, UTF-8 con BOM (se abre directo en Excel). |
| `pendientes_verificacion.md` | Lo que no se pudo leer del escaneo, con número de página, más las decisiones de negocio anotadas a mano sobre las facturas. |
| `datos_fiscales.md` | RUC, timbrado y domicilio fiscal sacados de los dos PDF legales, en formato listo para pegar en el `.env`. |

## Resumen del lote

**26 comprobantes de 8 proveedores**, entre el 28/05/2026 y el 24/08/2026:

| Proveedor | RUC | Comprobantes | Total Gs. |
|-----------|-----|--------------|-----------|
| MERCOESTE S.A.E.C.A. | 80059879-2 | 10 | 84.698.490 |
| SiderAgro S.A. | 80026064-3 | 4 | 18.519.185 |
| SANYCER S.A.C.I. | 80030944-8 | 2 | 17.175.221 |
| San Carlos S.R.L. | 80054999-6 | 4 | 16.347.056 |
| Agro Aceros S.A. | 80117815-0 | 2 | 6.047.000 |
| El Renacer Comercial | 1357352-7 | 1 | 5.667.000 |
| Prolar Shop | 7510797-0 | 1 | 5.220.500 |
| Emporio / DIKASA | 80061011-3 | 1 | 3.279.000 |
| **Total del lote** | | **25 facturas + 1 recibo** | **156.953.452** |

La página 13 es un **recibo de dinero** de Agro Aceros (6.047.000, cancela las
facturas 58096 y 58097) — no trae mercadería. Las páginas 5, 6 y 7 son
**remitos de San Carlos** que duplican las facturas de las páginas 3, 2 y 1
respectivamente; sirven de control cruzado, no agregan productos.

Rubros que trae: porcelanatos y cerámicos (45×120, 60×60, 57×57, 58×58, 53×53,
50×50, 32×45, 20×20), sanitarios completos (líneas Corona Laguna, Deca Izy,
Celite Saveiro, Incepa Thema, Santa Clara Araxa), bachas y lavatorios, cisternas
Cipla, mingitorios, grifería FV, caños y plomería, espejos, pastina Mapei,
argamasa, niveladores Cortag/Metasul, puertas PVC y kits de accesorios.

## Control de exactitud

**25 de las 26 facturas cierran exacto** contra el total impreso en el papel —
o sea, las líneas están completas y los precios bien leídos.

La excepción es la **página 27 (Prolar Shop)**: mi suma da 5.230.500 y la
factura dice 5.220.500. Está detallado en `pendientes_verificacion.md`.

## Columnas del CSV

Las primeras seis son **trazabilidad al papel** — de dónde salió cada fila:

`pagina` · `proveedor` · `factura` · `fecha` · `cod_proveedor` ·
`descripcion_factura`

Las siguientes son la **propuesta de carga** al modelo del sistema
(`Producto` → `Variante`):

`categoria_sugerida` (mapea a `Categoria.tipo`) · `marca` · `nombre_producto` ·
`color` · `largo_cm` · `ancho_cm` · `unidad_venta` · `m2_por_caja` ·
`piezas_por_caja`

Y el cierre es **cantidad y costo**:

`cantidad_factura` · `unidad_cantidad` · `cajas` · `costo_unitario_gs` ·
`total_linea_gs` · `observaciones`

### Dos cosas para tener presentes

1. **`costo_unitario_gs` es COSTO, no precio de venta.** Va a
   `Producto.precio_costo`. El `precio_base` (venta) hay que definirlo aplicando
   el margen del rubro.

2. **En cerámicos y porcelanatos la cantidad está en m², no en cajas.** El
   `m2_por_caja` sale de la propia descripción de la factura y da exacto contra
   la cantidad facturada. Ejemplos verificados:

   | Producto | Cant. facturada | m²/caja | Cajas |
   |----------|-----------------|---------|-------|
   | Bello Oasi Duna Ripa 45×120 | 38,64 m² | 1,61 | 24 |
   | Elizabeth Pure White 60×60 | 144,00 m² | 1,80 | 80 |
   | Formigres Dhama Azul 32×45 | 288,00 m² | 2,00 | 144 |
   | Rochaforte HD 57×57 | 158,40 m² | 3,30 | 48 |
   | Malibu Lake 20×20 | 69,12 m² | 0,64 | 108 |

## Antes de cargar

1. Leer `pendientes_verificacion.md` y resolver los 6 datos ilegibles y las 8
   decisiones de negocio anotadas a mano.
2. Definir el margen de venta por rubro (paso 3 de abajo).

Las marcas y las categorías **no** hay que darlas de alta a mano: el comando
las crea si faltan. El stock tampoco se toca a mano — entra por
`Stock.registrar_movimiento()`, como exige `CLAUDE.md`.

## Cómo cargarlo

```
cd backend
venv\Scripts\activate
python manage.py cargar_lote_facturas --margen 40 --dry-run
```

El `--dry-run` hace la carga completa de verdad y la deshace al final, así que
lo que muestra es exactamente lo que va a pasar: cuántos productos y variantes
entran, qué filas se saltean y cuáles se ajustan. Recién cuando la salida
convence, se corre sin `--dry-run`.

| Opción | Para qué |
|--------|----------|
| `--margen 40` | Margen general en % sobre el costo. **Obligatorio** (el CSV solo trae costos). |
| `--margen-rubro ceramica=35,pastina=60` | Margen distinto por rubro; pisa al general. |
| `--redondeo 1000` | Redondea el precio de venta hacia arriba al millar (default). `0` lo deja exacto. |
| `--incluir-dudosos` | Carga también las 3 filas con decisiones de negocio abiertas. |
| `--sin-stock` | Solo el catálogo, sin movimientos de inventario. |
| `--archivo ruta.csv` | Otro CSV con el mismo formato. |

Con margen parejo de 40% la corrida da **181 variantes en 111 productos**, 3
filas salteadas y 0 errores.

Es idempotente: repetirlo no duplica nada ni vuelve a sumar stock. La clave es
(`nombre_producto`, `color`), y las filas que comparten `nombre_producto` se
agrupan en un solo Producto con una Variante por color.

### Lo que el comando decide solo, y avisa

- **3 filas salteadas** — las que en `observaciones` dicen «confirmar si…»:
  el kit Dona Beja que puede haberse vendido, la cuña niveladora marcada «NO»
  y el exhibidor Cortag. Entran con `--incluir-dudosos`.
- **2 al catálogo con stock 0** — las marcadas «no cargar al stock» (el espejo
  ROTO y el kit devuelto): el producto existe, la mercadería no.
- **7 filas ajustadas** — 4 conjuntos de baño que traen una sola medida (el
  modelo pide largo y ancho juntos, así que se cargan sin dimensiones; la
  medida ya está en el nombre) y 3 cerámicos donde el m²/caja del fabricante
  no cierra con las piezas por caja (gana el m²/caja de la factura, que es el
  que se verificó contra las cantidades).
- **19 filas comparten producto con otro costo** — queda el de la primera
  fila. Son diferencias reales entre facturas del mismo artículo; hay que
  repasar esos precios a mano en la pantalla de Productos.

### Después de cargar

Las fotos no se vinculan solas: se suben por variante desde la pantalla de
Productos, usando el código de proveedor que queda guardado en «notas
internas» de cada producto junto con la página y el número de factura.
