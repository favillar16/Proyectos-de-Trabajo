# Ejemplos de los reportes

Un ejemplo de cada reporte descargable, en PDF y en Excel, generado el
18/11/2026 con el formato nuevo (`backend/apps/caja/reportes.py`). Los datos son
los de prueba de la base de desarrollo, no ventas reales del local.

Todos los PDF abren con un resumen (las cifras principales en recuadros) y
debajo el detalle; la cuenta completa va al final, con lo que resta marcado
`(-)` y el resultado `(=)`. Los Excel traen montos y cantidades como números,
para poder sumarlos y filtrarlos.

| Archivo | Reporte | Dónde se descarga |
|---|---|---|
| `01_stock` | Stock: primero lo que hay que reponer | Dashboard → Reportes |
| `02_balance_ventas` | Balance de Ventas, con el desglose por medio de pago | Dashboard → Reportes |
| `03_extracto_caja` | Extracto de Caja: un renglón por turno | Dashboard → Reportes |
| `04_productos_comercializados` | Qué se vendió, acumulado por producto | Dashboard → Reportes |
| `05_productos_comercializados_detalle` | Lo mismo, una fila por venta | Dashboard → Reportes |
| `06_ganancias` | Ganancias: hoja 1 de resumen, detalle desde la 2 | Dashboard → Reportes |
| `07_ganancias_detalle` | Ganancias venta por venta | Dashboard → Reportes |
| `08_comisiones_bancarias` | Lo que descuenta el banco de tarjetas, QR y PIX | Dashboard → Reportes |
| `09_arqueo_caja` | Arqueo de un día, con la planilla de conteo | Dashboard → Reportes |
| `10_clientes` | Monto invertido por cliente | Clientes |
| `11_registro_ajustes` | Ajustes manuales de stock | Inventario → Registro de ajustes |

Para regenerarlos después de cambiar un reporte, usar las funciones
`reporte_*` de `apps/caja/reportes.py` con `render_pdf` / `render_xlsx`.
