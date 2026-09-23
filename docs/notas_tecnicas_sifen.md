# Notas Técnicas del SIFEN — registro de revisión

Revisadas las **27** Notas Técnicas publicadas al **14/09/2026**, una por una,
contra lo que el sistema tiene implementado.

## Por qué existe este documento

El Manual Técnico V150 que está en `docs/Documentacion para Facturación
Electrónica/` tiene pie de página de **septiembre de 2019**. La DNIT no
reemplaza el manual cuando algo cambia: le publica una **Nota Técnica**
encima. Leer solo el manual es leer la versión de hace siete años.

El riesgo es del mismo tipo que el del dígito verificador del CDC: silencioso
hasta el día que el SIFEN rechaza todo. De hecho **cuatro** de las notas
corrigen cosas que el sistema tenía mal justamente por seguir el manual base.

La propia especificación de ingeniería del proyecto
(`SIFEN_Specification_ES-000_ES-013/README.md`) lo pide explícitamente: *"No
copiar manualmente tablas o XSD sin registrar su versión y origen"*. Esto es
ese registro.

**Fuente:** <https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica>

Los 27 PDF están versionados en
`docs/Documentacion para Facturación Electrónica/Notas Tecnicas/`, bajados de
ahí el 14/09/2026. Se guardan en el repositorio a propósito y no solo el
enlace: los del portal cuelgan de URLs con token, la DNIT reorganiza el sitio
cada tanto, y volver a bajar y releer 27 documentos para verificar una duda
puntual no es razonable. Es el mismo criterio con el que ya estaban guardados
el Manual Técnico y la Guía de Pruebas.

---

## Lo que se aplicó

Cinco notas obligaron a cambiar código. Están ordenadas por impacto.

### NT 024 (17/12/2024) — el receptor hay que identificarlo desde 7 millones

Es la de mayor impacto sobre la operación del negocio, y no es técnica sino
comercial.

La **NT 021** (29/12/2023) prohibió que el receptor quede *innominado* cuando
el total llega a **35.000.000 Gs**. Un año después la **NT 024** bajó ese
umbral a **7.000.000 Gs** (validación D208c, código 1331).

Siete millones de guaraníes son los pisos de un baño. O sea que en este rubro
**la mayoría de las ventas medianas ya no puede facturarse sin identificar al
comprador**. Alcanza la cédula, no hace falta RUC.

Implementado en `payload._exigir_receptor_identificado()`.

> **Para la propietaria:** esto es una regla del DNIT, no del sistema. Conviene
> avisarle a la cajera antes de que el SIFEN se prenda: en ventas de 7
> millones para arriba hay que pedir cédula o RUC, siempre.

### NT 006 (25/03/2021) — el tipo de transacción no va en las notas

> "No informar el tipo de transacción cuando C002≠1 o 4" (D011a, código 1216).

El payload lo mandaba **siempre**, incluso en notas de crédito, débito y
remisión. Eran tres de los cinco tipos de documento rechazados. Corregido:
solo se declara en factura y autofactura.

### NT 023 (27/08/2024) — las notas nunca van a un receptor innominado

Una nota de crédito, de débito o de remisión no puede emitirse a un receptor
sin identificar, **sin importar el monto** (D208e, código 1331). Tiene
sentido: corrigen o trasladan algo que se le entregó a alguien concreto.

### NT 010 (04/02/2022) — los kilómetros de la remisión son obligatorios

`dKmR` (E505) pasó de opcional a `1-1`. El modelo los tenía opcionales y el
payload los mandaba solo si estaban. Ahora `DatosTraslado.clean()` los exige
y el armado falla claro si faltan.

### NT 009 (09/09/2021) y NT 005 (09/02/2021) — longitudes

| Campo | Antes | Ahora | Qué pasaba |
|---|---|---|---|
| `dCodInt` (E701) código del ítem | — | 1-50 | `Variante.sku` admite 100: había que recortarlo |
| `dDesProSer` (E708) descripción | — | 1-2000 | Se truncaba a 120 por nada; recortar el nombre de un producto en un comprobante legal es peor que mandarlo largo |
| `dNroMatVeh` (E965) matrícula | A 6 | A 6-7 | El modelo tenía `max_length=6` |

