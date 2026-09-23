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

> 📋 **Para trabajar el día que lleguen los documentos**, ver
> `docs/habilitacion_sifen_checklist.md`: junta en un solo lugar lo que falta
> conseguir, lo que falta construir y la batería de pruebas, con el orden de
> dependencias. Este documento sigue siendo el detalle técnico de cada pieza.

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
        ├──→ timbrado nuevo ──────────┐   Fase C · eventos ✅
        └──→ acceso ambiente test ──┐ │   Fase D · KuDE + QR ✅
                                    │ │   Fase E · worker de la cola ✅
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

**Resuelto el 16/09/2026.** `payload.construir()` aplica la leyenda cuando
`SIFEN_AMBIENTE != 'produccion'`, en los dos lugares que pide la guía, y no
toca ningún importe. Tiene tests en los dos sentidos
(`test_ambiente_pruebas.py`): que en test la ponga y que en **producción no la
ponga**, que es el que de verdad importa — una factura real con la leyenda de
prueba sería un problema tributario.

Un detalle que costó encontrar: **esto no lo hace la librería**. `xmlgen`
tiene una opción `config.test`, y parece que sirviera para esto, pero no marca
el documento de ninguna manera. Es andamiaje que quedó de la NT 013 (2023),
cuando una fórmula del IVA entró en test un mes antes que en producción; las
dos fechas ya pasaron y hoy los dos caminos calculan igual
(`jsonDteItem.service.js`, bloque "Vigencia en test y produccion"). Confiar en
el nombre de la opción habría mandado los ~130 documentos de la habilitación
sin la leyenda.

El CSC genérico de pruebas se carga en el `.env` (`SIFEN_CSC_ID` /
`SIFEN_CSC`) cuando llegue el momento de las pruebas; hoy está el real.

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

### Fase A — Sidecar ✅ (14/09/2026 lado Django · 16/09/2026 proceso Node)

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

**El sidecar está construido** (16/09/2026). Vive en `sidecar/`, se levanta
con `npm start` y escucha en `127.0.0.1:8100`. `iniciar.bat` lo arranca junto
a daphne y Vite, `detener.bat` lo baja y `setup.bat` corre su `npm install`.
22 tests propios (`npm test`). Ver `sidecar/README.md`.

La cadena **payload → sidecar → XML** está verificada de punta a punta contra
un cobro real de la base, con `manage.py sifen_probar`. Lo único que no se
puede probar sin el `.p12` es firmar y transmitir.

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
  Se carga al preparar la entrega.

  **La pantalla ya está (16/09/2026).** Vive en el panel del pedido, dentro de
  Pedidos: una fila «Datos del traslado» que aparece en todos los pedidos —gris
  cuando falta, verde con el resumen cuando está cargado— y abre un formulario
  lateral. Lo carga depósito, vendedor, encargada o admin; el cajero no la ve.

  Tres decisiones del formulario que conviene no deshacer:

  · **Abre lleno.** El backend manda los valores sugeridos del negocio —traslado
    por venta, camión propio, terrestre, dirección del local— y solo hay que
    poner chapa, kilómetros y dirección de entrega. No es comodidad: cuanto
    menos haya que elegir, menos chances de elegir mal un código que después
    rechaza el SIFEN.
  · **Lo secundario está plegado.** De los veinticinco campos, cinco se llenan
    siempre. El transportista tercerizado y las direcciones desglosadas van en
    secciones colapsadas; mostrarlos todos de entrada haría que la pantalla se
    lea como un trámite y se llene de cualquier manera.
  · **La validación corre en el servidor, no en el formulario.** Las reglas que
    evitan el rechazo —vehículo identificable, kilómetros de la NT 010,
    dirección de entrega— viven en `DatosTraslado.clean()`, y el serializer lo
    llama a mano: `ModelSerializer` **no** lo ejecuta solo. Sin ese paso la
    pantalla dejaría guardar un traslado que después no se puede emitir, y el
    error aparecería recién en el worker.

  Endpoints: `GET/PUT/DELETE /api/v1/facturacion/pedidos/<id>/traslado/` y
  `GET /api/v1/facturacion/opciones-traslado/`, que sirve las tablas de la DNIT
  para que el frontend no tenga su propia copia. 18 tests
  (`test_api_traslado.py`). El `DELETE` se niega si la remisión ya se emitió:
  ahí el documento existe ante el DNIT y para deshacerlo hace falta el evento
  de cancelación.

- ✅ **Nota de Remisión — la emisión (20/09/2026).** `apps/facturacion/remision.py`
  es el disparador que faltaba: hasta acá el tipo 7 solo aparecía asignado a
  mano en los tests, y ningún código de producción creaba el documento.
  `emitir(pago, usuario=...)` toma el número de la secuencia del tipo 7 —que
  corre aparte de la de facturas—, calcula el CDC, copia el timbrado y el
  receptor de la factura cuando existe, y deja el DE en `pendiente` para el
  worker. Referencia la factura por su CDC; el SIFEN además registra esa
  vinculación por su cuenta al aprobar (Manual §11.3, ejemplo 2).

  Endpoints `GET/POST /api/v1/facturacion/pedidos/<id>/remision/` y el botón
  en el panel del pedido, debajo de la fila del traslado: **Emitir** cuando no
  existe, **KuDE** cuando sí. 18 tests (`test_emision_remision.py`), incluida
  la descarga del KuDE, que es el papel que viaja con la mercadería.

  **Es un botón y no un efecto del cobro, y eso es normativo, no una decisión
  de diseño.** Ver la sección «¿Cada venta lleva remisión?» más abajo.

  Valida antes de tomar el número —traslado cargado, kilómetros de la NT 010,
  receptor identificado por la NT 023, que no haya otra ya emitida— porque un
  correlativo que avanza y después falla deja un hueco que hay que declarar
  por el evento de inutilización.

  **No toca stock**: la mercadería ya se descontó al confirmar el pago.

