# Datos fiscales de Óga Porã E.A.S.

Extraídos de los dos documentos de la DNIT que están en `docs/`:

- `Constancia DE RUC OGA PORA EAS.pdf` — constancia de RUC, emitida 26/08/2026
- `TIMBRADO FACTURADOR ELECTRONICO OGA PORA EAS.pdf` — habilitación como
  facturador electrónico, **estado Aprobado**

Con esto se completa lo que `python manage.py verificar_fiscal` venía marcando
como faltante.

## Identificación

| Dato | Valor |
|------|-------|
| RUC | **80173107** — DV **0** |
| Razón social | ÓGA PORA E.A.S. |
| Nombre de fantasía | ÓGA PORA |
| Tipo de sociedad | Empresa por Acciones Simplificadas (E.A.S.) |
| Fecha de constitución | 05/06/2026 |
| Inicio de actividades | 17/06/2026 |
| Cierre de ejercicio | Diciembre (mes 12) |
| Registro de comercio | N.º 31173, 17/06/2026 |
| RUC anterior | GPET2665702 |

## Domicilio fiscal

| Dato | Valor |
|------|-------|
| Departamento | CAAGUAZÚ |
| Distrito / Ciudad | CNEL. OVIEDO |
| Localidad | CNEL. OVIEDO |
| Barrio | SAN ISIDRO |
| Dirección | CALLE LIDIA PERALTA DE BENÍTEZ E/ JOSEFINA PLAS |
| Teléfono | (0971) 451936 |
| Correo (contable) | consultoracontablemymcov@gmail.com |

El establecimiento habilitado es el **001 — MATRIZ**, en esa misma dirección.

## Facturación electrónica

