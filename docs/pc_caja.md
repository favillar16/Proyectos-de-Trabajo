# Armado de la PC de Caja

Checklist para dejar operativo el puesto de caja. Complementa
`guia_instalacion_dispositivos.md` §3 con el detalle que ese resumen no
cubre: sobre todo la **impresora térmica**, que es la única parte del puesto
que necesita configuración real.

Tiempo estimado: ~10 minutos si la impresora ya tiene driver instalado.

---

## 1. Lo primero: la PC de caja NO tiene base de datos

Es un **cliente**. No se instala Python, ni Node, ni PostgreSQL, ni este
repositorio. Solo Chrome.

Vale la pena entender el porqué, porque es la pregunta que aparece siempre:

> ¿No conviene que la caja tenga una copia de la base, para que siga
> funcionando si el servidor se cae?

**No.** El control de stock del sistema se apoya en que hay **una sola
base**. `NotaPedido.reservar_stock()` y `descontar_stock()` usan
`select_for_update()` sobre la fila de `Stock` justamente para que dos
personas no vendan el mismo material al mismo tiempo. Ese candado solo
existe dentro de una base de datos.

Con una base propia en la caja, un pago confirmado ahí descontaría stock
**en la base de la caja** y no en la del servidor: el depósito seguiría
viendo material ya vendido, el mismo pallet se vendería dos veces, y las dos
bases quedarían con historias distintas que después nadie puede reconciliar.

La notebook de la propietaria es la única con base propia, y precisamente
por eso es **espejo de solo lectura**: lo que se escriba ahí se pisa en el
sync siguiente (`docs/sync_notebook.md`).

Si el servidor se cae, la caja no vende. Esa es la decisión de diseño, y la
respuesta correcta es que el servidor esté prendido y respaldado
(`respaldo\respaldo.bat`), no repartir copias de la base.

---

## 2. Red

1. Conectar la PC a la **misma red WiFi/cableada** del local que el
   servidor.
2. Confirmar que llega al servidor. En PowerShell:
   ```powershell
   Test-NetConnection -ComputerName 192.168.0.10 -Port 5173
   ```
   (reemplazar por la IP real del servidor — §2 de
   `guia_instalacion_dispositivos.md`). Tiene que decir
   `TcpTestSucceeded : True`.

   Si falla, ver `docs/verificacion_red.md`.

---

## 3. Acceso al sistema

Con el servidor corriendo (`iniciar.bat` en la PC servidor):

1. Abrir Chrome → `http://IP-DEL-SERVIDOR:5173`
2. Iniciar sesión con un usuario de rol **`cajero`**.
3. Dejarlo como una app y no como una pestaña más: menú (⋮) → **Más
   herramientas → Crear acceso directo** → tildar **"Abrir como ventana"**.
   Queda un ícono en el escritorio que abre directo al sistema, sin barra de
   direcciones.
4. Opcional pero cómodo: arrastrar ese ícono a
   `shell:startup` (Win+R → `shell:startup`) para que el puesto abra solo al
   prender la PC.

No hace falta configurar ninguna IP dentro del sistema: el frontend deduce
la dirección del backend del host con el que se abrió la página
(`frontend/src/services/api.js`), así que con entrar por la IP correcta
alcanza.

---

## 4. Impresora térmica (la parte que importa)

### 4.1 Entender dónde se imprime

Esto sorprende, así que conviene tenerlo claro antes de conectar cables:

**El ticket se imprime desde la PC servidor, no desde la PC de caja.**

`apps/caja/printer.py` corre dentro del proceso de Django y manda los bytes
ESC/POS con `win32print`. Cuando la cajera confirma un pago, la que arma e
imprime el ticket es la máquina que corre `daphne` — el servidor. La PC de
caja solo mostró el botón.

Entonces hay dos formas de armarlo:

| Opción | Dónde va la impresora | Resultado |
|---|---|---|
| **A** (recomendada) | USB en la **PC de caja**, compartida en red | El ticket sale al lado de la cajera |
| **B** | USB en la **PC servidor** | El ticket sale donde esté el servidor — sirve solo si están en el mismo mostrador |

La opción A es la que corresponde salvo que las dos PCs estén juntas. El
código ya la contempla: `WindowsPrinter._por_cola_windows` usa la cola de
impresión de Windows, que acepta impresoras compartidas en red.