- ⏸ **Autofactura.** Es la única que sigue sin poder armarse. Necesita el
  vendedor no contribuyente (nombre, documento, domicilio) y el lugar de la
  transacción, que el sistema no captura en ninguna parte. `payload.py` no la
  arma en silencio: lanza un error que nombra qué falta.

### ¿Cada venta lleva nota de remisión? (20/09/2026)

**No.** La remisión no se ata a la venta sino al **traslado**, y hay ventas que
no generan ningún traslado a cargo del local. Es la pregunta que decide si el
sistema la emite solo al cobrar o si la deja como una acción aparte, y la
respuesta está en la norma, no en el Manual Técnico —que solo define la
estructura del XML.

**Decreto 6.539/2005, art. 30** (el reglamento que el propio Manual V150 §4.2
cita como base legal de las notas de remisión):

> «Son los documentos que sustentan el traslado de mercaderías dentro del
> territorio nacional, **por cualquier motivo** (…). Las Notas de Remisión
> deberán ser expedidas **en forma previa al traslado** y acompañar a la
> mercadería en tránsito en todo el trayecto.»

**Art. 31** — está obligada a expedirla «toda persona física y jurídica,
**propietaria o responsable de los bienes**».

**RG 41/2014, art. 5** — la excepción que resuelve el caso más común del
mostrador:

> «La emisión de la nota de remisión **no será necesaria**, cuando la factura u
> otro comprobante de venta contenga todos los datos requeridos en los
> artículos precedentes.»

Traducido a Óga Porã:

| Situación | ¿Remisión? |
|---|---|
| El cliente carga los pisos en su camioneta y se va con la factura | **No.** La mercadería viaja respaldada por el comprobante de venta |
| El local entrega con su propio flete | **Sí.** El local es responsable de los bienes en tránsito |
| El local contrata un transportista | **Sí**, y hay que cargar sus datos en el formulario de traslado |
| Mercadería que se mueve entre locales, va a una feria o vuelve por reparación | **Sí**, aunque no haya venta — son motivos 7, 12 y 9 de la tabla E502 |

Esa última fila es la que más conviene retener: de los **catorce** motivos de
emisión de la tabla E502 del manual, «traslado por ventas» es **uno solo**. Un
sistema que emitiera la remisión como parte del cobro no podría representar los
otros trece.

**Consecuencia en el código:** emitir es un botón en el panel del pedido, no un
paso de caja. La condición que decide —¿sale en el flete o se lo lleva el
cliente?— la conoce quien despacha, no el sistema. Ver `remision.py`, cuyo
docstring repite esto para quien llegue por el código y no por acá.

**Lo que queda sin resolver desde afuera:** si la remisión debe expedirse
«en forma previa al traslado», emitirla contra un cobro ya confirmado sirve
mientras el local cobre antes de despachar, que es lo que hace hoy. Un
despacho a crédito, o uno que sale antes de pasar por caja, no entra en este
modelo: el `DocumentoElectronico` cuelga del `Pago`. El manual prevé el caso
—el campo E506 es la «fecha futura de emisión de la factura», justamente para
cuando la remisión sale antes— así que si el negocio empieza a despachar a
crédito, esto hay que rediseñarlo, no parchearlo.

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

### Cobro con cheque (17/09/2026)

El mismo problema que la tarjeta, en el otro medio de pago que el SIFEN no
deja declarar a secas: el grupo **E630 (`gPagCheq`)** se activa si E606 = 2, y
sus dos campos son obligatorios (ocurrencia 1-1):

| Campo | Tipo | Detalle |
|---|---|---|
| E631 `dNumCheq` | A(8) | número, "completar con 0 a la izquierda hasta alcanzar 8 cifras" |
| E632 `dBcoEmi` | A(4-20) | banco emisor |

`apps/caja/cheque.py` + el modelo `DatosCheque` + los campos en la pantalla de
cobro, más `'cheque'` en `Pago.MEDIOS` y en `codigos.MEDIO_PAGO`.

Dos cosas que conviene no perder:

- **El mínimo de 4 caracteres del banco no es decorativo.** "BNF" tiene tres y
  el documento volvería rechazado, así que se guarda el nombre y no la sigla.
  La lista de bancos de la pantalla está pensada para eso.
- **Acá los datos se exigen siempre, no solo al facturar** — y esa es la
  diferencia deliberada con la tarjeta. La tarjeta ya fue autorizada por la
  terminal y el voucher queda impreso: el cobro está hecho aunque el sistema no
  anote nada. Un cheque es una promesa de pago, y sin banco ni número el local
  se queda con un papel que no puede cruzar contra el extracto. Eso es del
  negocio, no del DNIT, y rige con el SIFEN apagado igual.

De yapa, dos datos que el SIFEN no pide y la tienda sí necesita: quién libró el
cheque y la **fecha de cobro** si es diferido. El cheque nunca entra al arqueo
de efectivo (el arqueo compara el cajón físico contra apertura + ventas en
efectivo), así que un turno con cheques no muestra faltante.