| Dato | Valor |
|------|-------|
| Solicitud de habilitación | **364010060120** — estado **Aprobado** |
| Modalidad de emisión | **Solución gratuita** (e-Kuatia'i) |
| **Timbrado** | **18936285** |
| Estado del timbrado | ACTIVO |
| Inicio de vigencia | **23/06/2026** |
| Establecimiento | 001 |
| Punto de expedición | 001 |
| Documentos habilitados | Factura electrónica · Nota de crédito electrónica |
| ID | 1 |

> El código de seguridad (CSC) de la habilitación figura en el PDF del
> timbrado. **No lo copio acá ni al repositorio**: va en el `.env` de la PC
> servidor, que no se versiona.

La resolución que aplica es la **RG DNIT N.º 06/2024**, y la aprobación
recuerda cumplir el **art. 2.º incs. b y c de la RG DNIT N.º 19/2024**.

## Actividades económicas

| Código | Descripción | Principal |
|--------|-------------|-----------|
| **47523** | Comercio al por menor de otros materiales de construcción tales como ladrillos, madera, equipo sanitario | Sí |
| 46633 | Comercio al por mayor de pinturas, barnices, papel de empapelar y revestimiento de pisos | No |

En la solicitud del facturador aparecen como `C4_47523` y `C4_46633`.

## Obligaciones vigentes (todas desde 17/06/2026)

| Código | Descripción |
|--------|-------------|
| 211 | IVA General |
| 700 | IRE General |
| 726 | RET. IDU |
| 735 | Anticipo IRE |
| 948 | Estados financieros |
| 954 | DJI IDU |
| 955 | Registro mensual de comprobantes |

## Personas

**Socios**

| Documento | Número | Nombre |
|-----------|--------|--------|
| Cédula | 3809154 | RUBEN DARIO SOTO NARVAEZ |
| Cédula | 4054621 | MARIA PAMELA PEREIRA RIVAS |

**Representante legal:** RUBEN DARIO SOTO NARVAEZ, cédula 3809154.

> Esto explica dos cosas del lote de facturas de compra: las de **SiderAgro**
> están a nombre de Rubén Darío Soto Narváez y la de **Prolar Shop** a nombre de
> Pamela Pereira — son los socios comprando a título personal, no la E.A.S.

---

## ⚠️ Antes de cargar el timbrado: la modalidad cambia qué puede hacer el sistema

**«Solución gratuita» es e-Kuatia'i, y e-Kuatia'i no tiene API.** La factura
electrónica se emite **en el portal del DNIT**, cargada a mano. El sistema no
puede emitirla, y `SIFEN_HABILITADO` se queda en `False` — no de forma
transitoria, sino mientras la modalidad sea esta.

De ahí se desprenden tres cosas a resolver antes de pegar el bloque de abajo:

1. **El timbrado 18936285 pertenece a los documentos que se emiten en el
   portal**, no a un papel que imprima esta PC. Hoy `FacturaBuilder`
   (`apps/caja/printer.py`) ya imprime comprobantes que dicen `FACTURA` y
   `* COMPROBANTE LEGAL *`; agregarles ese timbrado los haría pasar por un
   documento que no son. **Cargar `FISCAL_TIMBRADO` recién después de decidir
   qué imprime el sistema.**

2. **Óga Porã no está habilitada como autoimpresor.** La habilitación es como
   facturador electrónico por la solución gratuita. Son cosas distintas: la
   primera autoriza a imprimir comprobantes desde software propio, la segunda
   no.

3. **El timbrado está vigente desde el 23/06/2026.** Si desde entonces se sigue
   facturando en papel, es una pregunta de cumplimiento, no de software. El
   contacto registrado en la habilitación es la consultora contable: es la vía
   más corta para responderla, junto con el **art. 2.º incs. b y c de la RG DNIT
   19/2024** que la propia aprobación señala como lo que sigue.

**Lo que el sistema sí puede aportar bajo e-Kuatia'i** es preparar y validar los
datos de cada venta para que la cajera los cargue rápido en el portal, en vez de
transcribirlos del papel. Eso no está hecho, y es el trabajo que tendría sentido
encarar.

Nada de esto invalida cargar el resto de los datos: sirven igual para el ticket
interno y para dejar el sistema consistente.

---

## Bloque para el `.env` de la PC servidor

Pegar en `backend/.env` (los códigos de departamento/distrito/ciudad quedan
marcados: son los códigos de la **tabla geográfica del SIFEN**, que no figuran
en la constancia — hay que sacarlos del manual técnico o del Marangatú, no se
pueden deducir del nombre).

```dotenv
# ─── Datos fiscales (facturación) ───────────────────────────────────────────
FISCAL_RUC=80173107-0
FISCAL_RAZON_SOCIAL=ÓGA PORA E.A.S.
FISCAL_DIRECCION=CALLE LIDIA PERALTA DE BENÍTEZ E/ JOSEFINA PLAS - B° SAN ISIDRO - CNEL. OVIEDO
FISCAL_TELEFONO=0971451936
FISCAL_TIMBRADO=18936285
FISCAL_TIMBRADO_VTO=

FISCAL_ESTABLECIMIENTO=001
FISCAL_PUNTO_EXPEDICION=001
FISCAL_TIPO_CONTRIBUYENTE=2

# Domicilio desglosado — los códigos numéricos son de la tabla del SIFEN
FISCAL_DEPARTAMENTO=            # ← CAAGUAZÚ (falta el código SIFEN)
FISCAL_DEPARTAMENTO_DESC=CAAGUAZU
FISCAL_DISTRITO=                # ← CNEL. OVIEDO (falta el código SIFEN)
FISCAL_DISTRITO_DESC=CNEL. OVIEDO
FISCAL_CIUDAD=                  # ← CNEL. OVIEDO (falta el código SIFEN)
FISCAL_CIUDAD_DESC=CNEL. OVIEDO

FISCAL_ACTIVIDAD_CODIGO=47523
FISCAL_ACTIVIDAD_DESC=Comercio al por menor de otros materiales de construcción tales como ladrillos, madera, equipo sanitario
```

### Lo que todavía falta

**Decisiones, antes que datos:**

- **Qué imprime el sistema.** Ver el aviso de más arriba. Mientras no esté
  resuelto, dejar `FISCAL_TIMBRADO` vacío.
- **Confirmar con la contadora** desde cuándo corre la obligación de emitir por
  el portal, y qué exige el art. 2.º incs. b y c de la RG 19/2024.

**Datos.** Ojo con los puntos 2 y 3: bajo e-Kuatia'i **no hacen falta**, porque
el sistema no arma el XML ni el QR. Quedan pendientes solo si algún día se pasa
a solución propia. Por eso `verificar_fiscal` los va a seguir marcando como
faltantes, y está bien que lo haga.

1. **`FISCAL_TIMBRADO_VTO`** — la habilitación dice inicio de vigencia
   23/06/2026 pero **no imprime fecha de fin**. Para los timbrados electrónicos
   suele no vencer; confirmar en Marangatú antes de dejar el campo vacío.
2. **Códigos SIFEN de departamento / distrito / ciudad** — son numéricos y no
   están en la constancia.
3. **Código de seguridad (CSC)** — está en el PDF del timbrado, va al `.env` de
   la PC servidor y **no se versiona**.
4. Correr `python manage.py verificar_fiscal` en el servidor para confirmar que
   ya no marca faltantes.