### NT 007 (01/02/2022) — la remisión lleva una leyenda legal obligatoria

El campo de información al Fisco (`dInfoFisc`, B006) es **obligatorio** en la
nota de remisión y tiene que llevar el mensaje del art. 3 inc. 7 de la
**RG 41/2014**.

El texto exacto no está en la NT (el ejemplo es una imagen) y **no se
inventa**: es un texto legal. Se configura en `FISCAL_LEYENDA_REMISION` y el
armado del documento falla si está vacío.

> **Pendiente para la contadora:** conseguir el texto literal de esa leyenda.

### NT 013 (20/03/2023) — la fórmula del IVA por ítem

Fijó el cálculo de la base gravada:

```
dBasGravIVA = [100 * EA008 * E733] / [10000 + (E734 * E733)]
```

No hubo que cambiar nada: con proporción gravada 100 y tasa 10 da
`total * 10/11`, que es exactamente lo que hace `codigos.desglosar_iva()`.
Queda un test que contrasta las dos cuentas, para que si alguien toca el
desglose se entere de que se apartó de la fórmula oficial.

---

## Las 27, una por una

| NT | Fecha | Asunto | Estado |
|---|---|---|---|
| 001 | 14/10/2019 | Voluntariedad controlada de la facturación electrónica | No aplica — régimen de adhesión |
| 002 | 16/07/2020 | `iTipIDRec` / `dNumIDRec`: tabla y reglas del documento de identidad | ✅ Ya coincidía (verificado 14/09/2026) |
| 003 | 18/11/2020 | Departamento y ciudad del receptor pasan a condicionales | No aplica — no se manda domicilio del receptor |
| 004 | 29/12/2020 | Elimina la validación de RUC emisor inhabilitado | No aplica — validación del lado DNIT |
| 005 | 09/02/2021 | `dDesPaisRe` 4-50; **`dNroMatVeh` 6-7** | ✅ Aplicado (matrícula) |
| 006 | 25/03/2021 | **No informar tipo de transacción si C002≠1 o 4** | ✅ Aplicado — corrigió un error |
| 007 | 01/02/2022 | **`dInfoFisc` obligatorio en la remisión**; datos de exportación | ✅ Aplicado (leyenda configurable) |
| 008 | 21/09/2021 | Póliza de seguros; `F023` en autofactura | No aplica — otros rubros |
| 009 | 09/09/2021 | **`dCodInt` 1-50; `dDesProSer` 1-2000** | ✅ Aplicado |
| 010 | 04/02/2022 | Elimina `dSisFact`; **`dKmR` obligatorio**; rastreo de mercadería | ✅ Aplicado (kilómetros) |
| 011 | 20/10/2022 | WS de consulta masiva de RUC | No aplica hoy — sería del sidecar |
| 012 | 21/02/2023 | La autofactura debe ser en PYG | No aplica — autofactura no implementada |
| 013 | 20/03/2023 | **Fórmula de base gravada y base exenta por ítem** | ✅ Verificado — nuestra cuenta coincide |
| 014 | 20/03/2023 | Evento de Nominación de Factura Electrónica | Pendiente — la nominación no se implementó (ver abajo) |
| 015 | 14/08/2023 | Validación `H004i` del evento de nominación | Pendiente — ídem |
| 016 | 14/08/2023 | Estándar de firma digital (ley de servicios de confianza) | **Del sidecar** — lo resuelve `xmlsign`, no nuestro código |
| 017 | 14/08/2023 | Mensajes de validación de distrito/ciudad del receptor | No aplica — no se manda domicilio del receptor |
| 018 | 17/11/2023 | Grupo `gOblAfe` (imputación RG90) | No aplica — el grupo es opcional (0-11) |
| 019 | 17/11/2023 | Evento Notificación–Recepción | **Pendiente de releer** — dejó de no aplicar el 20/09/2026 (ver abajo) |
| 020 | 17/11/2023 | Compras públicas / `dCodConDncp` | No aplica — el negocio no vende B2G |
| 021 | 29/12/2023 | Innominado prohibido desde 35.000.000 | Reemplazada por la NT 024 |
| 022 | 09/02/2024 | Código de obligación duplicado (RG90) | No aplica — `gOblAfe` no se usa |
| 023 | 27/08/2024 | `dCantProSer` 1-10p(0-8); `dRucFus`; **notas no pueden ir innominadas** | ✅ Aplicado |
| 024 | 17/12/2024 | **Innominado prohibido desde 7.000.000** | ✅ Aplicado — la de mayor impacto |
| 025 | 23/04/2025 | Cancelación: se excluye la validación de confirmación previa | ✅ Revisada (19/09/2026) — no exige código (ver abajo) |
| 026 | 06/06/2025 | Compras públicas pasan a opcionales | No aplica — el negocio no vende B2G |
| 027 | 09/03/2026 | Evento de Nominación: `iTipIDRec` | Pendiente — con la nominación |