Verificado contra el sidecar sobre un cobro real: el XML sale con
`<iTiPago>2</iTiPago><dDesTiPag>Cheque</dDesTiPag>` y
`<gPagCheq><dNumCheq>00004571</dNumCheq><dBcoEmi>Banco Continental</dBcoEmi></gPagCheq>`.

### Fase C — Eventos ✅ (19/09/2026)

Cancelación e inutilización, las dos del rol emisor. Los cuatro eventos del
rol receptor quedan afuera a propósito: son para cuando el negocio recibe
documentos electrónicos de sus proveedores, que es otro problema y todavía no
existe en el sistema.

**Modelo `EventoDocumento`** (`apps/facturacion/models.py`), un registro por
evento, con su estado frente al SIFEN. **Módulo `eventos.py`** con las reglas.
**Endpoints**: `POST /documentos/<pk>/cancelar/`, `GET|POST
/inutilizaciones/`, `GET /numeros-sin-usar/`. **Pantalla**: `FacturacionPage`
en el frontend, solo admin. **36 tests** en `tests/test_eventos.py`.

Las reglas que salen del manual y no de la cabeza de nadie:

- **El plazo de cancelación se cuenta desde la aprobación del SIFEN**, no
  desde la emisión: 48 horas para la factura electrónica y 168 para el resto
  de los tipos (§11.6.1, validaciones GDE004a y GDE004b). Para poder
  calcularlo hizo falta guardar `DocumentoElectronico.fecha_aprobacion`, que
  antes no existía — `ultimo_intento` se pisa en cada reintento y
  `fecha_emision` es cuándo se cobró. Vencido el plazo, la corrección va por
  nota de crédito, y la pantalla lo dice con esas palabras.
- **El motivo es obligatorio y va de 5 a 500 caracteres** (GEC003 y GEI008).
  El mínimo no es un capricho: un "ok" vuelve rechazado.
- **Un rango de inutilización no pasa de 1000 números** (GEI006) y no puede
  contener ninguno ya emitido (GEI005) ni ya inutilizado (GEI005a). Las tres
  se validan de este lado, antes de gastar un intento contra un rechazo
  previsible.
- **La NT 025 (23/04/2025)** sacó la validación que impedía cancelar cuando
  el receptor ya había confirmado el DTE. No hubo nada que implementar por
  esa nota: lo que hace es quitar un motivo de rechazo.

Dos decisiones de diseño, las dos por lo mismo — que la operación no dependa
de que internet ande en ese segundo:

1. **El evento se guarda antes de transmitirse**, igual que un DE. Si el
   sidecar está caído queda `pendiente` y lo levanta `sifen_transmitir`, que
   ahora recorre las dos colas y manda **primero los eventos**: son los que
   corren contra un plazo.
2. **El documento pasa a `cancelado` solo cuando el SIFEN aprueba el
   evento.** Marcarlo antes dejaría la base diciendo que un DTE está anulado
   cuando para la DNIT sigue vivo, que es la desincronización más cara de las
   dos posibles.

Y una tercera que no es técnica: **cancelar no toca el stock ni el cobro**.
Anular el comprobante fiscal y devolver la mercadería son dos cosas
distintas; mezclarlas haría que una corrección de papeles mueva el
inventario. Si además hay devolución, eso es la nota de crédito, que sí
repone stock según el motivo.

#### Los números sin usar, que es el hueco operativo real

`eventos.huecos_de_numeracion()` compara el correlativo que consumió
`SecuenciaComprobante` contra los documentos que existen, y devuelve los
números que quedaron en el medio. Nadie los va a encontrar mirando la lista a
ojo, y un salto sin declarar es una observación en una fiscalización. La
pantalla los agrupa en rangos —cuatro números corridos son un evento, no
cuatro— y no ofrece ninguno que sí se haya emitido.

### Los plazos del Manual, y cuáles bloquean (23/09/2026)

Releyendo el Manual aparecieron cuatro reglas que el sistema no aplicaba. La
parte interesante no es implementarlas sino que **no todas se comportan
igual**, y la diferencia no es de criterio nuestro:

| Regla | Dónde | Qué hace |
|---|---|---|
| 45 días para un evento del receptor, desde la emisión | Tabla J, filas 10–13 | **Bloquea** |
| 15 días para corregir un evento del receptor | Tabla K | Solo se calcula — falta el evento |
| 15 primeros días del mes siguiente, inutilización | Tabla J, fila 2 | **Avisa, no impide** |
| Vigencia del timbrado, inutilización | Tabla J, fila 2 | **Bloquea** |
| Cancelar primero el último DTE de la cadena | Tabla J, fila 1 | **Bloquea** |

**Por qué la inutilización avisa y la cancelación bloquea.** Vencido el plazo
de cancelación queda otro camino: la nota de crédito. Un hueco de numeración
no tiene ninguno — si el sistema se negara a declararlo fuera de término, el
correlativo quedaría roto para siempre y la única salida sería tocar la base.
Declarar tarde es peor que a tiempo y mucho mejor que nunca, y esa decisión
es del contribuyente. El aviso llega hasta la pantalla (campo `advertencia`
de la respuesta, toast de 12 segundos): en el log no lo iba a leer nadie.

En cambio la **vigencia del timbrado**, en la misma fila de la misma tabla,
sí bloquea, porque el Manual la marca como «plazo del sistema»: la hace
cumplir el SIFEN y un rango de un timbrado vencido vuelve rechazado.

