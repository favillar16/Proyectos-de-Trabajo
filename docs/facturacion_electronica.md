# Facturación electrónica — e-Kuatia / SIFEN

Estado al **23/08/2026**. Reemplaza y amplía la sección 6.5 de
`todo_montaje_servidor.md`.

---

## 1. Lo primero: e-Kuatia'i no se integra

Es el malentendido que hay que sacarse de encima antes de planificar nada.

| | **e-Kuatia'i** | **e-Kuatia** (completo) |
|---|---|---|
| Para quién | Pequeños contribuyentes | Medianos y grandes |
| Cómo se emite | **A mano, en el portal web del DNIT** | Desde el software propio, vía web services |
| Integración con este sistema | **No existe. No hay API.** | Sí, contra la especificación técnica del SIFEN |
| Requisitos | Un solo establecimiento, un solo punto de expedición, certificado de firma (gratis del DNIT) | Certificado + habilitación con pruebas |
| Costo | Gratis | Gratis el certificado; el desarrollo es propio |

**Consecuencia práctica:** si Oga Porã va por e-Kuatia'i, la cajera cobra en
este sistema y **además** carga la factura a mano en el portal del DNIT.
Doble trabajo por venta facturada. Este sistema puede reducirlo (validando
los datos y exportándolos listos para copiar) pero no eliminarlo.

Si se quiere que la factura salga sola al confirmar el cobro, el camino es
**e-Kuatia completo**. Es la decisión de fondo, y es una decisión de negocio
más que técnica.

---

## 2. El conflicto con el diseño del sistema

Este sistema es un **appliance de red local sin dependencia de internet** —
es la premisa de `CLAUDE.md` y la razón por la que funciona cuando se corta
el servicio en el local. El SIFEN necesita internet.

**No se resuelve poniendo internet en la PC servidor y ya.** Si el cobro
espera la respuesta del SIFEN, cada caída de conexión frena la caja con
gente en el mostrador.

La arquitectura elegida evita eso:

```
Cobro en caja
   │
   ├─→ CDC calculado LOCALMENTE (no necesita internet)
   ├─→ Se imprime el comprobante en el acto        ← la venta nunca espera
   └─→ El DE queda encolado en estado 'pendiente'
                │
                └─→ Worker aparte lo transmite cuando hay conexión
                        └─→ anota aprobado / rechazado y reintenta
```

Esto además aprovecha que el DNIT da una ventana para transmitir un DE ya
emitido: un corte de unas horas no invalida la venta.

---

## 3. Librería elegida

El DNIT publica dos librerías de referencia en
<https://www.dnit.gov.py/en/web/e-kuatia/librerias>:

| | `facturacionelectronicapy-*` (TIPS-SA) | `rshk-jsifenlib` (Roshka) |
|---|---|---|
| Runtime | **Node.js / TypeScript**, npm | Java 8, Maven |
| Cubre | XML, firma, QR, envío, KuDE (5 paquetes) | Web services: recepción, lotes, eventos, consulta RUC |
| En la PC servidor | **Node ya está instalado** (Vite) | Habría que instalar un JRE |

> Ojo con el nombre: el `py` de `facturacionelectronicapy` es **Paraguay**,
> no Python. Es una librería de Node.

**Decisión: suite de TIPS-SA como sidecar Node.** Cubre el pipeline completo
y no agrega ningún runtime nuevo a la PC servidor.

Se descartó implementarlo en Python puro (`lxml` + `xmlsec`): `xmlsec` en
Windows es binario nativo y difícil de instalar, y reimplementar el esquema
del SIFEN nos dejaría manteniendo a mano cada revisión del manual técnico.

Paquetes: `xmlgen` (XML del DE), `xmlsign` (firma), `qrgen` (QR del KuDE),
`setapi` (envío a SIFEN), `kude` (representación gráfica).

---

## 4. Lo que ya quedó hecho (23/08/2026)

Todo lo de abajo **funciona con `SIFEN_HABILITADO=False`**, que es como está
hoy: el sistema factura exactamente como antes, no genera DEs y no intenta
salir a internet. Es el interruptor que permite tener este código en
producción sin que cambie nada hasta que estén certificado y habilitación.

### App nueva: `backend/apps/facturacion/`

| Archivo | Qué resuelve |
|---|---|
| `ruc.py` | Valida el dígito verificador del RUC (módulo 11). El SIFEN rechaza el DE entero si viene mal. |
| `codigos.py` | Tablas de códigos del SIFEN y traducción desde los valores del sistema (`efectivo` → `1`, etc.). Único lugar donde se traduce. |
| `cdc.py` | Genera y valida el CDC de 44 dígitos, localmente. |
| `numeracion.py` | Formato `EEE-PPP-NNNNNNN`. |
| `models.py` | `SecuenciaComprobante` (correlativo) y `DocumentoElectronico` (cola). |
| `emisor.py` | Convierte un cobro en un DE. **Nunca lanza**: un problema de FE no puede tumbar una venta ya hecha. |
| `management/commands/verificar_fiscal.py` | Diagnóstico de qué falta configurar. |

