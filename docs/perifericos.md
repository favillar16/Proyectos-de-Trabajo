# Periféricos — lector de código de barras e impresoras

Qué hay conectado al sistema, para qué sirve cada cosa y cómo se prueba.

| Dispositivo | Para qué | Dónde se configura |
|---|---|---|
| **Lector FTX-LC123BH5** | Escanear productos en showroom, pedidos y depósito | No se configura: es un teclado |
| **Térmica FTX FTXP-80W** | Tickets y comprobantes de mostrador | `IMPRESORA_TERMICA_*` en `backend\.env` |
| **Epson EcoTank L1250** | Etiquetas de código de barras en hoja A4 | `IMPRESORA_A4_*` en `backend\.env` |
| **Impresora de facturas** | Comprobante fiscal | ⏳ **Pendiente** — todavía no se definió el equipo |

> ⚠️ **La L1250 no imprime facturas.** El comprobante fiscal va a salir por su
> propio equipo, que todavía no está conectado. La L1250 está para lo que
> necesita hoja A4 común — hoy, las etiquetas de código de barras.

Para probar las dos impresoras y el estado del lector de una sola vez:

```
cd backend
venv\Scripts\activate
python diagnostico_impresora.py
```

---

## 1. Lector de código de barras FTX-LC123BH5

### Cómo funciona (y por qué no hay driver que instalar)

El FTX-LC123BH5 es un **HID**: Windows lo ve como un teclado más. Al leer un
código lo "tipea" carácter por carácter y termina con un Enter. No hay driver,
no hay puerto serie, no hay servicio corriendo. Se enchufa el receptor USB y
funciona.

El sistema lo distingue del tipeo humano por la **velocidad**: una persona
tarda 80–200 ms entre teclas, el lector manda todo el código en menos de 30 ms
por carácter. Esa es toda la magia (`frontend/src/hooks/useEscaner.js`).

### Configuración del lector — sí hay que verificar una cosa

El lector tiene que tener configurado **Enter (CR) como sufijo**. Viene así de
fábrica, pero si alguien lo reconfiguró, sin el Enter el sistema junta las
teclas y nunca dispara la búsqueda. Se restablece escaneando el código de
"Restore factory defaults" del manualito que trae el aparato.

Simbologías: lee EAN-13 y Code128 de fábrica, que son las dos que el sistema
imprime. No hace falta habilitar nada.

### Qué hace un escaneo en cada pantalla

| Pantalla | Al escanear |
|---|---|
| **Showroom** / consulta de stock | Abre la ficha de esa variante con su stock |
| **Nueva nota de pedido** | Agrega el producto al pedido (o le suma uno si ya estaba) |
| **Inventario** | Abre el panel de ajuste de esa variante — es el flujo de recepción de mercadería |
| **Ficha de producto** | Con el cursor en «Código de barras», carga el código en el campo |

Funciona con el cursor en el buscador **o** sin tocar nada: si el foco está en
un campo de texto el lector escribe ahí y el Enter dispara la búsqueda; si no,
el sistema captura las teclas por su cuenta.

### De dónde salen los códigos

Dos orígenes conviven:

1. **De fábrica.** La caja del porcelanato ya trae un EAN-13 impreso. Se
   escanea al recibir la mercadería y queda guardado tal cual. Es el caso
   ideal y no requiere imprimir nada.
2. **Interno.** Buena parte del rubro (sanitarios, griferías, accesorios)
   llega sin código. Para esos, el sistema genera un EAN-13 propio con
   **prefijo 200**, que es el rango que GS1 reserva para uso interno de un
   comercio: nunca colisiona con un código real de fábrica, porque ningún
   fabricante puede registrarse ahí.

Para asignar códigos internos a todo lo que no tenga:

```
cd backend
venv\Scripts\activate
python manage.py asignar_codigos_barras --simular   # muestra qué haría
python manage.py asignar_codigos_barras             # los asigna
```

Nunca pisa un código existente: si la caja ya trae el EAN de fábrica, ese
manda.

> ⚠️ **Correrlo en la PC servidor, no en la notebook.** La notebook es un
> espejo de solo lectura: lo que se escriba ahí se pisa en la siguiente
> sincronización.

---

## 2. Epson EcoTank L1250 — etiquetas en hoja A4

### Qué imprime

La planilla de etiquetas de código de barras para pegar en la mercadería. Es
la contraparte física del lector: sin etiqueta pegada no hay nada que escanear
en los productos que vienen sin código de fábrica.

No imprime comprobantes. No entiende ESC/POS: es una inyección de tinta con
driver GDI, y mandarle los bytes de la térmica saca páginas de basura. Todo lo
que sale por ella va como PDF.

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
5. Verificar: `python diagnostico_impresora.py` — lista las impresoras
   instaladas y avisa si el nombre del `.env` no coincide con ninguna.

### Los dos modos

- **`manual`** (recomendado y default) — el sistema arma el PDF y lo abre en el
  navegador; se imprime desde el diálogo de siempre. Anda en cualquier equipo,
  sin depender de qué visor de PDF esté instalado.
- **`auto`** — el servidor manda el PDF a la cola de Windows sin diálogo.
  Necesita que el `.pdf` tenga registrado el verbo **"printto"**, que lo
  instala Adobe Acrobat Reader y **no** trae el visor de Edge ni el de Chrome.
  Si no está, el trabajo se pierde en silencio — que es el peor modo de fallar.
  `diagnostico_impresora.py` chequea si está registrado antes de que se
  descubra a mano.

### Imprimir etiquetas

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

## 3. Problemas comunes

| Síntoma | Causa habitual |
|---|---|
| El lector no hace nada | El receptor USB no está enchufado, o el lector se quedó sin batería. Probarlo en el Bloc de notas: si ahí tampoco escribe, el problema es el aparato, no el sistema |
| Escanea pero no busca | Al lector le falta el sufijo Enter. Restablecer valores de fábrica con el código del manual |
| Dice "el código no está en el catálogo" | Ese producto todavía no tiene código cargado. Se carga desde la ficha del producto, o se le asigna uno interno con `asignar_codigos_barras` |
| Un escaneo devuelve varias opciones | Se escaneó un código de producto (no de variante) y ese producto tiene varios colores/medidas. Hay que elegir cuál |
| Las etiquetas no se leen | Se imprimieron con "ajustar a la página". Reimprimir a escala 100% |
| Las etiquetas caen fuera del troquel | La planilla comprada no es 3×8 de 70×37 mm. Ver "Formato de la planilla" |
| La L1250 no aparece | El nombre del `.env` no coincide con el de Windows. `diagnostico_impresora.py` lista los nombres reales |