**De dónde sale la fecha de los 45 días.** Del CDC, posiciones 26 a 33
(`cdc.fecha_de_emision()`). El documento es de un proveedor: nunca vimos su
aprobación y no podemos confiar en que alguien tipee bien la fecha aparte.

**El punto flojo, anotado a propósito.** El Manual cuenta el plazo de la
inutilización desde «el acaecimiento del hecho» y no define cuál es la fecha
de un número que nunca existió. `eventos.fecha_del_hecho()` toma la del
primer documento emitido **después** del rango, que es cuando el correlativo
siguió de largo. Es una interpretación, no una cita; si la contadora lee otra
cosa, se cambia en un solo lugar.

**Cancelación en cadena**: alcanza a notas de crédito, de débito y remisiones,
porque las tres referencian la factura por `documento_asociado_cdc`. Un
documento rechazado no cuenta (nunca fue DTE) y uno ya cancelado tampoco;
uno todavía en la cola sí, porque va a ser un DTE en minutos.

37 tests en `tests/test_plazos_manual.py`, más 10 nuevos de `esquema.py`.

### Fase D — KuDE y QR ✅ (19/09/2026)

`apps/facturacion/kude.py` arma el **PDF del KuDE** con reportlab, y
`GET /documentos/<pk>/kude/` lo entrega. **23 tests** en `tests/test_kude.py`.

#### Repaso del formato (20/09/2026) — y por qué hay que mirar el PDF

Hasta acá el KuDE se había revisado leyendo el código y corriendo tests. Se
renderizó a imagen por primera vez y aparecieron cuatro cosas que ningún test
podía ver:

1. **La raya separadora cruzaba el logo y el teléfono del emisor.** El margen
   superior estaba fijo en 76 mm y la raya a 26 mm del tope, sin mirar cuánto
   medía el bloque del emisor. Con los datos reales del local ese bloque mide
   25,8 mm: **0,2 mm de margen**. En ambiente de prueba, donde la razón social
   se reemplaza por la leyenda obligatoria de la Guía §2 y ocupa dos
   renglones, se pasaba de largo y la primera línea del receptor caía encima
   de la última del emisor.

   Ahora el alto lo calcula `_alto_encabezado_mm()` a partir de las líneas
   reales, y tanto el `topMargin` como el dibujo salen de ahí. El logo se
   escala a la banda en vez de tener 34 mm fijos. Cinco tests nuevos fijan la
   invariante.

2. **La tabla de totales no alineaba con la de ítems, y eso la hacía mentir.**
   Las columnas eran `0,52 / 0,16 / 0,16 / 0,16` contra unos ítems que
   terminaban en `0,75 / 0,83 / 0,91`. Los tres números del SUBTOTAL —que son
   el total de las columnas Exentas, 5% y 10%— caían debajo de "Precio unit."
   y "Descuento". No era solo feo: el papel decía otra cosa de la que
   liquidaba. Ahora los anchos se **derivan** de los de la tabla de ítems, así
   que no se pueden volver a separar.

3. **Los títulos se partían al medio** ("Unida/d", "Descuent/o") y el SKU
   ocupaba cinco renglones. Se reajustaron los anchos, se bajó el relleno
   lateral de 6 pt a 3 pt y el código usa `wordWrap='CJK'`, que corta una
   palabra larga con guiones donde entre.

4. **Correo y dirección del receptor compartían línea de base**, uno alineado
   a izquierda y otro a derecha: una dirección larga se le encimaba al correo.
   El correo pasó a su propio renglón y los dos campos se recortan al ancho.

**Cómo mirarlo** (no hay poppler en el equipo, pero sí `pypdfium2` en el venv):

```python
import pypdfium2 as pdfium
pdfium.PdfDocument('kude.pdf')[0].render(scale=2.2).to_pil().save('kude.png')
```

Vale la pena antes de dar por bueno cualquier cambio de formato.

### Qué pasa al apretar "Facturar" — repaso del flujo (20/09/2026)

El recorrido completo, todo dentro de un `@transaction.atomic` con el pedido
tomado por `select_for_update()`:

1. Se crea el `Pago` y, si corresponde, `DatosTarjeta` o `DatosCheque`.
2. El pedido pasa a `pagado`.
3. `descontar_stock()` libera la reserva y descuenta, con su `MovimientoStock`.
4. Se avisa por WebSocket.
5. **Solo si es factura**, `emitir_para_pago()` crea el DE: toma el
   correlativo, calcula el CDC y lo deja en `pendiente` para el worker.
6. Se arma el ticket y **se imprime**.
7. Se responde con el comprobante.

El frontend exige RUC y razón social antes de habilitar el botón cuando el
comprobante es factura, la denominación de la tarjeta si se cobra con
tarjeta, y número y banco si es cheque. Eso está bien cubierto.

**Las dos cosas que aparecieron en el repaso, ya corregidas (20/09/2026):**

- ✅ **La impresión corría adentro de la transacción**, con el pedido
  bloqueado por `select_for_update()`. `win32print` no tiene timeout: una
  impresora colgada —no apagada, que eso devuelve error enseguida: colgada,
  con el spooler sin contestar— mantenía abierta la transacción y el lock sin
  límite. Con varias tablets cobrando a la vez, un cobro trabado podía frenar
  a los demás.

  `RegistrarPagoView` se partió en dos: `_registrar()` conserva el
  `@transaction.atomic` y hace todo lo que toca la base, y `post()` arma el
  comprobante e imprime **después**, con la transacción ya cerrada. El papel
  no es parte de la consistencia de la venta: si la impresión falla, el cobro
  ya ocurrió y se reimprime desde "Cobros del turno".

  La invariante quedó fijada en `apps/caja/tests/test_cobro_transaccion.py`,
  que espía la llamada a la impresora y verifica `connection.in_atomic_block`.
  Usa `TransactionTestCase` y no `TestCase` a propósito: `TestCase` envuelve
  cada prueba en su propia transacción y la prueba pasaría sin probar nada.
  Incluye además el test de lo que **no** hay que sacar afuera — el descuento
  de stock, que sí tiene que estar adentro.

