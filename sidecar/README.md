# Sidecar SIFEN

Proceso Node que firma los documentos electrónicos y los transmite al SIFEN.
Lo consume `backend/apps/facturacion/sifen_client.py`; no lo usa nadie más y
no se expone a la red.

```
cd sidecar
npm install
npm start          # queda escuchando en http://127.0.0.1:8100
npm test           # 10 tests de la interpretación de la respuesta del SIFEN
```

En la PC de la tienda lo levanta `iniciar.bat` junto con daphne y Vite, y lo
baja `detener.bat`. `setup.bat` corre su `npm install`.

## Por qué existe

Firmar un XML y abrir un TLS mutuo con certificado, desde Python sobre
Windows, exige `xmlsec`, que es binario nativo y difícil de instalar. La DNIT
publica librerías de referencia en Node (`facturacionelectronicapy-*`, de
TIPS-SA) que ya resuelven las dos cosas, y la PC servidor ya tiene Node
instalado para Vite.

## Qué expone

Todo es POST con JSON. El contrato está definido —y probado— del lado Django,
en `sifen_client.py`, que se escribió **antes** que este proceso a propósito.

| Ruta | Entra | Sale | ¿Certificado? |
|---|---|---|---|
| `/xml` | `{params, data, test}` | `{xml}` | no |
| `/firmar` | `{xml}` | `{xml}` | sí |
| `/qr` | `{xml}` | `{xml}` | no (usa el CSC) |
| `/enviar` | `{xml}` | `{estado, codigo, mensaje, protocolo, respuesta}` | sí |
| `/consultar` | `{cdc}` | ídem | sí |
| `/evento/<tipo>` | `{params, data}` | ídem, más `xml` | sí |
| `/salud` | `{}` | diagnóstico | lo reporta |
| `/geografia` | `{departamento?, distrito?}` | tablas de la DNIT | no |

`/salud` y `/geografia` también responden por GET, para poder mirarlos con
curl sin armar un POST.

## Los códigos HTTP son parte del diseño

De esto depende que la cola de `transmision.py` reintente lo que corresponde:

- **200** — el SIFEN contestó. Incluso "Rechazado": eso es una respuesta, no
  una falla.
- **422** — el pedido está mal o falta configuración (no hay certificado, el
  CDC no tiene 44 dígitos, el evento no existe). Reintentarlo da lo mismo, así
  que Django lo trata como **terminal**.
- **502** — no se pudo hablar con el SIFEN, o pasó algo que no entendemos.
  Puede ser el corte de internet de la tienda: **reintentable**.

Ante la duda va 502. La asimetría es deliberada: reintentar de más gasta
intentos, pero dar por rechazado un documento válido pierde una venta ya
cobrada y eso no se deshace.

## Configuración

No tiene archivo propio: lee **el mismo `backend/.env` que Django**
(`config.js`). Con dos configuraciones separadas, el día que alguien cambia
`SIFEN_AMBIENTE` en una sola, el sistema firmaría para un ambiente y
transmitiría al otro, y el síntoma sería un rechazo incomprensible.

Claves que mira: `SIFEN_AMBIENTE`, `SIFEN_CERT_PATH`, `SIFEN_CERT_PASSWORD`,
`SIFEN_CSC_ID`, `SIFEN_CSC`, `SIFEN_TIMEOUT`, y `SIFEN_SIDECAR_PUERTO` /
`SIFEN_SIDECAR_HOST` / `SIFEN_SIDECAR_DEBUG`, que son propias.

### Escucha solo en 127.0.0.1, y tiene que seguir así

El sidecar tiene la clave del `.p12` en memoria y firma cualquier XML que le
manden, sin preguntar quién es. En esta LAN —con las tablets conectadas,
`ALLOWED_HOSTS=*` y CORS abierto— publicarlo en `0.0.0.0` sería entregar la
firma electrónica del contribuyente a cualquiera que esté en la WiFi. Django
corre en la misma máquina, así que loopback alcanza. Si alguna vez hiciera
falta cambiarlo, hay que ponerle autenticación primero.

## Tres cosas que se verificaron leyendo el código de las librerías

No están en los README y cambian decisiones de despliegue.

**1. `signByNodeJS` va en `true`, y no es opcional.** Es el último parámetro
de `signXML` y por defecto es `false`. Con `false`, `xmlsign` usa
`XMLDsigJava`: busca un JRE con `find-java-home` y hace `exec` de
`java -classpath ... SignXML`. Eso significaría instalar y mantener **Java en
la PC de la tienda**. Con `true` firma en Node, con `xml-crypto` y
`node-forge`. (`xmlsign/dist/index.js`)

**2. `facturacionelectronicapy-kude` no se instaló, a propósito.** Su
`generateKUDE` recibe un `java8Path` y una carpeta de plantillas `.jasper`:
es un envoltorio de JasperReports y arrastra Java 8 y las plantillas. El KuDE
en PDF se va a armar con reportlab del lado de Django, reusando el motor de
`nota_pedido_doc.py`, que ya genera PDF con la marca del negocio.

**3. `config.test` de `xmlgen` NO marca el documento como de prueba.** Es
andamiaje que quedó de la NT 013 (2023), cuando una fórmula del IVA entró en
test un mes antes que en producción; las dos fechas ya pasaron y hoy los dos
caminos calculan igual (`jsonDteItem.service.js`, bloque "Vigencia en test y
produccion"). Lo que de verdad distingue un documento de prueba es la leyenda
literal que exige la Guía de Pruebas §2, y esa la pone Django en
`payload._marcar_como_prueba()`.

## Cómo probarlo sin certificado

Armar el XML es lo único que no necesita la firma, y alcanza para verificar
casi toda la cadena:

```
cd backend
python manage.py sifen_probar --salud            # ¿está vivo el sidecar?
python manage.py sifen_probar --payload          # el JSON, sin llamarlo
python manage.py sifen_probar --documento 4      # payload → sidecar → XML
```

`sifen_probar` además contrasta el CDC: Django no se lo manda al sidecar, así
que `xmlgen` lo calcula por su cuenta y el comando compara los dos. Son dos
implementaciones independientes del mismo dígito verificador, el que estuvo
mal desde agosto de 2026 hasta que se corrigió.

## Lo que falta para transmitir de verdad

El certificado (`.p12` con el RUC adentro y **Extended Key Usage
`clientAuth`** — `setapi` arma un `https.Agent` con la clave privada, o sea
que el certificado es también la credencial de cliente del TLS mutuo), el
timbrado nuevo bajo software propio, y aprobar la Guía de Pruebas. Ver
`docs/migracion_ekuatia.md`.
