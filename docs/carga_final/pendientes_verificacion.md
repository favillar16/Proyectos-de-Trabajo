# Pendientes de verificación manual — carga final

Lo que no se pudo leer con certeza del escaneo
`docs/pdf de carga final de productos.pdf`. Cada punto indica la **página del
PDF** para ir directo al papel el día de la carga.

## 1. Datos ilegibles en el escaneo

| Pág. | Proveedor | Qué falta | Cómo llegar |
|------|-----------|-----------|-------------|
| **14** | Agro Aceros F. 0058096 | Código de artículo del **CONJUNTO ICASA 4X3PZ NEGRO** (2 un. a 82.000 c/u… ver nota). El agujero de la perforadora tapa el código. Los hermanos de la serie son 431-2, 432-9, 433-6, 434-3, 435-0 → el negro debería seguir el patrón. | Fila con `cod_proveedor = SIN CODIGO LEGIBLE` |
| **14** | Agro Aceros F. 0058096 | Código `4509-7` del **KIT ACCESORIO P/BAÑO PLASTICO 5PZ BLANCO** — se lee borroso, confirmar contra el papel. | |
| **15** | Agro Aceros F. 0058097 | Código de la **PUERTA PVC BLANCO 0.72×2.10** (3 un. a 106.000). La fila quedó cortada en el borde del escaneo. Los otros tres son 2701-4, 2703-8, 2706-2. | Fila con `cod_proveedor = SIN CODIGO LEGIBLE` |
| **28** | El Renacer F. 0003652 | Referencia de la **Bacha Red. Roma semiemb.** — se lee `3346` pero puede ser `3396`. | |
| **1** | San Carlos F. 0183189 | La línea dice `CEJATEL 53X53` — puede ser **CERATEL**. Confirmar el nombre de la línea con el proveedor. | |
| **26** | Emporio F. 0002487 | Dos bachas (`561483` / `6CC008C4` y `561606` / `6CC008C44`) vienen **sin medidas** en la factura. Hay que medirlas o pedirle la ficha al proveedor. | |

## 2. Diferencia de importe (única del lote)

| Pág. | Proveedor | Detalle |
|------|-----------|---------|
| **27** | Prolar Shop F. 0110787 | La suma de las 15 líneas que leí da **5.230.500**, la factura declara **5.220.500**. Faltan 10.000 en alguna línea — lo más probable es que uno de los dos espejos redondos de 70 cm sea **178.500** y no 183.500. **Verificar precio unitario línea por línea contra el papel.** |

Las otras **25 facturas cuadran al guaraní** contra el total impreso, así que
esas líneas se pueden cargar sin revisar precio por precio.

## 3. Decisiones del negocio (no son errores de lectura)

Cosas anotadas a mano sobre las facturas que hay que resolver antes de tocar el
stock:

| Pág. | Ítem | Anotación | Qué decidir |
|------|------|-----------|-------------|
| **8** | KIT INO. CIST. ALTA DONA BEJA AZUL (cód. 20326) | «NO (se vendió)» | ¿Entra al stock o ya salió? |
| **8** | KIT INO. CIST. BAJA ALAMO BLANCO (cód. 7372) | Cantidad corregida de **5 → 4** | ¿Cargar 4 o 5? |
| **8** | INODORO ALTA ARAXA BLANCO (cód. 20400) | Cantidad corregida de **5 → 3** | ¿Cargar 3 o 5? |
| **9** | CUÑA NIVELADORA METASUL NEGRA (cód. 23387) | «NO» | ¿Entra al stock? |
| **27** | ESPEJO REDONDO 70CM DD (cód. 6ES0270D) | «ROTO» | No cargar al stock (o cargar como baja) |
| **27** | KIT INOX 5PCS RD TDS (cód. 5JG223MD) | «Devolución» | No cargar al stock |
| **16** | CORTAG EXHIBIDOR (cód. 7712) | — | Es un **mueble de exhibición**, no mercadería. ¿Se carga al catálogo o va como gasto? |
| **27** | Toda la factura Prolar | «Verificar % con Pamela» | La factura está a nombre de **Pamela Pereira** (socia), no de la EAS. Hay porcentajes de margen anotados al pie («Lav. 35%», y otros dos debajo). Definir el margen antes de fijar precio de venta. |
| **8/9/10/11** | Todas las de SiderAgro | — | Están a nombre de **Rubén Darío Soto Narváez** (rep. legal), no de la EAS. |

## 4. Recordatorio sobre los precios

**Todos los importes del CSV son precio de COSTO** (lo que se le pagó al
proveedor, IVA incluido). El sistema guarda el precio de venta en
`Producto.precio_base` y el costo en `Producto.precio_costo`. Antes de cargar
hay que definir el margen por rubro — las únicas pistas del lote son las
anotaciones a mano de la página 27.

Para los cerámicos y porcelanatos el precio de factura es **por m²**, no por
caja: la columna `cantidad_factura` de esas filas también está en m².