- ✅ **La emisión del DE fallaba en silencio.** `emitir_para_pago()` no lanza
  nunca y devuelve `None` — deliberado, porque hay alguien esperando en el
  mostrador y un problema de facturación no puede tumbar un cobro ya hecho.
  Pero la venta se completaba, el ticket salía sin CDC y nadie se enteraba:
  quedaba solo en el log. Y después no había dónde verlo, porque la cola de
  `FacturacionPage` lista los `DocumentoElectronico` que **existen**; un cobro
  facturado que nunca llegó a generar uno era invisible.

  `GET /api/v1/facturacion/ventas-sin-documento/` (solo admin) los lista, y
  hay un panel propio en `FacturacionPage`. La respuesta incluye
  `sifen_habilitado` porque la misma lista significa dos cosas distintas:

  | Interruptor | Qué es la lista |
  |---|---|
  | Apagado (hoy) | Las ventas a cargar a mano en el portal. Normal, aparecen todas |
  | Prendido | **Alarma**: deberían tener comprobante fiscal y no lo tienen |

  El panel cambia de color y de texto según el caso, en vez de gritar siempre.
  El filtro mira "tiene factura", no "tiene algún documento": si mirara lo
  segundo, un cobro con nota de crédito y sin factura pasaría desapercibido —
  hay un test para eso. 7 tests en `test_ventas_sin_documento.py`.

Lo que define que esté bien:

- **Los ítems salen de `payload._items()`**, o sea exactamente lo que viajó
  al SIFEN, con los descuentos ya prorrateados. El manual prohíbe que el KuDE
  muestre información que no esté en el DE firmado (§13.2) y la única forma
  seria de garantizarlo es no tener una segunda fuente de datos.
- **El QR no se dibuja si el documento todavía no fue firmado.** Su contenido
  lo calcula `qrgen` y lleva el hash de la firma y el CSC (§13.8.2): no se
  puede reconstruir de este lado, y uno inventado con la URL de consulta
  escanearía y no resolvería nada. En ese caso el pie lo dice. El enlace se
  extrae del XML firmado (`dCarQR`) y se guarda en
  `DocumentoElectronico.enlace_qr` al transmitir, para no tener que volver a
  leer el XML entero en cada reimpresión.
- **En ambiente de prueba la razón social del KuDE es la leyenda obligatoria**
  de la Guía §2, la misma que va en el XML. Si el papel dijera el nombre real
  y el XML la leyenda, no coincidirían.
- Estructura del §13.4 completa: encabezado con timbrado y sus dos vigencias,
  ítems con la afectación del IVA en tres columnas, subtotales y liquidación,
  CDC en once grupos de cuatro y QR de 30 mm (el mínimo del §13.8.1 es 25).
- El tamaño es A4 vertical **por elección nuestra**: §13.5 dice "cualquier
  formato y tamaño de papel estándar" y las gráficas 09 a 15 son modelos
  referenciales.

El ticket térmico de 80 mm sigue existiendo y no cambió: sirve para el
mostrador, pero no es un KuDE. Le faltan el QR firmado, el timbrado con sus
vigencias y la liquidación del IVA. Son dos papeles distintos y conviven.

#### El correo del receptor ya se captura (20/09/2026)

La dirección a la que va a ir la factura se pide **al cobrar**, que es el
único momento en que el cliente está delante y se le puede preguntar. Campo
nuevo en el bloque "Datos del cliente" de caja, junto al teléfono.

Recorrido completo: formulario de caja → `Pago.cliente_email` (migración
`caja/0008`) → `DocumentoElectronico.receptor_email` → campo **D216
`dEmailRec`** del XML. También se guarda en el padrón de clientes, así que en
la próxima compra se autocompleta.

**Las reglas del campo no están en el Manual**, que solo dice "A 3-80,
ocurrencia 0-1". Salen de leer la librería de la DNIT
(`jsonDeMainValidate.service.js` y `jsonDeMain.service.js` de
facturacionelectronicapy-xmlgen), y están replicadas en
`codigos.validar_email_receptor`:

| Regla | Por qué importa |
|---|---|
| Vacío se omite del XML | La librería hace `if (email)`. Mandar un `dEmailRec` en blanco violaría el mínimo de 3 |
| Sin espacios | Rechazo |
| 3 a 80 caracteres | Rechazo |
| Formato de correo | Rechazo |
| **Varios separados por coma → viaja solo el primero** | El SIFEN no acepta comas. El recorte se hace en Django y no en el sidecar, para que lo guardado coincida con lo transmitido |

Esa última es la que conviene no descubrir en producción: la cajera escribe
dos correos creyendo que le llega a los dos, y el comprobante sale con uno.

Se valida **al cobrar** y no al transmitir. Un correo mal escrito que
descubre el worker al otro día es un documento rechazado y nadie a quien
preguntarle; con el cliente en el mostrador se corrige en el momento. El
frontend avisa mientras se escribe con las mismas reglas, y el backend las
vuelve a aplicar porque la API se puede llamar sin pasar por esa pantalla.

