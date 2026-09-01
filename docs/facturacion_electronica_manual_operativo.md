# Facturación electrónica — manual operativo para los propietarios

Estado al **31/08/2026**. Complementa `docs/facturacion_electronica.md` (estado
técnico del proyecto) y `docs/carga_final/datos_fiscales.md` (de dónde salieron
los datos fiscales cargados). Este documento es para explicarle a quien cobra
o factura en el local **cómo funciona desde ahora**, no para desarrolladores.

---

## 1. Cómo quedó habilitada la facturación electrónica

Confirmado directo del PDF de habilitación del DNIT
(`docs/Documentación para Facturación Electrónica/TIMBRADO FACTURADOR
ELECTRONICO OGA PORA EAS.pdf`, aprobado 26/08/2026):

> **MODALIDAD DE EMISIÓN DE DOCUMENTOS ELECTRÓNICOS: SOLUCIÓN GRATUITA**

Es lo que se conoce como **e-Kuatia'i**. Consecuencia práctica, sin vuelta:

- **La factura legal se carga a mano en el portal de Marangatú.** El sistema
  de la tienda no tiene forma de emitirla solo — esa modalidad no tiene API.
- Solo cambiaría si el negocio se re-habilita en el futuro con software propio
  (e-Kuatia completo), que normalmente tiene costo (certificado digital de
  firma). No es el caso hoy.

---

## 2. Cómo cobrar, día a día

**Venta sin factura (la mayoría):** Ticket normal, como siempre. Nada cambió.

**Venta con factura (el cliente pide poner su RUC):**

1. En caja, elegir **"Factura"** en vez de "Ticket".
2. Cargar RUC y razón social del cliente (obligatorio para poder cobrar así).
3. Confirmar el pago.
4. Sale un papel que dice únicamente **"COMPROBANTE DE VENTA"** — sin ninguna
   otra leyenda: a propósito no dice "factura legal" ni trae timbrado, esa
   factura legal todavía no existe hasta que se carga en el portal. Es
   información para el cliente y control interno, no el documento fiscal. La
   impresora térmica de la tienda es blanco y negro, así que el papel no lleva
   sombreados ni colores.
5. En la pantalla, debajo del comprobante, aparece un cuadro
   **"Datos para cargar en e-Kuatia'í (portal DNIT)"** con cliente, RUC,
   condición de venta, cada ítem (con su **código interno/SKU**, cantidad y
   precio unitario) y el desglose de IVA por tasa (10% / 5% / exento) ya
   calculado. Cada dato tiene su **propio botón de copiar** al lado — no hay
   un solo bloque de texto para recortar: se copia un campo, se pega en el
   campo correspondiente del formulario de e-Kuatia'í, y se sigue con el
   siguiente. El código interno de cada ítem es el mismo con el que está
   cargado el catálogo en e-Kuatia'í (`Catálogo de Productos`), así que sirve
   para pegarlo directo en el buscador de ítems del portal en vez de escribir
   la descripción a mano.
6. Debajo, el botón **"Generar factura electrónica"** abre e-Kuatia'í
   (`https://ekuatia.set.gov.py/ekuatiai/`) en una pestaña nueva del navegador
   o la tablet — ahorra escribir la dirección a mano. El sistema no inicia
   sesión ni envía nada: solo abre la página, el usuario y contraseña los
   pone quien factura.
7. Con e-Kuatia'í ya abierto, ir copiando y pegando cada dato del cuadro en
   el campo que corresponda del formulario del portal. Reemplaza transcribir
   todo a mano desde el papel.

---

## 3. Las credenciales del portal e-Kuatia'í / Marangatú

El usuario y la contraseña (RUC + Clave de Acceso) **no van a ningún archivo
del sistema** — el software no los usa ni los guarda, porque no hay ninguna
llamada automática al portal. Quedan a cargo de quien cargue las facturas.

Guardarlos en un lugar seguro (gestor de contraseñas), nunca en un papel a la
vista en el mostrador.

El **código de seguridad (CSC)** que vino en el mismo PDF de habilitación ya
está cargado en `backend\.env` del sistema — eso sí lo usa el software, pero
solo el día que se pase a software propio con API. Hoy no hace nada.

---

## 4. Lo que queda pendiente (no urgente)

Solo importa si en el futuro deciden pasar a facturar con software propio
(e-Kuatia completo, normalmente pago). Mientras sigan en Solución Gratuita,
nada de esto bloquea la operación diaria:

| Dato | Para qué serviría |
|------|--------------------|
| Códigos SIFEN de departamento / distrito / ciudad | Armar el XML del documento electrónico |
| Certificado digital de firma (.p12) | Firmar el XML — lo emite un prestador habilitado, normalmente con costo |

Correr `python manage.py verificar_fiscal` desde `backend/` muestra en
cualquier momento qué falta y qué ya está.

---

## 5. Pregunta para la contadora (no la resuelve el software)

El timbrado está **vigente desde el 23/06/2026**. Confirmar con la consultora
contable (contacto registrado en la habilitación:
`consultoracontablemymcov@gmail.com`):

- Desde cuándo corre, en la práctica, la obligación de facturar por el portal.
- Qué exige el **art. 2° incs. b y c de la RG DNIT N.º 19/2024**, que la propia
  aprobación de la DNIT señala como paso siguiente.

Es una decisión de cumplimiento tributario, no algo que el sistema pueda
decidir por su cuenta.

---

## 6. Antes de dar el trabajo por cerrado

Probar una vez en la PC real de la tienda (no en la máquina de desarrollo):

1. Cobrar una venta de prueba eligiendo **"Factura"**.
2. Confirmar que el "COMPROBANTE DE VENTA" sale bien en la impresora térmica.
3. Probar los botones de copiar de al menos un par de campos (por ejemplo el
   RUC del cliente y el código de un ítem) en el navegador o tablet que
   realmente usa la cajera — la primera vez, el navegador puede pedir permiso
   para copiar al portapapeles.
4. Probar el botón **"Generar factura electrónica"**: debe abrir
   `https://ekuatia.set.gov.py/ekuatiai/` en una pestaña nueva. En la tablet,
   confirmar que el navegador no bloquea la pestaña emergente.
5. Cargar esa venta de prueba en e-Kuatia'í siguiendo los datos copiados, para
   confirmar que alcanzan y están en el orden que pide el portal.

---

## Referencias

- `docs/facturacion_electronica.md` — estado técnico completo del proyecto.
- `docs/carga_final/datos_fiscales.md` — de dónde salió cada dato fiscal cargado.
- Portal e-Kuatia'í (carga de la factura): <https://ekuatia.set.gov.py/ekuatiai/>
- Portal Marangatú: <https://marangatu.set.gov.py>
- Portal e-Kuatia (información general): <https://www.dnit.gov.py/en/web/e-kuatia>
