# Traspaso — trabajo pendiente y contexto

**Fecha de corte: 23/08/2026.** Documento pensado para que otra persona o
equipo pueda continuar sin haber participado de las sesiones previas.

Complementa, no reemplaza:

- `docs/facturacion_electronica.md` — detalle técnico de la facturación electrónica
- `docs/todo_montaje_servidor.md` — checklist del armado del local
- `docs/log_revisiones_tecnicas.md` — historial de revisiones
- `CLAUDE.md` — arquitectura del sistema

---

## 0. Lo que hay que entender antes de tocar nada

**Este sistema es un appliance de red local sin dependencia de internet.**
Una PC servidor en el local corre PostgreSQL + daphne + Vite; las tablets y
las otras PC son clientes por WiFi; la notebook de la propietaria mantiene un
espejo de solo lectura.

Dos consecuencias que se olvidan y muerden:

1. **Nada puede quedar bloqueado esperando internet.** Es la razón de que la
   facturación electrónica esté diseñada como cola asíncrona y no como
   llamada sincrónica al SIFEN.
2. **La notebook no escribe.** Lo que se cargue ahí se pisa en la próxima
   sincronización. Nunca asumir que todos los clientes pueden escribir.

---

## 1. Estado de la facturación electrónica

### Qué quedó implementado y probado

App `backend/apps/facturacion/`, con interruptor `SIFEN_HABILITADO` (hoy
`False`). Con el interruptor apagado el sistema factura **exactamente** como
antes: no genera documentos electrónicos y no sale a internet.

**117 tests versionados** en `apps/facturacion/tests/`. Correr con:

```
cd backend
venv\Scriptsctivate
python manage.py test apps.facturacion
```

| Garantía | Test |
|---|---|
| Sin duplicados con varias cajas a la vez | `test_numeracion.ConcurrenciaTests` (6 hilos reales contra Postgres) |
| Correlativo sin huecos | idem |
| Un rollback devuelve el número | `test_numeracion.SecuenciaTests` |
| Rango de timbrado agotado avisa | idem |
| El DV del CDC protege los 43 dígitos | `test_cdc.ProteccionDelDigitoVerificadorTests` |
| El desglose de IVA suma el total exacto | `test_emisor.DesgloseDeIvaTests` |
| Emitir nunca rompe un cobro | `test_emisor.EmitirNoRompeElCobroTests` |
| Con SIFEN apagado nada cambia | `test_integracion_caja.SifenApagadoTests` |
| Reimpresión conserva número y timbrado | `test_integracion_caja.ReimpresionTests` |

Está **conectado** al flujo de cobro (`apps/caja/views.py`,
`ConfirmarPagoView`) y solo se dispara para `tipo_comprobante == 'factura'`.

### Verificado contra el Manual Técnico del SIFEN v150

Se descargó el manual oficial y se contrastó. Quedó confirmado: la
composición de los 44 dígitos del CDC (contra el ejemplo del §10.1), que el
CDC lo genera el sistema del emisor y no el SIFEN, que el KuDE lo muestra
agrupado de a cuatro, y las reglas del código de seguridad (§10.3) — que
además destaparon un bug: se podía generar `000000000`, fuera del rango
permitido. Detalle en `docs/facturacion_electronica.md` §5.2.

### ⚠️ Lo que NO se pudo verificar — leer antes de emitir en producción

1. **El rango de pesos del módulo 11**, tanto en `ruc.py` como en `cdc.py`.
   El manual (§10.2) no lo detalla: remite a un PDF aparte
   (`digito-verificador.pdf`) cuyo **enlace está caído**. Para cerrarlo hay
   que conseguir ese documento o escribir a
   **facturacionelectronica@dnit.gov.py** / Mesa de Ayuda SIFEN.

   Mientras tanto `verificar_fiscal` lo chequea indirectamente: al cargar el
   RUC real, si dice que el DV no cierra pero la cédula tributaria dice que
   sí, el algoritmo no coincide con el del DNIT.

   **Ojo con "corregir" los pesos a ojo.** La primera versión de `cdc.py`
   ciclaba de 2 a 11 igual que `ruc.py`, y eso dejaba 8 de los 43 dígitos
   sin proteger, porque un peso de 11 anula el aporte del dígito
   (11·d ≡ 0 mod 11). Hoy cicla hasta 9 y hay un test que falla si alguien
   vuelve a subirlo. En `ruc.py` el ciclo 2..11 es inofensivo porque el RUC
   tiene 8 dígitos y los pesos nunca llegan a 11.