El correo **no se imprime** en el papel: al cliente no le aporta nada saber
su propia dirección. Se muestra en el comprobante en pantalla para que quien
cobra confirme adónde va a ir la factura antes de que el cliente se vaya.

15 tests en `tests/test_email_receptor.py`.

**Sigue pendiente el envío en sí.** Ahora hay adónde mandar, pero nada manda
todavía: falta decidir si lo envía el SIFEN al aprobar el DE o si lo manda el
sistema con el PDF adjunto. No bloquea nada — hoy el papel se imprime o se
manda por WhatsApp desde el PDF.

Ojo con una asimetría que queda: `NotaPedido` **no** tiene correo, así que
una nota de remisión emitida sobre un pedido sin factura sale sin
`dEmailRec`. Es válido (el campo es opcional) y no rompe nada, pero si algún
día se quiere que la remisión también llegue por correo, hay que sumar el
campo al pedido y a la rendija de `NotaPedidoDetailView.patch()`.

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

### Fase F — Monitoreo y operación — parcial (19/09/2026)

**Hecho**: la pantalla `Facturación` del frontend (solo admin) muestra la
cola con el resumen por estado, el motivo de cada rechazo, el KuDE de cada
documento y cuántas horas quedan para poder cancelarlo. Ya no hace falta
entrar al servidor a correr `sifen_transmitir --listar` para saber si hay
algo trabado.

**Falta**: el estado de conexión del sidecar en esa misma pantalla y el
**aviso de certificado próximo a vencer**. El chequeo del `.p12` existe
—`verificar_fiscal` lo hace— pero es un comando, y un certificado vencido
frena la facturación entera sin avisar. Tiene que llegar a la pantalla o a
un aviso automático.

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

### Los códigos geográficos — resueltos el 16/09/2026

El Manual no los trae: la Tabla 2.1 (§15) remite a una planilla externa,
`CODIGO DE REFERENCIA GEOGRAFICA.xlsx`. Pero **`xmlgen` trae las tablas de la
DNIT adentro**, con `consultarDepartamentos()`, `consultarDistritos()` y
`consultarCiudades()`. O sea que no hace falta bajar la planilla: se consultan
con `POST /geografia` del sidecar, o con `npm run geo`.

| Dato | Código | Descripción |
|---|---|---|
| Departamento | **6** | CAAGUAZU |
| Distrito | **61** | CNEL. OVIEDO |
| Ciudad | **2886** | CNEL. OVIEDO |

⚠️ **La ciudad hay que confirmarla.** El distrito 61 tiene **dos** entradas
llamadas "CNEL. OVIEDO": la 2886 y la 2937. Se eligió la 2886 por la forma de
la tabla —en 205 de los 272 distritos la primera ciudad listada es la cabecera,
fuera del orden alfabético, y 2886 es la primera del distrito 61, mientras que
2937 aparece en su lugar alfabético entre "CHIRCA TY" y "COL. SANTA MARIA"—.
Es una inferencia sobre datos, no un dato oficial, y un código geográfico
equivocado es rechazo directo: conviene que la contadora lo confirme contra la
planilla del DNIT antes de las pruebas. Mientras tanto ya está cargado en el
`.env` para poder armar XML.

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

### Las 27 Notas Técnicas ✅ (14/09/2026)

Revisadas una por una. El registro completo, con qué se aplicó y qué no,
está en **`docs/notas_tecnicas_sifen.md`**.

El riesgo era real y del mismo tipo que el del dígito verificador: **cuatro**
notas corregían cosas que el sistema tenía mal justamente por seguir el manual
base, que es de 2019.

Lo más importante que salió:

- **NT 024** — el receptor no puede quedar sin identificar en ventas de
  **7.000.000 Gs o más**. No es técnico, es operativo: siete millones son los
  pisos de un baño, así que en este rubro es el caso normal. Hay que avisarle
  a la cajera antes de prender el SIFEN.
- **NT 006** — el tipo de transacción no se informa fuera de factura y
  autofactura. El payload lo mandaba siempre: tres de los cinco tipos de
  documento habrían sido rechazados.
- **NT 023** — las notas de crédito, débito y remisión nunca pueden ir a un
  receptor innominado.
- **NT 010, 009, 005, 007** — kilómetros obligatorios en la remisión,
  longitudes de código y descripción del ítem, matrícula de 7 caracteres, y la
  leyenda legal obligatoria de la remisión.

Queda **un pendiente para la contadora**: el texto literal de la leyenda del
art. 3 inc. 7 de la RG 41/2014, que va en la nota de remisión. No está en la
NT y no se inventa.

**Encontrado el 20/09/2026, y complica el pendiente en vez de cerrarlo.** El
art. 3 inc. 7 de la RG 41/2014 dice:

> «La indicación expresa de "Mercaderías con cadena de Frío"; "Carga
> Peligrosa", u otro dato de relevancia similar, cuando se transporten
> productos que cumplan algunas de estas características.»

O sea que el inciso es **condicional**: aplica a mercadería refrigerada o
peligrosa. Los pisos, revestimientos y sanitarios de Óga Porã no son ni una
cosa ni la otra, así que el supuesto del inciso no se cumple. Pero la **NT
007** volvió el campo B006 `dInfoFisc` **obligatorio** en la nota de remisión,
y `payload._bloque_remision()` corta la emisión si `FISCAL_LEYENDA_REMISION`
está vacío.

