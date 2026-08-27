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
2. Definir el margen de venta por rubro.
3. Dar de alta las marcas que todavía no existan: OASIS, BELLO, DSN, FORMIGRES,
   VIVA, ROCHAFORTE, CELITE, CORONA, DECA, INCEPA, ROCA, SANTA CLARA, SIDER,
   ICASA, CIPLA, FV, MAPEI, MEGACOLA, CORTAG, METASUL, PCT, LORENZETTI, PERIN.
4. El stock se carga con `Stock.registrar_movimiento()` — **nunca** tocando
   `Stock.cantidad` a mano (ver `CLAUDE.md`).