### Cuatro problemas de fondo que se corrigieron

1. **La numeración no servía.** Era `T-<timestamp>-<pedido_id>`, que no es un
   número de comprobante válido para ninguna factura, ni electrónica ni en
   papel. Ahora hay correlativo real por punto de expedición, sin saltos
   (con `select_for_update()` para que dos cajas simultáneas no dupliquen) y
   con aviso al agotarse el rango del timbrado.

2. **El IVA se calculaba global** como `total / 11`, con 10% fijo para todo.
   El SIFEN lo exige **por ítem**. Se agregó `Producto.tasa_iva`
   (10 / 5 / exento, default 10) y el desglose por tasa con prorrateo del
   descuento de caja.

3. **Los datos fiscales no se guardaban.** Se leían de `settings` al
   imprimir, así que reimprimir una factura vieja después de cambiar el
   timbrado la sacaba con el timbrado nuevo — mal. Ahora el
   `DocumentoElectronico` guarda un snapshot inmutable del emisor.

4. **El receptor no se persistía.** El RUC del cliente se pasaba solo al
   imprimir y se perdía. Ahora queda guardado en el DE.

### Suite de tests

Antes el proyecto no tenía tests automatizados; estos son los primeros.

```
cd backend && python manage.py test apps.facturacion   # 117 tests
cd frontend && npm test                                # 22 tests
```

### Verificado contra la base real

- Numeración correlativa: 5 números consecutivos, sin repetir.
- Puntos de expedición independientes entre sí.
- **Rollback no deja hueco**: si el cobro falla, el número vuelve atrás.
- Rango agotado: error claro antes de quedarse sin poder facturar.
- CDC: ida y vuelta exacta, detecta corrupción del DV.
- Desglose de IVA: 1.100.000 al 10% → base 1.000.000 + IVA 100.000.
- **Cuadre del desglose**: 400 casos al azar con descuento prorrateado y
  tasas mezcladas, 0 descuadres. La primera versión descuadraba 1 Gs en el
  6,5% de los casos (cada tasa se redondea por separado) — el SIFEN valida
  que el desglose sume exacto, así que eso habrían sido rechazos. Se
  corrigió absorbiendo la diferencia en la base gravada más grande.
- `emitir_para_pago()` con SIFEN apagado devuelve `None` sin tocar nada.
- **Concurrencia**: 8 hilos simultáneos × 15 cobros = 120 números, 0
  duplicados y correlativo exacto 1..120. Es la garantía que la DNIT no
  perdona: dos cajas cobrando a la vez no pueden sacar el mismo número.
- **Integración con caja**: la factura impresa lleva el número legal
  (`001-001-0000001`) y no el ticket interno; el timbrado sale del snapshot
  del DE; el ticket nunca emite DE.
- **Reimpresión**: un pago con DE reimprime la *factura* con su CDC y
  timbrado originales; uno sin DE, el ticket de siempre.

---

## 5. Lo que falta — en orden

### 5.1 Datos a pedirle a la propietaria

Correr primero, que los lista solos:

```
cd backend
venv\Scripts\activate
python manage.py verificar_fiscal
```

Al 23/08/2026 faltan **9**:

| Dato | Clave en `backend\.env` | De dónde sale |
|---|---|---|
| RUC del negocio | `FISCAL_RUC` | Cédula tributaria, con DV |
| Dirección | `FISCAL_DIRECCION` | La que figura en el timbrado |
| Teléfono | `FISCAL_TELEFONO` | |
| Nº de timbrado | `FISCAL_TIMBRADO` | Lo otorga el DNIT |
| Vencimiento timbrado | `FISCAL_TIMBRADO_VTO` | |
| Departamento | `FISCAL_DEPARTAMENTO` | Código de la tabla del DNIT |
| Distrito | `FISCAL_DISTRITO` | Código de la tabla del DNIT |
| Ciudad | `FISCAL_CIUDAD` | Código de la tabla del DNIT |
| Actividad económica | `FISCAL_ACTIVIDAD_CODIGO` | Código del RUC |

Y confirmar (hoy están en su valor por defecto, que puede ser el correcto):

- `FISCAL_RAZON_SOCIAL` — hoy cae en "Oga Porã". Tiene que ser **exacta** a
  la del RUC.
- `FISCAL_ESTABLECIMIENTO` y `FISCAL_PUNTO_EXPEDICION` — hoy `001`. Tienen
  que coincidir con lo habilitado en el RUC.