2. **Tablas de códigos** (`apps/facturacion/codigos.py`): medio de pago,
   condición de operación, naturaleza del receptor, afectación de IVA, tipo
   de documento. Están en la sección *Tablas y Codificaciones* del portal
   del DNIT; no se contrastaron campo por campo.

Ambos puntos están marcados con `⚠️` en el propio código.

### Trabajo técnico que falta

| Qué | Dónde | Nota |
|---|---|---|
| Sidecar Node con la suite `facturacionelectronicapy-*` | nuevo | `SIFEN_SIDECAR_URL` ya está en settings (`127.0.0.1:8100`) |
| Worker que transmite la cola | nuevo | Levanta los DE en estado `pendiente` y reintenta |
| QR del KuDE | `apps/caja/printer.py` | Necesita la firma; hay un `TODO` en el lugar exacto |
| Nota de crédito (anular ventas facturadas) | `apps/facturacion/` | `TIPO_DE_NOTA_CREDITO` ya está definido |
| Eventos de cancelación / inutilización | `apps/facturacion/` | |

### Decisiones de negocio abiertas

- **e-Kuatia'i o e-Kuatia.** Es la decisión de fondo. e-Kuatia'i **no tiene
  API**: la cajera cobraría en el sistema y además cargaría la factura a mano
  en el portal del DNIT. Para que la factura salga sola hay que ir a e-Kuatia
  completo, con certificado y habilitación. Ver
  `docs/facturacion_electronica.md` §1.
- **Internet en la PC servidor.** Hoy el local no tiene. Sin internet no hay
  transmisión al SIFEN por ningún camino.
- **Numeración por talonario.** Falta confirmar con la propietaria si
  necesita numeración propia por talonario o le sirve la del sistema.
- **9 datos fiscales sin cargar.** `python manage.py verificar_fiscal` los
  lista. Detalle y de dónde sale cada uno en
  `docs/facturacion_electronica.md` §5.1.

---

## 2. Sistema de ayudas contextuales

Implementado: F1 y botón «?» flotante abren un panel con la ayuda de la
pantalla actual, filtrada por rol. Contenido en
`frontend/src/ayuda/contenido.js`, presentación en
`frontend/src/components/ayuda/AyudaContextual.jsx`. Para agregar una
pantalla nueva se toca **solo el archivo de contenido**.

### Cubierto por tests

`cd frontend && npm test` — 22 tests que verifican que F1 abre y cierra, que
Escape cierra, que el botón «?» funciona, el filtrado por rol, y que el
contenido cubre las 8 pantallas sin bloques vacíos.

Entre ellos hay uno que verifica que ante F1 se llame a `preventDefault()`,
que es **nuestro** lado del contrato con el navegador.

### ⚠️ Lo único que queda por confirmar a mano

Que **Chrome respete** ese `preventDefault()` y no abra su propia ayuda es
comportamiento del navegador: no se puede probar desde jsdom. F1 no es una
tecla reservada (a diferencia de F11 o F12), así que debería funcionar, pero
conviene abrir el sistema y apretar F1 una vez para confirmarlo. El botón
«?» es independiente y no depende de esto — en las tablets, que no tienen
teclas de función, es la única vía.

---

## 3. Otros pendientes registrados

### Seguridad — RESUELTO en código, falta un paso manual

Había **dos** secretos en texto plano en este equipo, no uno:

1. El token de GitHub en la URL del remoto, en `.git/config`.
2. Un segundo credencial en `~/.git-credentials`, escrito por
   `credential.helper = store` configurado en el `.gitconfig` **global** —
   o sea que afectaba a todos los repos de este usuario, no solo a este.

