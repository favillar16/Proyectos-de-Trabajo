# Migración a e-Kuatia completo (software propio)

Estado al **14/09/2026**. Arranca cuando la propietaria decide conseguir el
certificado de firma electrónica.

Complementa —no reemplaza— `facturacion_electronica.md` (estado técnico de la
app `facturacion`) y `facturacion_electronica_manual_operativo.md` (cómo se
opera hoy, bajo e-Kuatia'í).

---

## 1. Qué cambia, en una línea

Hoy la cajera cobra en el sistema y **además** carga la factura a mano en el
portal del DNIT. Después de esta migración, la factura sale sola al confirmar
el cobro y el portal deja de usarse.

## 2. Decisiones ya tomadas (14/09/2026)

| Pregunta | Respuesta | Consecuencia |
|---|---|---|
| ¿Qué tipos de documento se habilitan? | **Los cinco**: Factura, Nota de Crédito, Nota de Débito, Autofactura, Nota de Remisión | El sistema hoy modela solo factura. Hay que construir los otros cuatro, y la Guía de Pruebas se multiplica por cinco (ver §5) |
| ¿Internet en el local? | **Resuelto** — servicio fluido | Se levanta el bloqueo de fondo. La cola asíncrona sigue siendo el diseño correcto igual: cubre los cortes, no la ausencia |
| ¿Trámite ante el DNIT? | **En gestión con la contadora** | La vía administrativa corre en paralelo; la técnica no la espera |

---

## 3. Lo que el certificado NO resuelve

Es el malentendido más caro de esta etapa: **tener la firma no habilita a
facturar**. Faltan tres cosas más.

### 3.1 El certificado tiene requisitos técnicos, no alcanza cualquiera

Guía de Pruebas §4.1 y Manual Técnico. Antes de pagarlo, confirmar **por
escrito con el prestador** que el certificado:

- es un **certificado cualificado de firma electrónica**, emitido por un PSC
  habilitado por el MIC (lista oficial en <https://www.acraiz.gov.py>);
- **contiene el RUC del contribuyente** emisor;
- trae la extensión **Extended Key Usage con el permiso `clientAuth`**.

Ese último punto es el que se pasa por alto. El SIFEN no solo pide firmar el
XML: hace **autenticación mutua TLS**, o sea que el certificado actúa además
como credencial de cliente. Un certificado de firma "de documentos" común no
sirve para conectarse, y eso no se descubre hasta que falla el handshake.

Formato: `.p12` / `.pfx`. **Nunca se versiona**, ni el archivo ni su clave —
van al `.env` (`SIFEN_CERT_PATH`, `SIFEN_CERT_PASSWORD`), que no está en git.

### 3.2 Hay que re-habilitarse: el timbrado actual no sirve

El timbrado vigente (18936285) está emitido bajo **"SOLUCIÓN GRATUITA"**, que
es e-Kuatia'í. Pasar a software propio es un trámite distinto en Marangatú
(guía "Habilitación como Facturador Electrónico", en
<https://www.dnit.gov.py/web/e-kuatia/guias>), que otorga:

- timbrado nuevo bajo la modalidad correcta,
- establecimiento y hasta **tres** puntos de expedición,
- acceso al **ambiente de pruebas** del SIFEN.

### 3.3 Hay que aprobar la Guía de Pruebas

El DNIT no habilita producción hasta que el sistema recorra toda la cadena en
el ambiente de test. Es la parte más grande del trabajo — §5.

---

## 4. Las tres vías, y cuál bloquea a cuál

```
VÍA ADMINISTRATIVA (contadora)          VÍA TÉCNICA (desarrollo)
  trámite de habilitación                 Fase A · sidecar + XML + firma
        │                                 Fase B · los cinco tipos de DE
        ├──→ timbrado nuevo ──────────┐   Fase C · eventos
        └──→ acceso ambiente test ──┐ │   Fase D · KuDE + QR
                                    │ │   Fase E · worker de la cola
   CERTIFICADO (prestador PSC)      │ │          │
        └──→ .p12 + clave ──────────┼─┼──────────┤
                                    ▼ ▼          ▼
                              PRUEBAS CONTRA SIFEN TEST
                                        │
                                        ▼
                              HABILITACIÓN DE PRODUCCIÓN
```

Lectura práctica: **las fases A a E se construyen sin certificado y sin
trámite**. Lo único que no se puede hacer sin ellos es probar contra el SIFEN.
Conviene que el desarrollo vaya adelante para que el día que llegue el `.p12`
lo único pendiente sea ejecutar la batería de pruebas.

---

## 5. El tamaño real de la Guía de Pruebas

Esto es lo que define el esfuerzo, y conviene tenerlo a la vista desde el
principio. Fuente: `Guia de Pruebas para e-kuatia.pdf`, §4.

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

Más, una sola vez:

| Escenario | Mínimo |
|---|---|
| Autenticación mutua contra los 7 web services, certificado **válido** | 1 c/u |
| Ídem con certificado **inválido** (se autogenera) | recomendado |
| Evento **cancelación** (rol emisor) | 5 |
| Evento **inutilización** (rol emisor) | 2 FE + 1 NCE + 1 NDE + 1 AFE |
| Eventos rol **receptor**: conformidad, disconformidad, desconocimiento, notificación de recepción, ajuste | 3 c/u |

Da del orden de **130 documentos y eventos** a generar y verificar. No es
trabajo de un día, y la mitad es construir los tipos de documento que el
sistema hoy no tiene.

### Datos del ambiente de pruebas

Los publica la misma guía y **no son los reales**:

- **CSC genérico**: `IdCSC 0001` → `ABCD0000000000000000000000000000`;
  `IdCSC 0002` → `EFGH0000000000000000000000000000`.
- La **razón social del emisor** y el **primer ítem** de cada DE de prueba
  deben decir literalmente:
  `DOCUMENTO ELECTRÓNICO SIN VALOR COMERCIAL NI FISCAL - GENERADO EN AMBIENTE DE PRUEBA`.
- El resto de los datos del emisor y del receptor **sí son los reales**, tal
  como figuran en Marangatú.

Implica que el sistema necesita poder emitir en modo prueba con esos
overrides sin ensuciar la configuración de producción — `SIFEN_AMBIENTE` ya
existe para eso, pero hoy no cambia nada más que la URL.

---

## 6. Fases técnicas

### Fase 0 — Cerrar lo que no depende de nadie ✅ (14/09/2026)

- [x] Contrastar `codigos.py` campo por campo contra el Manual Técnico V150.
      Se encontró y corrigió un error: `IDENTIDAD_PASAPORTE` estaba en `3`,
      que es el código de la **cédula extranjera**; el pasaporte es `2`. No
      había llegado a ningún DE porque esas constantes todavía no se usaban,
      pero habría salido como rechazo del SIFEN.
- [x] Completar `iTiDE` con la autofactura (`4`), que faltaba, y agregar las
      descripciones obligatorias del campo C003.
- [x] Agregar `iTiContRec` (persona física / jurídica del receptor), que el
      SIFEN exige cuando el receptor es contribuyente.
- [x] Fijar todo eso con tests que fallan si alguien cambia un código de
      memoria (`test_codigos.ContraElManualTecnicoTests`).

- [x] **Cerrado el dígito verificador del CDC**, que estaba abierto desde
      agosto — y estaba **mal**. El sistema calculaba el DV con pesos 2..9 y
      el SIFEN usa 2..11: todos los CDC que generaba el sistema tenían el
      dígito equivocado, o sea rechazo del 100% de los documentos desde el
      primero. Se descubrió revisando las librerías de referencia de la DNIT
      (§10 de este documento) y se confirmó contra el CDC de ejemplo que
      publica el propio Manual §10.1. Corregido a `PESO_MAX = 11`, con el
      ejemplo oficial como test. El detalle completo, incluido por qué el
      razonamiento original era correcto pero la conclusión no, está en
      `facturacion_electronica.md` §5.2.

**Sigue abierto:** nada de Fase 0. El `digito-verificador.pdf` del DNIT sigue
caído, pero ya no hace falta: las dos librerías de referencia y el ejemplo del
manual alcanzan y coinciden.

**Pendiente nuevo — las Notas Técnicas.** Ver §10.

### Fase A — Lado Django del sidecar ✅ (14/09/2026) · falta el proceso Node

Se construyó **todo lo que no necesita el certificado**, que es más de lo que
parecía:

| Módulo | Qué hace |
|---|---|
| `apps/facturacion/payload.py` | Traduce un cobro al JSON `params` + `data` que consume `xmlgen`. Es el núcleo de la integración. |
| `apps/facturacion/sifen_client.py` | Cliente HTTP del sidecar. Define el contrato que el proceso Node tendrá que cumplir. |
| `apps/facturacion/transmision.py` | La lógica de la cola: qué se reintenta, qué no, y qué se guarda de cada respuesta. |
| `manage.py sifen_transmitir` | El worker, para la tarea programada de Windows. |

La estructura del payload **no se inventó**: está transcrita del README de
`facturacionelectronicapy-xmlgen`, misma disciplina que se usó para cerrar el
dígito verificador. Los códigos salen de `codigos.py`, ya contrastado contra
el Manual V150.

`sifen_client.py` se escribió **antes** que el sidecar a propósito: así el
lado Node se escribe contra un contrato ya probado, en vez de al revés. Los
endpoints que tendrá que exponer son `/xml`, `/firmar`, `/qr`, `/enviar`,
`/consultar`, `/evento/<tipo>` y `/salud`.

**Falta el proceso Node en sí**: `npm install` de la suite
`facturacionelectronicapy-*` y el servidor HTTP que la envuelve, corriendo en
`127.0.0.1:8100` (`SIFEN_SIDECAR_URL` ya apunta ahí), más engancharlo al
arranque junto a daphne y Vite (`iniciar.bat` / `iniciar_servicios.ps1`).
Se puede escribir sin certificado —`xmlgen` no lo necesita— pero firmar y
transmitir no se pueden probar hasta tenerlo.

#### Dos cosas que salieron al construirlo

**1. El cuadre de los ítems no puede ser exacto, y es aritmética, no un bug.**
El SIFEN recalcula los totales desde los ítems y exige que cierren. Pero pide
el descuento **por unidad** (`dDescItem`), y acá se vende por m²: con cantidad
2,35 ningún valor de precisión finita multiplicado por 2,35 cae exactamente en
un entero de guaraníes. Se acota el residuo muy por debajo de 1 Gs (8
decimales) y se verifica en cada armado. **Cuánta diferencia tolera realmente
el SIFEN solo se puede confirmar contra su ambiente de pruebas.**

**2. Caja cobra hasta un guaraní de más, y es correcto.**
`ConfirmarPagoView` redondea el monto con `ROUND_HALF_UP`. Como los totales
con metrajes fraccionarios casi siempre tienen decimales, la mitad de las
veces el monto cobrado queda **por encima** de la suma de los ítems. La
primera versión del armador lo rechazaba como dato incoherente — habría
bloqueado la emisión de la mitad de las facturas del rubro. Ahora absorbe
hasta 1 Gs y solo rechaza diferencias materiales. Lo destapó un test al azar
que además era flaky (la generación de SKU consume del generador global de
`random`, así que `random.seed()` no alcanzaba); las dos cosas quedaron
arregladas.

### Fase B — Los cinco tipos de documento

Hoy `DocumentoElectronico` asume factura. Cada tipo nuevo trae campos
propios y reglas propias:

| Tipo | Lo que suma |
|---|---|
| Nota de Crédito | CDC del documento asociado, motivo. Es además lo que el negocio realmente necesita para anular una venta ya facturada |
| Nota de Débito | Ídem, en sentido inverso |
| Autofactura | Vendedor no contribuyente, su domicilio, naturaleza de la transacción |
| Nota de Remisión | Motivo del traslado, transportista, vehículo, origen y destino, fechas |

**Estado al 14/09/2026:**

- ✅ **Factura, Nota de Crédito y Nota de Débito.** El modelo ganó
  `documento_asociado_cdc` y `motivo_nota` (migración `0002`), con validación
  en `clean()`: una nota que no dice qué documento corrige no se guarda. Los
  ocho motivos del campo `iMotEmi` están en `codigos.MOTIVOS_NOTA`.

  La nota de crédito además **se emite de verdad**, no solo se arma: ver la
  sección propia más abajo.

- ✅ **Nota de Remisión — los datos.** `DatosTraslado` (migración `0004`)
  modela los grupos E6 y E10: motivo, responsable, fechas, tipo y modalidad
  de transporte, vehículo, transportista, conductor y direcciones de salida y
  entrega. `payload.py` ya arma el bloque completo.

  Cuelga del **pedido** y no del cobro, que es la particularidad del
  documento: una remisión describe un movimiento de mercadería, no una venta.
  Se carga al preparar la entrega. **Falta la pantalla** para cargarlo y el
  disparador que emite la nota al despachar.

- ⏸ **Autofactura.** Es la única que sigue sin poder armarse. Necesita el
  vendedor no contribuyente (nombre, documento, domicilio) y el lugar de la
  transacción, que el sistema no captura en ninguna parte. `payload.py` no la
  arma en silencio: lanza un error que nombra qué falta.

### Nota de crédito (14/09/2026)

`apps/facturacion/nota_credito.py` más los endpoints de `views.py`.

Emite la nota que revierte una factura ya emitida — por el **total**, que
cubre la anulación y la devolución completa. Una nota parcial (devolver dos
cajas de cinco) necesita elegir ítems y cantidades, o sea un modelo propio de
ítems de la nota; queda anotado y no se hizo a medias.

Lo que resuelve, más allá de armar el XML:

- **Numeración propia.** Factura y nota tienen talonarios distintos, así que
  `001-001-0000001` puede existir dos veces, una por tipo. `SecuenciaComprobante`
  ya estaba indexada por tipo de documento, así que salió gratis.
- **Reposición de stock, pero solo cuando corresponde.** Una devolución
  repone; un descuento posterior o un ajuste de precio no, porque la
  mercadería nunca volvió. Se decide por el motivo y se puede forzar (caso
  real: devuelta rota — vuelve la plata, no el stock vendible). Siempre por
  `Stock.registrar_movimiento()`, nunca tocando la cantidad a mano.
- **No se puede emitir dos veces** sobre la misma factura: sería devolver la
  mercadería dos veces.
- **No se emite sobre una factura rechazada**, que no existe como documento
  tributario: ahí lo que corresponde es corregir y emitir una factura nueva.

Hubo que cambiar una cosa del modelo: `DocumentoElectronico.pago` era
`OneToOne`, así que un cobro no podía tener factura **y** nota de crédito. Es
`ForeignKey` desde la migración `0003`, con un `UniqueConstraint` sobre
`(pago, tipo_documento)` que conserva lo que el `OneToOne` garantizaba de
verdad: no facturar dos veces la misma venta. `Pago.documento_electronico` y
`Pago.nota_credito` siguen dando el objeto en singular, así que el resto del
sistema no se enteró.

### Terminal POS (14/09/2026)

Salió de una obligación que no estaba a la vista: el grupo E620 (`gPagTarCD`)
del manual **se activa siempre** que el medio de pago es tarjeta, y pide como
mínimo la denominación y la forma de procesamiento. El sistema guardaba
`medio_pago='credito'` y nada más — o sea que **ninguna venta con tarjeta se
habría podido facturar**.

`apps/caja/pos.py` + el modelo `DatosTarjeta` + los campos en la pantalla de
cobro. Dos modos, y la diferencia importa:

| | Cómo funciona | Requisito |
|---|---|---|
| **Autónoma** (`manual`, por defecto) | La cajera copia los datos del voucher que imprime la terminal | Ninguno: funciona hoy |
| **Integrada** | El sistema le manda el monto a la terminal y recibe la autorización | SDK y acuerdo comercial con la procesadora (Bancard, Infonet, Procard) |

La segunda es una dependencia externa, como el certificado. Lo que sí se hizo
es dejarla enchufable: caja habla siempre con `obtener_terminal()` y nunca con
una marca concreta, así que agregar un driver no toca la pantalla de cobro ni
la facturación.

Dos cuidados que vale la pena no perder:

- Los datos se piden **solo** cuando la venta se factura y el SIFEN está
  prendido. Con ticket, o con el interruptor apagado, cobrar con tarjeta sigue
  siendo exactamente igual que hoy: no se le agrega un campo obligatorio a la
  cajera por una obligación que todavía no rige.
- Se valida **antes** de crear el cobro. Si falta la marca de la tarjeta es
  mejor frenar con el cliente todavía en el mostrador que emitir la factura y
  descubrirlo al otro día, cuando nadie se acuerda con qué tarjeta pagó.

### Fase C — Eventos

Cancelación, inutilización y los cuatro eventos del rol receptor. Modelo,
endpoints y UI. La inutilización es la que cierra el hueco operativo real: un
número de comprobante que se saltó hay que declararlo, no dejarlo en silencio.

### Fase D — KuDE y QR

- QR firmado con el CSC (`qrgen`) — hoy el ticket imprime el CDC pero no el QR.
- KuDE en **PDF**, que es lo que exige la guía de pruebas. El ticket térmico
  de 80 mm sirve para el mostrador, pero no es el KuDE que pide el DNIT.
  Conviene reusar el motor de `nota_pedido_doc.py`, que ya arma PDF con
  reportlab y la marca del negocio.
- Envío del KuDE por email al receptor.

### Fase E — Worker de la cola ✅ (14/09/2026)

`manage.py sifen_transmitir`, pensado para la tarea programada de Windows
igual que el sync. `--listar` muestra la cola sin transmitir, `--limite`
acota la corrida y `--forzar` permite probar con `SIFEN_HABILITADO=False`.

Lo que define que esté bien hecho es la distinción entre dos clases de fallo,
y está cubierta por tests:

- **Reintentable** — sidecar caído, timeout, corte de red, o cualquier error
  inesperado. No dicen nada sobre el documento: se reintenta hasta
  `SIFEN_MAX_INTENTOS`. Dar por rechazado un documento válido porque se cortó
  internet sería el peor error posible acá.
- **Terminal** — el SIFEN lo rechazó, o falta un dato fiscal. Reenviar lo
  mismo da lo mismo: se marca `rechazado` y se deja de intentar.

Otros dos cuidados: el XML firmado se guarda **antes** de transmitir (firmar
es lo caro y lo que toca el certificado, no hay que repetirlo si el envío se
corta), y cada documento va en su propia transacción — si la cola entera
fuera una sola, un rechazo al final revertiría envíos que el SIFEN ya aceptó.

Si el sidecar no responde, el comando sale sin recorrer la cola, para no
gastarle un intento a cada documento.

Ojo con una asimetría que ya está documentada en `CLAUDE.md`: la notebook de
la propietaria **no puede emitir**. La facturación es server-authoritative,
como el stock y la caja. El worker corre solo en la PC servidor.

### Fase F — Monitoreo y operación

Panel de admin: emitidos, aprobados, rechazados, pendientes, reintentos,
estado de conexión y **aviso de certificado próximo a vencer**. Un `.p12`
vencido frena la facturación entera y no avisa solo.

---

## 7. Datos fiscales que siguen faltando

Correr `python manage.py verificar_fiscal` desde `backend/` los lista.

| Dato | Clave en `.env` | De dónde sale |
|---|---|---|
| Vencimiento del timbrado | `FISCAL_TIMBRADO_VTO` | Del timbrado **nuevo**, no del actual |
| Código de departamento | `FISCAL_DEPARTAMENTO` | Planilla `CODIGO DE REFERENCIA GEOGRAFICA.xlsx` |
| Código de distrito | `FISCAL_DISTRITO` | Ídem |
| Código de ciudad | `FISCAL_CIUDAD` | Ídem |
| Certificado | `SIFEN_CERT_PATH` + `SIFEN_CERT_PASSWORD` | El prestador PSC |

Sobre los tres códigos geográficos: el Manual Técnico **no los trae**. La
Tabla 2.1 (§15) remite a una planilla externa,
`CODIGO DE REFERENCIA GEOGRAFICA.xlsx`, publicada en la documentación técnica
de e-Kuatia. Hay que descargarla y buscar **Caaguazú / Coronel Oviedo**. No
se inventan: un código geográfico equivocado es un rechazo del DE.

El CSC real ya está cargado (`SIFEN_CSC_ID`, `SIFEN_CSC`), pero vino con la
habilitación de Solución Gratuita — **confirmar si sigue siendo válido bajo
la modalidad nueva** o si el trámite entrega uno distinto.

---

## 8. El interruptor

`SIFEN_HABILITADO=False` sigue siendo la red de seguridad de todo esto. Con
el interruptor apagado, todo el código de arriba puede estar desplegado en la
PC de la tienda sin cambiar absolutamente nada de la operación diaria:
`emisor.emitir_para_pago()` devuelve `None` y el cobro sigue el camino de
siempre.

Se prende recién cuando estén las tres cosas: certificado instalado, pruebas
aprobadas y habilitación de producción otorgada. Ni antes, ni "para probar".

---

## 10. Revisión de las librerías que publica la DNIT (14/09/2026)

Revisado <https://www.dnit.gov.py/en/web/e-kuatia/librerias>. Publica dos, las
mismas de siempre, pero el estado de cada una cambió el análisis.

### La decisión de usar TIPS-SA queda confirmada, ahora con evidencia

En agosto se eligió TIPS-SA por un argumento de conveniencia: la PC servidor
ya tiene Node por Vite. El argumento de fondo es el mantenimiento.

| Paquete (TIPS-SA, Node/TypeScript) | Último update |
|---|---|
| `facturacionelectronicapy-setapi` | 04/08/2026 |
| `facturacionelectronicapy-xmlgen` | 29/05/2026 |
| `facturacionelectronicapy-recibo-xmlgen` | 28/03/2026 |
| `facturacionelectronicapy-qrgen` | 04/12/2025 |
| `facturacionelectronicapy-xmlsign` | 12/08/2025 |
| `facturacionelectronicapy-kude` | 11/06/2025 |
| `facturacionelectronicapy-pkcs12` | 19/12/2023 |

`xmlgen` declara Manual Técnico **V150** y soporta los **cinco** tipos de
documento, que es exactamente el alcance que se decidió pedir.

La alternativa, `rshk-jsifenlib` (Roshka, Java 8, v0.2.4), cubre bien los web
services —incluida la consulta de RUC y los eventos— pero su propio README
avisa que **la Nota Técnica N.º 14, de abril de 2023, todavía no está
soportada**. Tres años y medio de atraso en notas técnicas es motivo
suficiente para descartarla como base, más allá de que obligaría a instalar un
JRE en la PC servidor.

Conviene igual tenerla a mano como **segunda opinión**: es una implementación
independiente de las mismas reglas, y sirve para contrastar cuando algo no
cierra. De hecho fue así como se confirmó el dígito verificador.

### Pendiente nuevo: hay 27 Notas Técnicas sin revisar

Este es el hallazgo incómodo. El Manual Técnico V150 que está en `docs/` tiene
pie de página de **septiembre de 2019**. La DNIT no reemplaza el manual: le
publica **Notas Técnicas** encima, y hay **27** (NT 001 a NT 027), la última
de 2024.

El proyecto **no ha mirado ninguna**. Todo lo verificado hasta ahora —códigos,
CDC, código de seguridad— se contrastó contra el manual base. Si alguna NT
movió un código o agregó un campo obligatorio, no nos enteramos.

Hay que:

1. Bajar las 27 desde la documentación técnica y registrarlas en `docs/`.
2. Revisar cuáles tocan lo que ya está implementado (códigos, CDC, totales,
   QR) y cuáles tocan lo que falta construir.
3. Dejar anotado qué NT está aplicada, como pide el propio README de la
   especificación en `SIFEN_Specification_ES-000_ES-013`: *"No copiar
   manualmente tablas o XSD sin registrar su versión y origen"*.

El riesgo es del mismo tipo que el del dígito verificador: silencioso hasta el
día que el SIFEN rechaza todo.

### Falta también bajar la estructura XSD

La página publica `Estructura xml_DE` y `Estructura_DE xsd` (en `.rar`). El
XSD permite **validar el XML localmente antes de transmitir**, que es lo que
la Guía de Pruebas pide como primer filtro ("XML inválido → rechazo antes de
envío"). Es trabajo de Fase A.

---

## 9. Referencias

- `facturacion_electronica.md` — estado técnico de la app `facturacion`.
- `facturacion_electronica_manual_operativo.md` — cómo se opera hoy.
- `Documentacion para Facturación Electrónica/Manual Técnico Versión 150.pdf`
- `Documentacion para Facturación Electrónica/Guia de Pruebas para e-kuatia.pdf`
- Guías de habilitación: <https://www.dnit.gov.py/web/e-kuatia/guias>
- Documentación técnica: <https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica>
- Prestadores de certificación: <https://www.acraiz.gov.py>
- Librerías de referencia: <https://www.dnit.gov.py/en/web/e-kuatia/librerias>
- `facturacionelectronicapy-*` (TIPS-SA): <https://github.com/TIPS-SA>
- `rshk-jsifenlib` (Roshka): <https://github.com/roshkadev/rshk-jsifenlib>