- `FISCAL_TIPO_CONTRIBUYENTE` — hoy `2` (persona jurídica). Si la
  propietaria factura como persona física, es `1`.

### 5.2 Verificación contra el Manual Técnico

**Fuente:** Manual Técnico del SIFEN **versión 150**, descargable desde
<https://www.dnit.gov.py/en/web/e-kuatia/documentacion-tecnica>.
La versión 150 es además la que declara el sistema en el QR (`nVersion=150`).

#### ✅ Verificado contra el documento oficial (23/08/2026)

- **Composición del CDC** (§10.1). El manual publica un CDC de ejemplo:
  `0144 4444 0170 0100 1001 4528 2201 7012 5158 7326 0988`. Pasado por
  nuestros cortes da 44 dígitos, tipo de documento `01` (factura),
  establecimiento `001`, punto de expedición `001`, tipo de emisión `1`, y
  —la mejor evidencia— el campo de fecha parsea como **2017-01-25**, una
  fecha real. Si el orden de los campos estuviera corrido, ahí saldría
  cualquier cosa. Hay un test que lo contrasta
  (`test_cdc.ContraElManualTecnicoTests`).
- **El CDC lo genera el sistema del emisor** (§10.1), no el SIFEN. Confirma
  que se puede calcular sin internet, que es lo que sostiene todo el diseño
  de cola asíncrona.
- **El KuDE lo muestra agrupado de a cuatro** (§10.1). Es lo que hace
  `formatear_legible()`.
- **Las tablas de códigos** (14/09/2026), contra las tablas inline de §10.4
  y las Codificaciones de §15: `iTiDE`, `iTipEmi`, `iTipTra`, `iTImp`,
  `iCondOpe`, `iTiPago`, `iNatRec`, `iTiOpe`, `iTiContRec`, `iTipIDRec` y la
  Tabla 6 de afectación del IVA. Salió **un error**: `IDENTIDAD_PASAPORTE`
  estaba en `3`, que es el código de la *cédula extranjera*; el pasaporte es
  `2`. No había llegado a ningún DE porque esas constantes todavía no se
  usaban en ningún lado. Faltaba además la autofactura (`iTiDE = 4`), que
  ahora hace falta porque la habilitación se pide por los cinco tipos.
  Fijado en `test_codigos.ContraElManualTecnicoTests`.
- **Código de seguridad** (§10.3): 9 dígitos, aleatorio, no secuencial,
  rango **000000001 a 999999999**, distinto en cada DE, y **no puede ser
  igual al número de documento** (`dNumDoc`).

  Acá el manual destapó un bug: la implementación usaba
  `secrets.randbelow(10**9)`, que arranca en **0** — o sea que podía generar
  `000000000`, fuera del rango permitido. Corregido, y agregada la regla de
  no coincidir con `dNumDoc`, que directamente no estaba.

#### ⚠️ Lo que sigue sin poder verificarse

*(Al 14/09/2026 no queda nada en esta lista. Los códigos de `codigos.py` y el
módulo 11 del DV, que eran los dos pendientes, se cerraron ese día.)*

#### El módulo 11: resuelto el 14/09/2026, y al revés de lo que se creía

Esta es la corrección más importante de todo el módulo fiscal, así que
conviene leerla entera antes de tocar `cdc.PESO_MAX`.

**El estado hasta el 14/09/2026.** El manual (§10.2) dice que el DV se calcula
por módulo 11 pero no publica los pesos: remite a un `digito-verificador.pdf`
cuyo enlace está caído (reintentado el 14/09/2026 con la URL exacta que
imprime el manual; redirige de `set.gov.py` a `dnit.gov.py` sin el documento).

Ante esa ausencia, en agosto se razonó así: ciclar los pesos de 2 a 11 —como
hace `ruc.py`— es defectuoso, porque un peso de 11 anula el aporte de ese
dígito (11·d ≡ 0 mod 11) y deja posiciones que se pueden alterar sin que el
DV se entere. Así que se bajó `PESO_MAX` a 9 y se escribieron tests que
exigían que ninguna posición quedara ciega.

**El razonamiento era correcto y la conclusión estaba mal.** El DV no es una
decisión de diseño nuestra: es un protocolo compartido. El SIFEN recalcula el
dígito con **su** algoritmo y compara. Un DV más fuerte que el suyo es, para
el SIFEN, simplemente un DV equivocado — y el rechazo es del documento
entero. Con `PESO_MAX=9` el sistema habría sido rechazado en el **100%** de
las emisiones, desde el primer documento.

**Cómo se resolvió.** Por tres vías independientes, todas el 14/09/2026:

1. **El propio Manual Técnico.** §10.1 publica un CDC de ejemplo *completo*,
   con su DV: termina en **8**. Pasado por nuestro algoritmo, `PESO_MAX=11`
   da 8 y `PESO_MAX=9` da 2. El dato estaba a mano desde agosto — el test que
   lo usaba parseaba los campos pero **evitaba a propósito** verificar el DV,
   con la nota "el DV del ejemplo depende del algoritmo de pesos, que es
   justamente lo que no se pudo verificar todavía".
2. **`facturacionelectronicapy-xmlgen`** (TIPS-SA), una de las dos librerías
   que la DNIT publica como referencia:
   `calcularDigitoVerificador(cdc, 11)`.
3. **`rshk-jsifenlib`** (Roshka), la otra: `generateDv()` con `baseMax = 11`,
   aplicada al cuerpo del CDC.

Hoy `cdc.PESO_MAX` está en **11**, y hay un test que falla si alguien lo
cambia.

**Qué queda desprotegido, concretamente.** Las posiciones ciegas existen y
son reales, solo que no son nuestras para arreglar. Medidas, no deducidas:
son **4** (la documentación de agosto decía 8; el conteo también estaba mal),
deterministas, y caen en los índices **3, 13, 23 y 33** — exactamente los que
reciben peso 11. El 33 es el **tipo de emisión** (normal / contingencia), que
es el que más incomoda; el SIFEN lo valida por su cuenta.

Conviene distinguir dos cosas que parecen iguales:

- **Posición estructuralmente ciega**: el dígito no aporta nada, *cualquier*
  cambio pasa, siempre. Son esas cuatro, y son parte del algoritmo de la DNIT.
- **Colisión aislada**: para un valor puntual, dos cadenas dan el mismo DV.
  Ronda el **2%** de los cambios de un dígito en las otras 39 posiciones, y es
  inherente a este módulo 11: la regla "dv = 0 si resto < 2" hace que resto 0
  y resto 1 den el mismo dígito. Un dígito verificador único nunca detecta el
  100%.

**La lección, que vale más allá de este campo.** En un protocolo de
interoperabilidad, "más correcto" no existe como criterio independiente:
existe "igual al otro lado". Cuando falte documentación oficial, la respuesta
está en la implementación de referencia que publica el organismo, no en el
razonamiento propio por más sólido que sea. Y si hay un ejemplo oficial a
mano, hay que contrastarlo **entero** — incluido el campo que da pereza
verificar.

Sobre el **DV del RUC**: `verificar_fiscal` lo chequea solo. Al cargar el RUC
real, si dice que el DV no cierra pero la cédula tributaria dice que sí,
entonces el algoritmo de `ruc.py` no coincide con el del DNIT. En `ruc.py` el
ciclo 2..11 nunca llega a 11 en la práctica, porque el RUC tiene 8 dígitos.

### 5.3 Decisiones abiertas

- ~~**e-Kuatia'i o e-Kuatia.**~~ **Decidido el 14/09/2026: e-Kuatia completo**,
  con habilitación por los **cinco** tipos de documento. La propietaria va a
  conseguir el certificado de firma. El plan de migración, con sus fases y lo
  que el certificado *no* resuelve, está en `docs/migracion_ekuatia.md`.
- ~~**Internet en la PC servidor.**~~ **Resuelto el 14/09/2026**: el local
  tiene servicio y es estable. La cola asíncrona se mantiene igual — cubre
  los cortes, que es distinto de cubrir la ausencia de conexión.
- **Numeración por talonario.** Falta confirmar si la propietaria necesita
  numeración propia por talonario o le sirve la del sistema.

### 5.4 Trabajo técnico que queda

- Sidecar Node con la suite TIPS-SA (`SIFEN_SIDECAR_URL` ya está en
  settings, apuntando a `127.0.0.1:8100`).
- Worker de la cola: levantar los DEs `pendiente` y transmitirlos con
  reintentos.
- KuDE con QR en `printer.py`.
- Nota de crédito para anular ventas ya facturadas (`TIPO_DE_NOTA_CREDITO`
  ya está definido).
> `emisor.emitir_para_pago()` **ya está conectado** a `apps/caja/views.py`
> (`ConfirmarPagoView`), solo para `tipo_comprobante == 'factura'`. Con
> `SIFEN_HABILITADO=False` devuelve `None` y el flujo queda idéntico al
> anterior.

---

## 6. Referencias

- Portal e-Kuatia: <https://www.dnit.gov.py/en/web/e-kuatia>
- Librerías: <https://www.dnit.gov.py/en/web/e-kuatia/librerias>
- Documentación técnica: <https://www.dnit.gov.py/en/web/e-kuatia/documentacion>
- `docs/todo_montaje_servidor.md` §6.5 — estado anterior
