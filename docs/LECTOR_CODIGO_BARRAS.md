# Lector de código de barras — FTX LC123BH5
## Óga Porã — Sistema de Gestión Comercial

Guía de configuración y uso del lector de código de barras.

---

## 1. Qué es y cómo funciona

El **FTX LC123BH5** es un lector 2D inalámbrico (Bluetooth) con base de carga,
que también puede trabajar con cable USB. Lee tanto los códigos de barras
comunes de las cajas (los de rayitas) como los códigos QR.

Lo importante para entender el sistema: **para la computadora, el lector es un
teclado**. Cuando se aprieta el gatillo, el lector "escribe" el código en la
pantalla, igual que si alguien lo tipeara muy rápido, y termina con un Enter.

Por eso no hay que instalar ningún programa ni driver: se enchufa (o se aparea
por Bluetooth) y funciona.

El sistema aprovecha esa velocidad para distinguir el lector de una persona: si
los caracteres llegan uno atrás del otro en milisegundos, es el lector; si
llegan al ritmo de alguien escribiendo, es una persona.

---

## 2. Configuración inicial (una sola vez)

El lector se configura escaneando códigos que vienen impresos en el manualito
de la caja. Hay que dejarlo así:

| Ajuste | Valor | Por qué |
|---|---|---|
| **Modo de salida** | Teclado (HID / "keyboard") | Es el modo en que el lector escribe el código en la pantalla. Si queda en modo "puerto serie / COM virtual", el sistema no recibe nada. |
| **Sufijo** | Enter (CR) | Es lo que le avisa al sistema que el código terminó. Sin esto, el código queda a medio escribir. |
| **Prefijo** | Ninguno | Un prefijo agregaría caracteres al código y no coincidiría con lo cargado. |
| **Distribución de teclado** | Español / Latinoamericano | **El más importante y el que más problemas da.** Con la distribución en inglés, los guiones y algunos símbolos salen cambiados: un código `POR-001` puede llegar como `POR/001`. |

> Los códigos de configuración exactos están en el manual impreso que viene en
> la caja, y también en la web de FTX (`ftx.com.py` → Descargas → Manuales →
> Lector código de barra → LC123BH5).

### Cómo verificar que quedó bien

Antes de usarlo en el sistema:

1. Abrir el Bloc de notas.
2. Escanear cualquier producto.
3. Tiene que aparecer el código completo y el cursor bajar a la línea de abajo.

Si aparece con caracteres raros, falta ajustar la distribución de teclado. Si no
baja de línea, falta el sufijo Enter.

### Conexión

- **Con cable (PC de caja o depósito fijo):** se enchufa el USB y ya está.
- **Sin cable (para recorrer el depósito):** se aparea por Bluetooth con la
  computadora. La base sirve para cargarlo cuando no se usa.
- **En las tablets del showroom:** se aparea por Bluetooth como si fuera un
  teclado, desde la configuración de Bluetooth de la tablet.

---

## 3. Dónde se usa dentro del sistema

### 3.1 Cargar mercadería nueva (Productos → Nuevo producto)

En el paso de **Variantes**, cada variante tiene un campo **Código de barras**.
Se hace clic en el campo, se apunta a la caja y se dispara.

El sistema verifica al instante si ese código ya está cargado:

- **Verde, "Código disponible"** → se puede seguir.
- **Rojo, "Ese código ya está cargado en…"** → esa mercadería ya existe en el
  sistema. **No hay que cargarla de nuevo**: hay que ir a esa ficha y sumarle
  stock desde Inventario. Si se carga dos veces, el stock queda partido en dos
  fichas y el depósito ve la mitad de la mercadería en cada una.

### 3.2 Consultar stock (botón de consulta rápida)

Con la consulta rápida abierta, se apunta y se dispara: **no hace falta hacer
clic en el buscador primero**. El sistema escucha el lector en toda la pantalla.
Aparece la mercadería con su stock disponible, en cajas y en m².

### 3.3 Buscador general

El buscador de productos también encuentra por código de barras, así que se
puede escanear parado en cualquier búsqueda.

---

## 4. Mercadería sin código de fábrica

La mayoría de los porcelanatos y pisos vienen **sin código de barras impreso**.
Eso no es un problema:

- El campo se puede dejar vacío. Se busca por nombre o por código, como siempre.
- El sistema también reconoce el **SKU** y el **código propio de la variante**:
  si el proveedor pega una etiqueta con ese código, el lector sirve igual.
- Más adelante, si conviene, se le pueden imprimir etiquetas propias con la
  impresora térmica que ya está en caja (la FTX FTXP-80W sabe imprimir códigos
  de barras). Esa función todavía no está hecha en el sistema.

---

## 5. Problemas comunes

| Problema | Qué pasa | Solución |
|---|---|---|
| Escanea y no pasa nada | El lector está en modo puerto serie, no en modo teclado | Reconfigurar en modo HID/teclado con el código del manual |
| El código sale con símbolos cambiados | Distribución de teclado en inglés | Configurar teclado español/latinoamericano |
| El código queda escrito pero no busca | Falta el sufijo Enter | Configurar sufijo CR/Enter |
| Escanea dos veces el mismo código | Gatillo mantenido apretado | Soltar el gatillo entre lecturas |
| No escanea nada, no prende la luz | Batería agotada | Ponerlo en la base de carga |
| En la tablet no escribe | No está apareado o se desconectó | Volver a aparearlo desde Bluetooth |
| Dice que el código ya está usado y no debería | Otra variante lo tiene cargado, a veces una dada de baja | Buscar ese código en el buscador general para ver dónde está |

---

## 6. Nota para el técnico

- El código de barras se guarda en la **variante**, no en el producto: la
  variante es la que tiene caja física y stock propio.
- El campo es único, pero admite vacíos repetidos (se guarda `NULL`, no cadena
  vacía). Ver `Variante.save()` en `apps/productos/models.py`.
- El endpoint que consulta el lector es
  `GET /api/v1/productos/variantes/por-codigo-barras/?codigo=…`. Devuelve
  siempre `200` con `encontrado: true|false`; un código desconocido no es un
  error, porque al dar de alta mercadería nueva es lo esperado.
- La detección del lector está en
  `frontend/src/hooks/useLectorCodigoBarras.js`.

---

© 2026 ÓGA PORA E.A.S. — Acabados de Construcción.
