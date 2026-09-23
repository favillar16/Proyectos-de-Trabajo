# Qué falta para elaborar y remitir una factura de verdad

**Relevado el 20/09/2026.** Este documento junta, en un solo lugar, todo lo
que falta para que el sistema emita una factura electrónica y la transmita al
SIFEN. La idea es que el día que lleguen los documentos que están en trámite
no haya que volver a investigar nada: acá está qué se hace, en qué orden y
qué bloquea a qué.

El detalle técnico de cada pieza ya construida está en
`docs/migracion_ekuatia.md`. Esto es la lista de lo que **falta**.

---

## 1. En una línea

El camino **síncrono** está completo: el sistema arma el XML, lo firma,
genera el QR, lo transmite y guarda la respuesta. Lo que falta se divide en
tres cosas muy distintas entre sí: **documentos que no dependen de nosotros**,
**tres web services y dos tipos de documento que no están construidos**, y la
**batería de pruebas** que la DNIT exige antes de habilitar producción.

---

## 2. Bloque A — Lo que hay que conseguir (no es trabajo de código)

Es lo que está trabando todo lo demás.

### A.1 Certificado cualificado de firma electrónica

**El requisito que más se subestima.** No sirve cualquier certificado de
firma: el SIFEN hace **autenticación mutua TLS 1.2**, así que el certificado
funciona además como credencial de cliente. Tiene que cumplir las tres cosas
a la vez, y conviene pedirlas **por escrito al prestador antes de pagar**:

1. Ser un **certificado cualificado de firma electrónica**, de un Prestador
   Cualificado de Servicios de Confianza (PCSC) habilitado por el MIC. La
   Guía de Pruebas lo ata al **art. 43 de la Ley N.º 6822/2021**.
2. **Contener el RUC** del contribuyente emisor.
3. Traer la extensión **Extended Key Usage con el permiso `clientAuth`**.

El punto 3 es el que se pasa por alto: un certificado de "firma de
documentos" común firma bien el XML pero **no puede conectarse**, y eso no se
descubre hasta que falla el handshake TLS.

Formato **`.p12` / `.pfx`**. Vigencia habitual de 2 a 3 años.