Ninguno de los dos llegó nunca a commitearse (`git log -S` no los encuentra
en el historial), así que el alcance quedó contenido a este equipo.

**Lo que se hizo el 23/08/2026:**

- La URL del remoto se limpió: ahora es
  `https://github.com/favillar16/Proyectos-de-Trabajo.git`, sin token.
- Se quitó `credential.helper = store` de la configuración global.
- Se borró `~/.git-credentials`.
- Queda como único gestor **Git Credential Manager** (`manager`, el que trae
  Git para Windows), que guarda cifrado en el Administrador de credenciales
  de Windows en vez de en un archivo de texto.
- Verificado: `git ls-remote origin` sigue funcionando, así que los scripts
  desatendidos (`respaldo\subir_fotos.ps1`, `traer_fotos.ps1`) no se rompen.

**⚠️ Lo que falta y solo lo puede hacer una persona:** los dos tokens
estuvieron en texto plano, así que hay que darlos por comprometidos.

1. Revocarlos en GitHub → *Settings → Developer settings → Personal access
   tokens*, y generar uno nuevo.
2. La primera vez que se haga `git push` después de revocarlos, GCM va a
   pedir las credenciales una sola vez. Conviene hacerlo **a mano y no
   desde una tarea programada**, porque un script desatendido se quedaría
   esperando el diálogo. Después de esa vez, queda guardado cifrado y los
   scripts vuelven a andar solos.

**Contraseñas sin rotar.** `admin`, `cajero`, `deposito` y `vendedor` siguen
con `demo2025`, heredada del equipo de armado. Se difirió a propósito hasta
poco antes del lanzamiento (durante el armado hay que loguearse demasiadas
veces). Sigue siendo bloqueante para operar. Ver
`docs/instructivo_entrega_final.md` paso 3.

### Respaldo automático — decisión abierta

El respaldo existe (`respaldo\respaldo.bat`) pero **hay que correrlo a
mano**. Falta decidir estrategia, frecuencia, responsable y retención, y
probar una restauración real. Es lo más importante de la lista después de la
migración. Ver `docs/todo_montaje_servidor.md` §7.

### Observaciones menores

- **`frontend/dist/` está trackeado en git** y se regenera al buildear, así
  que ensucia el diff. `iniciar.bat` levanta el servidor de desarrollo, no
  `dist`. Ya figuraba como tema abierto en `todo_montaje_servidor.md` §9.
- **La notebook tiene 103 productos**, contra los 393 que la documentación
  dice que hay en la PC servidor. O el sync nunca corrió en este equipo, o
  apunta a otra base. Conviene verificarlo antes de sacar conclusiones de
  cualquier dato leído desde la notebook.
- **`CLAUDE.md` documenta mal el comando de migraciones.** Dice
  `makemigrations apps.productos ...` pero las etiquetas de app son cortas:
  `makemigrations productos facturacion`.
- **Los tests del resto del sistema siguen sin existir.** Se agregó la
  primera suite automatizada del proyecto, pero cubre solo facturación
  electrónica y la ayuda contextual. El resto se sigue verificando a mano
  contra `docs/checklist_entrega.md` (59 casos).
- **El channel layer es `InMemoryChannelLayer`.** Alcanza porque hay un solo
  proceso daphne. Si algún día se escala a varios, hay que pasar a Redis.

---

## 4. Cómo retomar

```
cd backend
venv\Scripts\activate
python manage.py verificar_fiscal      # qué falta para poder facturar
python manage.py verificar_fiscal --cdc  # + CDC de prueba descompuesto
```

Orden sugerido:

1. Cargar los 9 datos fiscales en `backend\.env` (las claves ya están en
   `.env.example`).
2. Verificar los tres ⚠️ del §1 contra el Manual Técnico vigente.
3. Decidir e-Kuatia'i vs e-Kuatia.
4. Recién entonces: sidecar, worker y QR.

No prender `SIFEN_HABILITADO=True` hasta tener certificado, habilitación y
los puntos 1 y 2 resueltos.