### 4.2 Compartir la impresora (en la PC de caja)

1. Conectar la **FTX FTXP-80W** por USB e instalar su driver.
2. Imprimir una página de prueba desde Windows para confirmar que funciona
   **antes** de meter el sistema en el medio.
3. Panel de control → **Dispositivos e impresoras** → clic derecho sobre la
   impresora → **Propiedades de impresora** → pestaña **Compartir**.
4. Tildar **"Compartir esta impresora"** y poner un nombre de recurso
   **sin espacios ni acentos**, por ejemplo `TERMICA80`.
5. Anotar el nombre de la PC de caja (`hostname` en PowerShell). La ruta
   final va a ser `\\NOMBRE-PC-CAJA\TERMICA80`.

> Si Windows pide activar la detección de redes, elegir **"Sí"** para redes
> privadas. La red del local tiene que estar marcada como **privada**, no
> pública, o el resto de los equipos no la va a ver.

### 4.3 Conectar el servidor a esa impresora (en la PC servidor)

1. Panel de control → **Dispositivos e impresoras** → **Agregar una
   impresora** → **"La impresora deseada no está en la lista"** →
   **"Seleccionar una impresora compartida por nombre"** →
   escribir `\\NOMBRE-PC-CAJA\TERMICA80`.
2. Confirmar que aparece instalada en el servidor.
3. Editar `backend\.env` en el servidor y poner **exactamente** ese nombre:
   ```
   IMPRESORA_TERMICA_NOMBRE=\\NOMBRE-PC-CAJA\TERMICA80
   ```
4. Reiniciar el sistema (cerrar las dos ventanas negras y volver a correr
   `iniciar.bat`) — el `.env` se lee al arrancar.

⚠️ La impresora tiene que quedar instalada **para el mismo usuario de
Windows que corre `iniciar.bat`** en el servidor. Si se agrega desde otra
cuenta, Django no la va a encontrar.

### 4.4 Probar

En la PC servidor:

```bat
cd backend
venv\Scripts\activate
python diagnostico_impresora.py
```

Ese script lista las impresoras que Windows ve, verifica que la configurada
exista e imprime un ticket de prueba. Si el ticket sale en la PC de caja,
está listo.

Después, la prueba de verdad: hacer una venta completa y confirmar el pago
desde la PC de caja, y ver que el ticket salga solo (`IMPRESORA_AUTO=True`
en el `.env` del servidor).

---

## 5. Verificación final del puesto

- [ ] Chrome abre el sistema desde el ícono del escritorio
- [ ] Entra con el usuario `cajero` y ve el módulo de Caja
- [ ] Puede abrir una sesión de caja
- [ ] Confirma un pago de prueba y el stock baja (verificar en Inventario
      desde otra PC)
- [ ] El ticket sale impreso automáticamente
- [ ] El cierre de caja imprime su reporte

---

## Problemas comunes

**"No carga nada / no se puede acceder al sitio"**
El servidor no está prendido o no corrió `iniciar.bat`. Es la causa en la
mayoría de los casos. Después, revisar la red con
`docs/verificacion_red.md`.

**Carga el sistema pero las pantallas quedan vacías**
El frontend (puerto 5173) responde pero el backend (8000) no. En el
servidor, revisar que la ventana negra de `daphne` siga abierta y sin
errores.

**El pago se confirma pero no imprime**
1. ¿La impresora aparece en el servidor con `python diagnostico_impresora.py`?
2. ¿El nombre en `IMPRESORA_TERMICA_NOMBRE` coincide **carácter por
   carácter** con el que muestra ese listado?
3. ¿La PC de caja está prendida? Si se apaga, el servidor pierde la
   impresora compartida.
4. Revisar la ventana de `daphne`: el error de impresión queda logueado
   (`logger.error` en `printer.py`) sin frenar la venta — el pago se
   registra igual, solo no sale el papel.

**Sale impreso con caracteres raros en vez de acentos**
Es la codificación (`cp850` en `settings.IMPRESORA_TERMICA`). Suele
significar que el driver instalado no es el de la FTX sino uno genérico.

---

## Referencias

- `guia_instalacion_dispositivos.md` — topología completa de los 6 equipos
- `docs/verificacion_red.md` — diagnóstico de conectividad
- `docs/respaldo_y_migracion.md` — respaldo y traslado del servidor
- `backend/diagnostico_impresora.py` — prueba de impresora
