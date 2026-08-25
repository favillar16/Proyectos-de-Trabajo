# Periféricos — mapa general e impresoras

Qué hay conectado al sistema y para qué sirve cada cosa.

| Dispositivo | Para qué | Dónde se configura | Detalle |
|---|---|---|---|
| **Lector FTX LC123BH5** | Escanear productos en showroom, pedidos, inventario y alta de mercadería | No se configura: es un teclado | **`docs/LECTOR_CODIGO_BARRAS.md`** |
| **Térmica FTX FTXP-80W** | Tickets y comprobantes de mostrador | `IMPRESORA_TERMICA_*` en `backend\.env` | §2 de este doc |
| **Epson EcoTank L1250** | Etiquetas de código de barras en hoja A4 | `IMPRESORA_A4_*` en `backend\.env` | §1 de este doc |
| **Impresora de facturas** | Comprobante fiscal | ⏳ **Pendiente** — todavía no se definió el equipo | — |

> ⚠️ **La L1250 no imprime facturas.** El comprobante fiscal va a salir por su
> propio equipo, que todavía no está conectado. La L1250 está para lo que
> necesita hoja A4 común — hoy, las etiquetas de código de barras.

Para probar las dos impresoras de una sola vez:

```
cd backend
venv\Scripts\activate
python diagnostico_impresora.py
```

Lista las impresoras instaladas en Windows, avisa si el nombre del `.env` no
coincide con ninguna, y ofrece imprimir una hoja de prueba en cada una.

---

## 1. Epson EcoTank L1250 — etiquetas en hoja A4

### Qué imprime

La planilla de etiquetas de código de barras para pegar en la mercadería. Es
la contraparte física del lector: los productos que vienen sin EAN de fábrica
—buena parte de los sanitarios y accesorios— no tienen nada que escanear hasta
que se les pega una.

No imprime comprobantes. Tampoco entiende ESC/POS: es una inyección de tinta
con driver GDI, y mandarle los bytes de la térmica saca páginas de basura. Todo
lo que sale por ella va como PDF.

### Instalación

1. Instalar la impresora en **Panel de control → Dispositivos e impresoras**
   (driver de Epson, por USB o WiFi).
2. Copiar el nombre **exacto** con el que quedó registrada. El driver de Epson
   suele registrarla como `EPSON L1250 Series`, pero puede variar.
3. Pegarlo en `backend\.env`:

```
IMPRESORA_A4_NOMBRE=EPSON L1250 Series
IMPRESORA_A4_MODO=manual
IMPRESORA_A4_COPIAS=1
```

4. Reiniciar el sistema (`iniciar.bat`).
5. Verificar con `python diagnostico_impresora.py`.

### Los dos modos

- **`manual`** (recomendado y default) — el sistema arma el PDF y lo abre en el
  navegador; se imprime desde el diálogo de siempre. Anda en cualquier equipo,
  sin depender de qué visor de PDF esté instalado.
- **`auto`** — el servidor manda el PDF a la cola de Windows sin diálogo.
  Necesita que el `.pdf` tenga registrado el verbo **"printto"**, que lo
  instala Adobe Acrobat Reader y **no** trae el visor de Edge ni el de Chrome.
  Si no está, el trabajo se pierde en silencio — el peor modo de fallar. El
  diagnóstico chequea si está registrado antes de que se descubra a mano.

### Primero los códigos, después las etiquetas

Para la mercadería sin EAN de fábrica, el sistema genera un código propio con
**prefijo 200**, el rango que GS1 reserva para uso interno de un comercio (así
nunca colisiona con el código real de un fabricante):

```
python manage.py asignar_codigos_barras --simular   # muestra qué haría
python manage.py asignar_codigos_barras             # los asigna
```

Nunca pisa un código existente: si la caja ya trae el EAN de fábrica, ese manda.

> ⚠️ **Correrlo en la PC servidor, no en la notebook.** La notebook es un
> espejo de solo lectura: lo que se escriba ahí se pisa en la siguiente
> sincronización.

### Imprimir las etiquetas

**Desde el sistema:** Inventario → filtrar lo que se quiere etiquetar → botón
**«Etiquetas»**. Se imprime lo que está a la vista, así que los filtros de
arriba son los que eligen qué entra en la planilla.

**Desde la consola**, para el catálogo completo o un producto puntual:

```
python manage.py imprimir_etiquetas --sin-imprimir       # deja el PDF para revisar
python manage.py imprimir_etiquetas --producto POR-001
python manage.py imprimir_etiquetas --desde 7            # reusar una planilla empezada
python manage.py imprimir_etiquetas --imprimir           # directo a la L1250 (modo auto)
```

### ⚠️ Imprimir siempre a escala 100%

La opción "ajustar a la página" del diálogo de impresión **achica el código de
barras y el lector deja de leerlo**. Es el error más común y el más difícil de
diagnosticar después, porque la etiqueta se ve perfecta.

### Formato de la planilla

Grilla de **3 × 8 etiquetas de 70 × 37 mm** en A4 — el formato autoadhesivo más
común de librería. Si se compra otro formato, se cambian las cuatro constantes
al principio de la sección de etiquetas en `backend/apps/caja/impresora_a4.py`
(`ETIQUETAS_COLUMNAS`, `ETIQUETAS_FILAS`, `ETIQUETA_ANCHO_MM`,
`ETIQUETA_ALTO_MM`) y el resto se acomoda solo.

El parámetro `desde` saltea las primeras celdas de la primera hoja, para reusar
una planilla a la que ya se le arrancaron etiquetas. Sin eso, imprimir tres
etiquetas gasta una hoja entera.

---

## 2. Térmica FTX FTXP-80W

Tickets y comprobantes de mostrador. Habla ESC/POS: el sistema le manda los
bytes crudos por la cola de Windows (`apps/caja/printer.py`). Se configura con
`IMPRESORA_TERMICA_NOMBRE` en `backend\.env` y se prueba con el mismo
`diagnostico_impresora.py`.

Mientras no esté conectada la impresora de facturas, la factura también sale
por acá. Sin timbrado cargado imprime la leyenda de que no es válida como
comprobante fiscal — ver `python manage.py verificar_fiscal`.

---

## 3. Problemas comunes

Los del lector están en `docs/LECTOR_CODIGO_BARRAS.md` §5. Los de las
impresoras:

| Síntoma | Causa habitual |
|---|---|
| La L1250 no aparece | El nombre del `.env` no coincide con el de Windows. `diagnostico_impresora.py` lista los nombres reales |
| Las etiquetas no se leen | Se imprimieron con "ajustar a la página". Reimprimir a escala 100% |
| Las etiquetas caen fuera del troquel | La planilla comprada no es 3×8 de 70×37 mm. Ver "Formato de la planilla" |
| «Ninguna variante tiene código de barras cargado» | Falta correr `asignar_codigos_barras` en la PC servidor |
| En modo `auto` no sale nada y no hay error | Falta el verbo `printto` para los `.pdf`. Dejar `IMPRESORA_A4_MODO=manual` |
| La térmica no imprime | Ver `docs/checklist_entrega.md` → "La impresora no imprime" |