Los dos hechos juntos dejan una pregunta que sigue siendo de la contadora, no
nuestra: qué se escribe en un campo obligatorio cuyo contenido previsto no
corresponde. Lo que **no** hay que hacer es inventar un texto ni poner el de
cadena de frío «por poner algo»: es un campo que el Fisco lee.

### Falta también bajar la estructura XSD

La página publica `Estructura xml_DE` y `Estructura_DE xsd` (en `.rar`). El
XSD permite **validar el XML localmente antes de transmitir**, que es lo que
la Guía de Pruebas pide como primer filtro ("XML inválido → rechazo antes de
envío"). El mecanismo ya está construido (`apps/facturacion/esquema.py`,
20/09/2026); lo que falta es el archivo.

#### ⚠️ El archivo que publica esa página es de 2018 y no sirve (23/09/2026)

Se bajó y se probó. **No es el de la V150.** Tres evidencias independientes:

1. **El Manual.** El Schema XML 18 (`DE_v150.xsd`, pág. 61) describe la raíz
   como `rDE` → `dVerFor` → `DE` con atributo `Id` → `dDVId`, `dFecFirma`,
   `dSisFact`. El archivo bajado no tiene el envoltorio `DE`, ni `Signature`,
   ni `gCamDEAsoc`, ni `gTransp`, ni `gPagCheq`/`gPagTarCD`.
2. **Los nombres de los grupos.** El archivo trae `gCiODE`, `gDTim`,
   `gCamOC`, `gInfPed`, `sSubVIva5`. Ninguno de esos aparece **ni una vez** en
   las 217 páginas del Manual V150, que usa `gOpeDE`, `gTimb`, `gDatGralOpe`,
   `gCamGen`, `dSubExe` y `dTotOpe`. `xmlgen` emite los de la V150.
3. **La prueba.** Compila sin un error —por eso engaña— pero validar un `rDE`
   con el namespace real devuelve un único error, en la raíz:
   `'{http://ekuatia.set.gov.py/sifen/xsd}rDE' is not an element of the
   schema`. El archivo no declara `targetNamespace`.

Apuntarle `SIFEN_XSD_PATH` habría hecho que **todo** documento volviera «no
cumple el esquema», y como `esquema.validar()` corre dentro de `_firmar()`,
habría tumbado el camino sincrónico y el de lote a la vez. La red de
seguridad del módulo —no frenar por no poder validar— no cubría este caso:
acá el XSD carga bien, solo que es el equivocado. Desde el 23/09 `_schema()`
revisa el `targetNamespace` y descarta el que no sea el del SIFEN.

**Qué hay que pedirle a la DNIT**, por el canal de Contáctenos o el de envío
de archivos (§5 de la Guía de Pruebas): el juego de la V150, por nombre. El
Manual los lista en su índice de schemas: **`siRecepDE_v150.xsd`** (el que
`xmlgen` declara en su `xsi:schemaLocation`), `DE_v150.xsd`,
`Evento_v150.xsd`, `xmldsig-core-schema-v150.xsd` y los demás, 19 en total.
Ninguna de las librerías de la DNIT los trae adentro: `find node_modules
-iname "*.xsd"` no devuelve nada.

Mientras tanto, **el Manual alcanza para saber la estructura** —sus tablas
dan grupo, ID, campo, nodo padre, tipo, longitud y ocurrencia, y son de donde
salió `payload.py`—, pero no para validar a máquina: una tabla en PDF no se
le pasa a `xmlschema`.

---

## 11. El sidecar (16/09/2026)

Vive en `sidecar/`. `sidecar/README.md` tiene el detalle; acá va lo que cambia
decisiones.

### Qué quedó funcionando

- **El proceso Node**, con las cuatro librerías de TIPS-SA (`xmlgen`,
  `xmlsign`, `qrgen`, `setapi`), implementando el contrato que ya definía
  `sifen_client.py`. 22 tests propios.
- **Enganchado al arranque**: `iniciar.bat` lo levanta, `detener.bat` lo baja,
  `setup.bat` corre su `npm install`. Si no está instalado, el arranque avisa y
  sigue — la tienda tiene que poder vender igual.
- **`manage.py sifen_probar`**, que recorre payload → sidecar → XML sin
  transmitir nada. Verificado contra un cobro real de la base.
- **`manage.py verificar_fiscal`** ahora revisa el sidecar y **avisa si el
  certificado está por vencer** (parte de la Fase F). Un `.p12` vencido frena
  la facturación entera y no avisa solo.

### Lo que confirmó, y no era obvio

**El CDC está bien.** `sifen_probar` compara el CDC que calcula Django con el
que calcula `xmlgen` — y son dos implementaciones independientes, porque el
CDC no se le manda al sidecar: se le mandan los campos sueltos y él lo arma.
Sobre un documento real coincidieron carácter por carácter, DV incluido. Es la
confirmación más fuerte que se podía tener del arreglo de agosto (pesos 2..11)
sin estar conectado al SIFEN, y además avisaría si una actualización de la
librería cambiara el algoritmo.

### Tres cosas que salieron de leer el código de las librerías

Ninguna está en los README, y las tres cambian decisiones.

**1. Java se evita, pero hay que pedirlo explícitamente.** `xmlsign.signXML`
tiene un último parámetro `signByNodeJS` que por defecto es `false`, y con
`false` busca un JRE y hace `exec` de un `java -classpath ... SignXML`. Habría
significado instalar y mantener **Java en la PC de la tienda**. Va en `true`.