### Las que quedan pendientes de otra fase

Ninguna se descartó por conveniencia. Las que dicen "no aplica" son de rubros
que el negocio no toca (seguros, energía, compras públicas, exportación) o de
funcionalidad que todavía no existe:

- **NT 025** — releída al construir la Fase C el 19/09/2026. Lo que hace es
  **sacar** una validación: hasta esa nota, un DTE que el receptor ya había
  confirmado no se podía cancelar (regla GEC002c, código 4004). Desde abril
  de 2025 esa restricción no corre para el emisor. No hay código que
  escribir: es un motivo de rechazo menos. Se deja anotado porque lo
  contrario —creer que la validación sigue viva— llevaría a bloquear
  cancelaciones que el SIFEN aceptaría.
- **NT 014, 015 y 027** — son las tres del **evento de Nominación**, que
  convierte una venta innominada en nominada cuando el cliente pide la
  factura a su nombre después de emitida. No se implementó: con la NT 024 el
  receptor ya tiene que identificarse desde 7.000.000 Gs, así que el caso
  que la nominación resuelve es el de una venta chica que el cliente quiere
  nominar más tarde. Si aparece en el mostrador, el evento ya tiene su lugar
  (`EventoDocumento`, `sifen_client.enviar_evento('nominacion', ...)`) y el
  sidecar lo soporta: falta el modelo de datos del receptor tardío y releer
  estas tres notas.
- **NT 019** — evento Notificación–Recepción. Es del **rol receptor**: se
  registra sobre documentos que el negocio *recibe* de sus proveedores.

  ⚠️ **Esta fila quedó desactualizada y se detectó el 23/09/2026.** Cuando se
  escribió era cierto que el sistema no llevaba documentos recibidos, pero el
  **20/09/2026** se construyeron `EventoReceptor`, `eventos_receptor.py` y la
  sección «Recibidos» de `FacturacionPage`, que hacen exactamente eso — y la
  notificación de recepción es uno de los cuatro tipos implementados. La nota
  pasó a aplicar y **nadie la releyó**: lo que se implementó salió del Manual
  §11.2 y de `jsonEventoMain.service.js`, no de la NT. Hay que leerla y ver si
  cambia algo de lo que ya está.

  Sirve de recordatorio de que un «no aplica» caduca cuando el alcance crece:
  vale revisar los demás de esta lista cada vez que se suma un módulo.
- **NT 016** — firma digital. Hay que releerla al montar el sidecar; la
  resuelve `facturacionelectronicapy-xmlsign`, pero conviene confirmar que la
  versión que se instale la implemente.
- **NT 011** — consulta masiva de RUC. Serviría para validar el RUC del
  cliente contra el padrón en vez de solo su dígito verificador. Es una mejora
  real, no un requisito.
- **NT 012** — cuando se implemente la autofactura.

---

## Cómo mantener esto

Cuando la DNIT publique la NT 028:

1. Bajarla de la documentación técnica y guardarla en `docs/Documentacion
   para Facturación Electrónica/`.
2. Contrastarla contra `codigos.py`, `payload.py` y los modelos.
3. Agregar una fila a la tabla de arriba, con estado.
4. Si cambia algo, sumar el test a
   `apps/facturacion/tests/test_notas_tecnicas.py`, que es donde vive cada
   regla que sale de una NT y no del manual base.

Cada test de ese archivo dice de qué nota sale. Es a propósito: cuando una NT
futura mueva un umbral, el test que falla señala exactamente qué regla cambió.