**PCSC habilitados** (registro oficial de AC Raíz,
<https://acraiz.gov.py/html/Certif_1PrestaServ.html>):

| Prestador | Sitio |
|---|---|
| VIT S.A. | vitsa.com.py · efirma.com.py |
| CODE 100 S.A. | code100.com.py |
| Documenta S.A. | digito.com.py |
| Ministerio del Interior | identificaciones.gov.py |
| Confirma S.A. | confirma.com.py |
| ITTI S.A.E.C.A. | secure.itti.digital |
| SOS Tecnología y Gestión de Información Ltda. | sosdocs.com.py |

> ⚠️ **El certificado gratuito que la DNIT entrega en sus oficinas es para
> e-Kuatia'í**, la solución gratuita. Para software propio hay que comprarlo
> a un PCSC. No son el mismo trámite ni el mismo certificado.

**Dónde va:** el `.p12` se guarda **fuera del repositorio** y su ruta y clave
van al `.env` (`SIFEN_CERT_PATH`, `SIFEN_CERT_PASSWORD`), que no está en git.
Hoy esas variables apuntan a un certificado **autofirmado de prueba** que
sirve para ejercitar la mecánica de firma, no para facturar.

### A.2 Timbrado nuevo, bajo la modalidad correcta

El timbrado vigente (**18936285**) está emitido bajo **"SOLUCIÓN GRATUITA"**,
que es e-Kuatia'í. **No sirve para software propio.** Hay que hacer el
trámite de *Habilitación como Facturador Electrónico* en Marangatú (guía en
<https://www.dnit.gov.py/web/e-kuatia/guias>), que otorga:

- timbrado nuevo bajo la modalidad correcta,
- un establecimiento y hasta **tres** puntos de expedición,
- **acceso al ambiente de pruebas** del SIFEN.

Ese último ítem es el que destraba el Bloque C: sin el trámite no hay contra
qué probar.

### A.3 Confirmaciones menores, pero que entran en el CDC

- **Establecimiento y punto de expedición.** Hoy están en `001` / `001`, que
  es el default. Salen del trámite de A.2 y hay que confirmarlos: forman
  parte del CDC, y equivocarlos invalida todos los comprobantes emitidos.
- **Fin de vigencia del timbrado.** Hoy sin definir. Normal en timbrado
  electrónico, pero conviene confirmarlo en Marangatú.
- **Código de ciudad** (hoy `2886`, CNEL. OVIEDO). Se dedujo de la tabla
  geográfica; vale confirmarlo contra el sidecar (`POST /geografia`).

### A.4 La leyenda de la RG 41/2014 — solo bloquea la nota de remisión

La NT 007 volvió obligatorio el campo B006 `dInfoFisc` en la nota de
remisión, con la leyenda del art. 3 inc. 7 de la RG 41/2014. El texto de ese
inciso es:

> «La indicación expresa de "Mercaderías con cadena de Frío"; "Carga
> Peligrosa", u otro dato de relevancia similar, cuando se transporten
> productos que cumplan algunas de estas características.»

Es **condicional**, y los pisos y sanitarios no son ni una cosa ni la otra.
Qué se escribe en un campo obligatorio cuyo supuesto no se cumple es pregunta
para la contadora. Va en `FISCAL_LEYENDA_REMISION` del `.env`. **No bloquea
la factura**, solo la remisión.

---

## 3. Bloque B — Construido el 20/09/2026

Todo esto se hizo en una pasada, porque nada de acá depende del certificado
ni del trámite. Queda listo para ejercitar el día que haya contra qué probar.

### B.1 Los tres web services que faltaban ✅

La Guía de Pruebas §3 exige probar autenticación mutua contra **todos** los
servicios web. Esta es la lista oficial contra lo que hay hoy:

| Web service | Librería DNIT | Sidecar | Django | Estado |
|---|---|---|---|---|
| WS Sincrónico | `recibe` | `/enviar` | `transmitir()` | ✅ |
| WS Asincrónico (lote) | `recibeLote` | `/enviarLote` | `transmitir_lote()` | ✅ **nuevo** |
| WS Consulta Resultado Lote | `consultaLote` | `/consultarLote` | `consultar_lote()` | ✅ **nuevo** |
| WS Consulta DE | `consulta` | `/consultar` | `consultar()` | ✅ |
| WS Recepción de evento | `evento` | `/evento/<tipo>` | emisor y receptor | ✅ |
| WS Consulta RUC | `consultaRUC` | `/consultarRuc` | `ConsultaRucView` | ✅ **nuevo** |

**El flujo del lote es lo que tuvo trabajo, no las rutas.** El asincrónico no
es "lo mismo pero más rápido": el SIFEN **no contesta si aprobó**, contesta un
número de lote (`dProtConsLote`) y procesa después. Son dos viajes, y entre
uno y otro hay que guardar ese número — si se pierde, los documentos quedan
transmitidos y huérfanos. De ahí el modelo `LoteTransmision` y el campo
`DocumentoElectronico.lote`.

Dos decisiones que conviene no deshacer:

- **El resultado se reparte por CDC, no por orden de envío.** El SIFEN no
  garantiza devolverlos en el mismo orden en que se mandaron.
- **Un documento que no se puede firmar no frena al lote**: se marca
  rechazado, o queda para el próximo, y los otros 49 salen igual.

`interpretarLote()` en el sidecar no recorre una ruta fija de la respuesta:
busca en el árbol cualquier nodo con un CDC y un `dEstRes`. El XSD que define
la forma exacta no está versionado (ver B.4), así que se prefirió algo que
aguante que el SIFEN anide distinto. **Cuando se baje el XSD, vale
contrastarlo.**

### B.2 Los dos tipos de documento que faltaban ✅

| Tipo | XML | Emisión | Estado |
|---|---|---|---|
| Factura (1) | ✅ | `emisor.py` | ✅ |
| **Autofactura (4)** | ✅ `_bloque_autofactura` | `autofactura.py` | ✅ **nuevo** |
| Nota de crédito (5) | ✅ | `nota_credito.py` | ✅ (falta la **parcial**) |
| **Nota de débito (6)** | ✅ | `nota_debito.py` | ✅ **nuevo** |
| Nota de remisión (7) | ✅ | `remision.py` | ✅ (falta la leyenda de A.4) |

**La nota de débito** resultó menos trivial de lo previsto. Se creía que
bastaba clonar la de crédito, pero su monto es un importe **nuevo** —un
interés, un flete— y no una redistribución de la venta: reusar los ítems del
pedido daba descuento negativo y el documento no se armaba. Lo destapó un
test. Ahora `_items_nota_debito()` genera **un solo renglón**, descrito por el
motivo declarado, que es lo que un débito es en la práctica.

Tampoco acepta los motivos de devolución: devolver mercadería baja lo que el
cliente debe, no lo sube. Para eso está la nota de crédito.

**La autofactura** obligó a un cambio estructural: es el único tipo que no
documenta una venta sino una **compra** a alguien sin RUC, así que no cuelga
de un cobro. `DocumentoElectronico.pago` pasó a admitir null, y sus ítems se
escriben a mano (`ItemAutofactura`) porque lo comprado no está en el catálogo.
No mueve inventario a propósito.

### B.3 Los eventos del receptor ✅

`eventos_receptor.py` más el modelo `EventoReceptor`. Los cuatro: conformidad
(total o parcial), disconformidad, desconocimiento y notificación de
recepción.

Es un módulo aparte de `eventos.py` y no un tipo más porque **el documento no
es nuestro**: lo emitió un proveedor y lo único que tenemos es su CDC. La
forma de `data` de cada uno está verificada contra `jsonEventoMain.service.js`
de la librería, incluido el detalle de que las fechas tienen que medir
**exactamente 19 caracteres** — la librería lo valida por largo, así que un
`isoformat()` con microsegundos lo rechaza.

### B.4 Validación contra el XSD ✅ (el mecanismo)

`apps/facturacion/esquema.py`, enganchado en `_firmar()` — o sea que cubre el
camino sincrónico y el de lote a la vez. Valida **antes de firmar**, porque
firmar cuesta abrir el `.p12` y no tiene sentido firmar algo que ya se sabe
que vuelve rechazado.

**Es opcional y está apagado**, y le faltan dos cosas que no son código:

1. **El XSD**, que la DNIT publica en un `.rar` y no está versionado acá. Se
   descomprime donde sea y se apunta `SIFEN_XSD_PATH` del `.env`.

   ⚠️ **El archivo que la página publica como «Estructura_DE xsd» es de 2018
   y no sirve** (probado el 23/09/2026): no declara `targetNamespace` y sus
   grupos se llaman `gCiODE`/`gDTim`/`gCamOC`, que no existen en la V150.
   Apuntárselo habría hecho rechazar **todos** los documentos. Hay que pedir
   el juego de la V150 por nombre —`siRecepDE_v150.xsd`, `DE_v150.xsd`,
   `Evento_v150.xsd`, `xmldsig-core-schema-v150.xsd` y los demás, 19 en
   total según el índice del Manual— por el canal del §5 de la Guía. Desde
   esa fecha `esquema.py` revisa el namespace y descarta el que no sea el
   del SIFEN, así que apuntarle el equivocado ya no rompe nada: avisa en el
   log y sigue sin validar. Detalle completo en `docs/migracion_ekuatia.md`.
2. **La librería `xmlschema`**, en `requirements-dev.txt` y no en
   `requirements.txt` a propósito: hace falta para la campaña de pruebas, no
   para vender, y este sistema corre en una PC que alguien va a reinstalar.

Sin cualquiera de las dos, no valida y lo dice una vez en el log. **Nunca
frena una emisión por no poder validar**: no poder chequear no es lo mismo que
estar mal.

### B.5 El envío de la factura por correo — pendiente, y no por código

**El dato ya se captura** (campo `cliente_email` en caja, campo D216 del DE).
Lo que falta **no es programación**: hay que decidir **si lo manda el SIFEN al
aprobar el DE o si lo mandamos nosotros** con el KuDE adjunto. Conviene
confirmarlo con la contadora o en el soporte del DNIT antes de escribir código
para algo que quizá ya hace el organismo.

### B.6 Las pantallas ✅ (20/09/2026)

`FacturacionPage` pasó de una columna con paneles apilados a **cuatro
secciones**, agrupadas por *la pregunta que contestan* y no por
funcionalidad — que es lo que evita que se encimen:

| Sección | Contesta |
|---|---|
| **Emitidos** | ¿Qué emitimos y en qué estado está? (incluye los números sin usar, que son de nuestra numeración) |
| **Transmisión** | ¿Qué mandamos y qué no llegó a mandarse? (lotes + ventas sin documento) |
| **Autofactura** | Lo único que se **crea** desde esta pantalla |
| **Recibidos** | Documentos que **otros** nos emitieron |

Separar "Emitidos" de "Recibidos" no es cosmético: en una sola lista, la
columna "estado" habría significado dos cosas distintas según la fila —el
estado de **nuestro** documento ante la DNIT, o el de **nuestra declaración**
sobre el documento de un tercero.

La paleta y los formateadores se movieron a
`components/facturacion/estilos.js` en vez de copiarse en cada pantalla
nueva: son partes de la misma vista y tres copias del mismo marrón terminan
distintas.

**El selector geográfico** (departamento → distrito → ciudad) habilita cada
nivel cuando el anterior tiene valor, así no se puede armar una combinación
imposible — elegir un distrito de otro departamento es de los errores que más
rechazos genera. Los datos salen de `GET /facturacion/geografia/`, que los
lee de la librería de la DNIT a través del sidecar: **no necesita certificado
ni internet**, es un archivo de la librería.

> De paso, esa tabla **confirmó los códigos del `.env`** que figuraban como
> "por confirmar" en A.3: departamento **6** = CAAGUAZU, distrito **61** =
> CNEL. OVIEDO, ciudad **2886** = CNEL. OVIEDO. Coinciden.

En el formulario de eventos del receptor, los campos cambian según el tipo
elegido: un formulario con ocho campos de los que sirven tres invita a llenar
cualquier cosa, y el SIFEN rechaza lo que sobra igual que lo que falta. La
pantalla además marca cuáles son **conclusivos** y cuáles **informativos**,
que es lo que decide cuál usar y no se deduce del nombre.

**Un bug que apareció acá y no en los tests del módulo:** el campo
`datetime-local` manda texto sin zona horaria. El evento se registraba bien
pero la transmisión moría con `'str' object has no attribute 'utcoffset'` —
un error que no dice nada sobre la fecha— y guardarla naive la corría cuatro
horas. Lo tapaba que `transmitir()` nunca lanza. Corregido en
`_a_datetime()` / `_fecha_sifen()`, con test de regresión.

### B.7 Los plazos del Manual ✅ (23/09/2026)

Cuatro reglas que el Manual fija y el sistema no aplicaba. Detalle y motivos
en `docs/migracion_ekuatia.md` → «Los plazos del Manual, y cuáles bloquean».

| Regla | Dónde | Qué hace |
|---|---|---|
| 45 días para un evento del receptor | Tabla J, filas 10–13 | **Bloquea** |
| Cancelar primero el último DTE de la cadena | Tabla J, fila 1 | **Bloquea** |
| Vigencia del timbrado al inutilizar | Tabla J, fila 2 | **Bloquea** |
| 15 primeros días del mes siguiente, inutilización | Tabla J, fila 2 | Avisa |
| 15 días para corregir un evento del receptor | Tabla K | Solo se calcula |

Importa para el Bloque C: de estas cinco, cuatro evitan rechazos durante la
campaña de pruebas. Un evento fuera de plazo antes se guardaba, se transmitía
y volvía rechazado, gastando un documento de la batería.

### Lo que sigue abierto, y por qué

- **El evento de ajuste del receptor** (Tabla K) — ver el recuadro del §4. Es
  el que además es escenario obligatorio de la campaña de pruebas.
- **Nota de crédito parcial** (devolver 2 cajas de 5). Necesita un modelo de
  ítems de la nota y elegir cantidades; está anotado desde antes.
- **El evento de nominación** (NT 014/015/027).
- **La pantalla de la nota de débito.** El endpoint y los motivos están; se
  emite por API. Va en el detalle de un documento de la sección Emitidos,
  al lado de "Nota de crédito" — no es una sección nueva.

---

## 4. Bloque C — La batería de pruebas

No se habilita producción hasta recorrer toda la cadena en el ambiente de
test. Fuente: `Guia de Pruebas para e-kuatia.pdf` (**febrero/2026**), §4.

Por **cada uno** de los cinco tipos de documento:

| Escenario | Mínimo |
|---|---|
| WS Sincrónico — aprobados (factura: mínimo 2 ítems) | 5 |
| WS Sincrónico — rechazados, con errores distintos | 5 |
| WS Asincrónico (lote) — aprobados | 5 en 1 lote |
| WS Asincrónico (lote) — rechazados | 5 en 1 lote |
| WS Consulta DTE | 3 |
| Consulta por código QR | 2 |
| KuDE en PDF | 1 |

Dos detalles del texto que la tabla de arriba comprime y conviene no perder:

- El mínimo del lote es 5, pero la Guía **recomienda 30 a 50 DE por lote** en
  los aprobados y **3 a 5** en los rechazados. El techo lo pone el Manual, no
  la Guía: los eventos van en **lotes de hasta 15** (especificaciones tras la
  Tabla J).
- Pide **una conexión distinta por cada tipo de DE**, no los cinco por la
  misma.

Más, una sola vez:

| Escenario | Mínimo |
|---|---|
| Autenticación mutua contra cada web service, certificado válido | 1 c/u |
| Ídem con certificado **inválido** | recomendado (hay `sidecar/herramientas/certificado_prueba.sh`) |
| Evento cancelación (emisor) | 5 |
| Evento inutilización (emisor) | 2 FE + 1 NCE + 1 NDE + 1 AFE |
| Eventos del receptor (4 tipos) | 3 c/u |
| **Ajuste de un evento previo (receptor)** | **3** |

Del orden de **133 documentos y eventos**.

> ⚠️ **El «Ajuste del Evento» se nos había pasado** (detectado el 23/09/2026).
> Es la quinta fila del rol RECEPTOR en el §4.3 de la Guía, y **no** es la
> «Devolución y Ajuste de precios» del §11.1.3 del Manual —esa es un evento
> *automático* de SIFEN, disparado al aprobarse una nota de crédito o débito,
> que no se transmite—. Lo que la Guía pide es la **Tabla K: Correcciones de
> los eventos del Receptor**: corregir un evento elegido por equivocación,
> hasta 15 días del registro del primero y **una sola vez por evento**, con
> justificativa en texto libre. Hay además una matriz de qué evento puede
> seguir a cuál.
>
> No está implementado y **no alcanza con programarlo**: `xmlgen` no trae
> generador para él (sus eventos son cancelación, inutilización, conformidad,
> disconformidad, desconocimiento, notificación, nominación y actualización
> de datos de transporte). Hay que averiguar con la Mesa de Ayuda si el
> ajuste es un tipo propio o es reenviar el evento corregido. El plazo sí
> está calculado y probado (`eventos_receptor.se_puede_corregir()`).

### Datos del ambiente de pruebas

- **CSC genérico**: `IdCSC 0001` → `ABCD0000000000000000000000000000`;
  `IdCSC 0002` → `EFGH0000000000000000000000000000`. Se cargan en
  `SIFEN_CSC_ID` / `SIFEN_CSC` cuando arranquen las pruebas; hoy está el real.
- La **razón social del emisor** y el **primer ítem** de cada DE de prueba
  deben decir literalmente
  `DOCUMENTO ELECTRÓNICO SIN VALOR COMERCIAL NI FISCAL - GENERADO EN AMBIENTE DE PRUEBA`.
  ✅ Ya implementado: `payload.construir()` lo aplica cuando
  `SIFEN_AMBIENTE != 'produccion'`, y hay tests de que en producción **no** lo
  ponga.
- El resto de los datos del emisor y del receptor **son los reales**, como
  figuran en Marangatú.

Soporte y envío de archivos para verificación:
<https://servicios.set.gov.py/eset-publico/EnvioMailSetIService.do>

---

## 5. El orden: qué bloquea a qué

```
  A.2 trámite Marangatú ──┬──→ timbrado nuevo ────────────┐
                          └──→ acceso ambiente test ──┐   │
                                                      │   │
  A.1 certificado PCSC ───────────────────────────────┤   │
                                                      ▼   ▼
  B.1 · B.2 · B.3 · B.4  (no dependen de nada)  →  BLOQUE C
        se pueden construir hoy                    pruebas
                                                      │
                                                      ▼
                                          habilitación de producción
```

**Lectura práctica:** todo el Bloque B se puede construir **sin certificado y
sin trámite**. Conviene que vaya adelante, para que el día que llegue el
`.p12` lo único pendiente sea correr las pruebas y no empezar a programar.

---

## 6. El día del cambio

Cuando estén el certificado, el timbrado y las pruebas aprobadas:

1. `.env`: `SIFEN_CERT_PATH` y `SIFEN_CERT_PASSWORD` al certificado real;
   `FISCAL_TIMBRADO`, `FISCAL_TIMBRADO_INICIO`, `FISCAL_ESTABLECIMIENTO` y
   `FISCAL_PUNTO_EXPEDICION` a los nuevos; `SIFEN_CSC_ID`/`SIFEN_CSC` a los
   reales; `SIFEN_AMBIENTE=produccion`.
2. `python manage.py verificar_fiscal` — tiene que dar todo OK.
3. Reiniciar el sidecar y daphne.
4. `SIFEN_HABILITADO=True`. **Este es el interruptor**: recién acá el sistema
   toma números oficiales y calcula CDC de verdad.
5. Programar `manage.py sifen_transmitir` en el Programador de tareas de
   Windows, igual que el sync.
6. Mirar el panel de Facturación los primeros días — en particular
   **"Ventas facturadas sin documento electrónico"**, que con el SIFEN
   prendido deja de ser una lista informativa y pasa a ser una alarma.

> ⚠️ **No prender `SIFEN_HABILITADO` antes de tener el certificado.** El
> sistema empezaría a consumir el correlativo oficial e imprimiría CDC que no
> existen en el portal.

---

## 7. Fuentes

- `docs/Documentacion para Facturación Electrónica/Guia de Pruebas para e-kuatia.pdf` (feb/2026)
- `docs/Documentacion para Facturación Electrónica/Manual Técnico Versión 150.pdf`
- Las 27 Notas Técnicas, en `docs/.../Notas Tecnicas/`
- Registro de PCSC: <https://acraiz.gov.py/html/Certif_1PrestaServ.html>
- Guías de habilitación: <https://www.dnit.gov.py/web/e-kuatia/guias>
- Documentación técnica: <https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica>
- Librerías de referencia: <https://www.dnit.gov.py/en/web/e-kuatia/librerias>