**2. `facturacionelectronicapy-kude` no se instaló.** Su `generateKUDE` recibe
un `java8Path` y una carpeta de plantillas `.jasper`: es un envoltorio de
JasperReports y arrastra Java 8. El KuDE en PDF se arma con reportlab del lado
de Django, reusando el motor de `nota_pedido_doc.py` — que además ya tiene la
marca del negocio. Esto no agranda la Fase D: era el plan.

**3. `xmlgen` no valida: interpola.** Si a `generateXMLDE` le falta un campo,
no falla — escribe el string `"undefined"` en el XML y devuelve éxito. Se
descubrió probando sin `codigoSeguridadAleatorio`, y salió un DE con

```
<DE Id="0180173107000100100000012202609161undefined3">
<dCodSeg>undefined</dCodSeg>
```

y respuesta OK. Ese documento se habría firmado, transmitido, y vuelto
rechazado con un error del SIFEN que **no señala el campo que falta** — y como
un rechazo es terminal, la venta quedaba sin factura y sin pista. El sidecar
ahora revisa el XML antes de devolverlo (`verificarXmlSano`): si hay
`undefined` dice qué campo, y si el CDC no tiene 44 dígitos también corta.
`payload.py` hoy manda todo, así que es una red, no un parche: protege del día
que se agregue un tipo de documento y se olvide un campo.

### Se puede probar hasta el QR sin el certificado real

`sidecar/herramientas/certificado_prueba.sh` genera un `.p12` autofirmado con
`clientAuth`. No es un atajo inventado: la Guía de Pruebas §2 pide, como uno de
sus escenarios, intentar con un certificado **no válido** que el contribuyente
se autogenera.

Con eso se verifica toda la mecánica de firma —que el archivo abra, que la
clave sea la correcta, que se firme el nodo que corresponde, que la referencia
apunte al CDC, que el QR se calcule con el CSC— sin esperar al certificado del
prestador. Lo único que queda afuera es el handshake contra el SIFEN, que es
justamente lo que necesita el certificado de verdad.

    bash sidecar/herramientas/certificado_prueba.sh
    python manage.py sifen_probar --documento <id> --firmar

El `.p12` se escribe **fuera** del repositorio, a propósito.

Verificado el 16/09/2026 sobre los tres tipos que el sistema emite —factura,
nota de crédito y nota de remisión—: XML, CDC contrastado, firma RSA-SHA256
con el certificado embebido y `Reference URI` apuntando al CDC, y el QR
apuntando a `consultas-test`.

Dos cosas salieron de hacerlo, y ninguna se habría visto sin un certificado:

**1. El aviso de vencimiento no funcionaba.** `xmlsign.getExpiration()` no
devuelve una fecha: devuelve `{notBefore, notAfter}`. El diagnóstico esperaba
un string, así que nunca entendía el dato y nunca avisaba — la función entera
era decorativa. Ahora el sidecar normaliza la forma y `verificar_fiscal` la
tolera igual, por si corre contra un sidecar de otra versión.

**2. La nota de remisión no se podía emitir.** Era el único de los tres tipos
construidos que nunca se había probado contra `xmlgen`: se había escrito
leyendo el manual. La librería la rechazó con **diez** errores de golpe, entre
ellos que las fechas de traslado se llaman `inicioEstimadoTranslado` y
`finEstimadoTranslado` —con "Transl", no "Trasl"—, que el receptor de una
remisión necesita domicilio completo, y que el transportista y el chofer
necesitan documento y dirección, con un tope de 60 caracteres que la dirección
real del local supera. Migración `0006` para los campos que faltaban, y once
tests nuevos en `test_remision.CamposQueExigeXmlgenTests`, uno por hallazgo.

La moraleja es la de siempre en este proyecto: el manual no alcanza, y un
bloque que nunca se ejecutó contra la implementación de referencia todavía no
está escrito.

### El mapeo de errores, que es lo que sostiene la cola

El sidecar contesta con el código HTTP que le dice a `transmision.py` qué
hacer:

| Código | Significa | Django |
|---|---|---|
| 200 | el SIFEN contestó (incluso "Rechazado") | lee el estado |
| 422 | el pedido o la configuración están mal | **terminal** |
| 502 | no se pudo hablar, o no se entendió | **reintentable** |

Un caso que hay que tener claro: los errores de `xmlgen` van como **terminales**.
Armar el XML es cálculo local puro —no toca la red, no abre archivos—, así que
todo lo que falle ahí es un problema de los datos y reintentarlo diez veces da
diez veces lo mismo. Sin esa traducción, una remisión a la que le falta la
dirección del chofer se llevaba los diez intentos y el mensaje quedaba
enterrado entre reintentos.

Ante la duda va 502. Reintentar de más gasta intentos; dar por rechazado un
documento válido pierde una venta ya cobrada y eso no se deshace.
`sifen_client._postear()` traduce el 422 a `RechazoSifen` — antes cualquier
error HTTP era reintentable, así que un certificado faltante se llevaba los
diez intentos de cada documento de la cola.

### Seguridad: escucha solo en loopback

El sidecar tiene la clave del `.p12` en memoria y firma cualquier XML que le
manden, sin autenticar a nadie. En esta LAN —tablets conectadas,
`ALLOWED_HOSTS=*`, CORS abierto— publicarlo en `0.0.0.0` sería entregar la
firma electrónica del contribuyente a cualquiera que esté en la WiFi. Django
corre en la misma máquina. Si alguna vez hiciera falta cambiarlo, primero
autenticación.

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
