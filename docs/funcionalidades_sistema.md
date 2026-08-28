# Funcionalidades del sistema — Óga Porã Gestión Comercial

Resumen de qué hace el sistema hoy, módulo por módulo. Pensado como
referencia rápida para el propietario y para retomar trabajo en sesiones
futuras — no reemplaza el manual de uso (`manual_usuario.docx`) ni la guía
de demo (`guia_demo_propietarios.md`).

Última actualización: agosto 2026.

---

## 1. Usuarios y roles

Cinco roles, cada uno con su propia vista y permisos:

| Rol | Qué puede hacer |
|---|---|
| **Administrador** | Acceso total: todos los módulos, único que ve el Dashboard general, gestiona usuarios (crear, editar, resetear contraseña, activar/desactivar) y es el único con acceso a los reportes PDF/Excel de Caja. |
| **Encargada de Ventas** | Igual que Vendedor, pero además es la única (junto al admin) que puede modificar precios, descuentos o el monto negociado de un pedido. |
| **Vendedor** | Arma pedidos desde el showroom con los precios de catálogo (no puede tocar montos), ve el estado de sus propios pedidos. |
| **Cajero** | Abre y cierra su caja, cobra pedidos "listos para cobrar", puede aplicar un descuento propio al cobrar (hasta 70%), imprime tickets/facturas. |
| **Depósito** | Ve los pedidos pendientes/en preparación, marca ítems como preparados y pasa el pedido a "listo para cobrar". No ve montos ni maneja caja. |

Cada pantalla y cada endpoint del backend solo está disponible para los
roles habilitados — un vendedor, por ejemplo, no puede abrir la pantalla
de Caja ni ver los reportes, aunque conozca la URL.

---

## 2. Catálogo de productos

- **Categorías**: además de las categorías generales (Pisos, Porcelanatos,
  Cerámicas, Sanitarios, Accesorios de Baño, Artículos de Cocina), el
  catálogo tiene subcategorías específicas para sanitarios y accesorios
  (Bachas, Piletas para cocina, Piletas para ropa, Grifería, Duchas,
  Inodoros, Migitorios, Bidés, Duchas higiénicas, Cisternas, Tapas para
  inodoro, Nichos para baño, Espejos, Adhesivos, Pastinas, Plomería, Tiras
  de fondo con tarugo). Cada categoría tiene su propio prefijo de código
  (ej. `PIS-001-OG` para pisos, `GRI-001-OG` para grifería), generado
  automáticamente.
- **Producto → Variante**: un producto (ej. "Porcelanato Roma") agrupa
  variantes (ej. color/medida específicos), que son la unidad real que se
  vende y tiene stock propio.
- **Formulario de alta dinámico**: el formulario de variante muestra solo
  los campos que corresponden según el tipo de producto elegido:
  - **Dimensiones** (largo/ancho): pisos, porcelanatos, cerámicas, bachas,
    piletas, grifería, duchas, nichos, espejos.
  - **Atributos de grifería**: accionamiento (Frío/Monocomando), posición
    (Alta/Baja), montaje (De mesa/De pared).
  - **Atributos de ducha**: accionamiento (Frío/Eléctrico/Monocomando).
  - **Atributos de inodoro**: tipo de cisterna (Alta/Baja).
  - **Rendimiento por caja** (Piezas/caja, m²/caja, Cajas/pallet): solo
    para productos que se venden por m² — no aplica a algo vendido por
    pieza o juego (una bacha, un juego de baño).
  - **Precio diferencial**: precio propio de una variante distinto al
    precio base del producto — solo se muestra cuando el producto tiene
    2 o más variantes cargadas (con una sola no tiene sentido distinguirlo
    del precio base).
- Ya no se piden **espesor**, **peso por caja**, ni **descripción libre**
  del producto al cargarlo (quedan en la base para productos viejos que ya
  los tenían, pero no se vuelven a pedir).
- El segmento de **"Tipos de instalación"** (Piso/Pared/Exterior/etc.) se
  eliminó por completo — era redundante.
- **Costo de adquisición**: visible en la tarjeta del producto (debajo del
  precio de venta) únicamente para los roles Administrador y Depósito —
  para negociar precio con un proveedor sin tener que abrir el detalle.
- **Orden del listado**: selector para ver los productos por destacados
  (default), nombre (A-Z / Z-A), precio (menor a mayor / mayor a menor) o
  más recientes.
- **Búsqueda y filtros**: por nombre, código o marca, y por categoría.

---

## 3. Inventario / Stock

- Cada variante tiene su propio stock (cantidad física, reservado por
  pedidos pendientes de cobro, disponible = cantidad − reservado).
- Todo movimiento de stock (entrada, salida, ajuste, reserva, liberación,
  devolución) queda en un **historial de auditoría inmutable** — nunca se
  edita ni se borra un movimiento ya registrado.
- **Descuento automático de stock**: al confirmar un pago en Caja, el
  stock de las variantes vendidas se descuenta solo, sin intervención
  manual.
- **Carga de stock en cajas o pallets**: para productos que se venden por
  m² y tienen cargados "m²/caja" y "Cajas/pallet", el ajuste de stock en
  Inventario permite cargar la cantidad directamente en cajas o en
  pallets — el sistema hace la conversión a m² automáticamente (ej. 2
  pallets × 40 cajas × 1,44 m² = 115,20 m²).
- **Alertas de stock por porcentaje**, calculadas contra el stock inicial
  cargado al crear la variante:
  - 🟡 **Bajo** — 25% o menos del stock inicial.
  - 🔴 **Crítico** — 15% o menos.
  - 🔴 **Sin stock** — 0.
  Estas alertas se ven en la pantalla de Inventario (banners, contador por
  estado, filtro) y también llegan como notificación en tiempo real a
  Administración y Depósito apenas se cruza el umbral.
- Consulta rápida de stock por código, SKU o nombre (usada también desde
  el showroom).

---

## 4. Costos operativos

- **Gastos del mes**: registro de gastos por categoría (pago a proveedor,
  salario, servicio, otro), con método de pago (efectivo, transferencia,
  crédito, cheque) y seguimiento de cheques por cobrar.
- **Proveedores**: ficha con contacto, RUC, rubro.
- **Empleados**: ficha con cargo y salario base.
- **Pedidos a proveedor**: registro de qué se pidió, a quién, por cuánto y
  para cuándo, con estado (Pendiente → En camino → Recibido, o
  Cancelado).
  - Un pedido puede vincularse a un **producto del catálogo** (opcional).
    Mientras el pedido esté Pendiente o En camino, la tarjeta de ese
    producto en Productos muestra una burbuja **"🚚 Pedido realizado"**
    arriba del indicador de stock — recordatorio visual para no duplicar
    el pedido, con el proveedor y la fecha estimada de entrega al pasar el
    mouse.
  - **Al marcar el pedido como Recibido, el sistema suma el stock
    automáticamente** (ya no hace falta cargarlo aparte en Inventario). Si
    el producto tiene una sola variante, se aplica directo; si tiene
    varias, pide elegir a cuál entra el stock. La cantidad puede cargarse
    en m², cajas o pallets (misma conversión que en Inventario), y queda
    registrada en el historial de movimientos de stock.
  - La burbuja desaparece automáticamente al confirmar la recepción.
- Alertas de cheques próximos a vencer y pedidos a proveedor atrasados.

---

## 5. Ventas y pedidos

- Un **pedido** (nota de pedido) es el carrito que arma el vendedor: datos
  del cliente, lista de productos/variantes con cantidad y precio, y
  totales. Se numera solo (`NP-AAAAMM-0001`).
- **Estados**: Pendiente → En preparación (depósito lo está armando) →
  Listo para cobrar → Pagado, o Cancelado en cualquier momento antes de
  pagarse.
  - Depósito mueve el pedido de Pendiente a En preparación a Listo.
  - El pedido pasa a Pagado únicamente al cobrarse desde Caja — no se
    puede marcar "pagado" a mano, para que no quede un pedido cerrado sin
    un cobro real detrás.
- **Reserva de stock**: al crear el pedido, el stock de cada ítem se
  reserva automáticamente (evita que dos vendedores vendan lo mismo dos
  veces); si algo no tiene stock suficiente, el pedido no se crea. Al
  cancelar, la reserva se libera; al pagar, se descuenta el stock físico
  real.
- **Clientes**: hay un padrón con razón social, RUC/CI, tipo (persona
  física/jurídica) y condición de venta (contado/crédito); se puede
  buscar por nombre o RUC al armar un pedido o facturar, y cargar clientes
  nuevos al vuelo.
- **Precios y descuentos**: un vendedor común arma pedidos a precio de
  catálogo; solo Administrador y Encargada de Ventas pueden ajustar el
  descuento o fijar un monto negociado. Un pedido deja de poder editarse
  en cuanto depósito empieza a prepararlo.
- Todo cambio de estado se ve **en vivo** en las pantallas de los demás
  roles involucrados (sin recargar), vía notificaciones en tiempo real.
- **Nota para el cliente**: desde el detalle del pedido se descarga la nota
  diagramada con el logo y los colores del negocio. Se elige el encabezado
  —**Presupuesto** (lo que se le pasa al cliente para que decida, es la
  opción por defecto) o **Pedido** (la venta ya confirmada)— y el formato.
  Los datos de contacto del pie son los comerciales (correo, teléfono y
  dirección que el negocio le da al cliente), no los fiscales de la
  factura. Los dos formatos sirven para cosas distintas:
  - **PDF** — para imprimir o mandar por WhatsApp. Respeta el diseño de la
    nota que el negocio ya venía usando (logo arriba, cajas de fecha,
    tabla CANTIDAD / PRODUCTO / PRECIO / TOTAL con renglones en blanco al
    final para agregar algo a mano, y la franja de contacto al pie).
  - **Excel** — para trabajarla y editarla. Cantidad y precio unitario van
    como números y el total sale por fórmula, así que cambiar una cantidad
    recalcula solo esa fila y el total general. Trae 12 renglones en
    blanco ya con la fórmula puesta.
  Depósito no ve estos botones: la nota lleva precios y ese rol no maneja
  montos en ninguna pantalla.

---

## 6. Caja

- **Apertura/cierre de sesión de caja**: cada cajero abre su turno con un
  monto inicial contado; solo puede tener una sesión abierta a la vez. Al
  cerrar, carga el monto contado físicamente y el sistema calcula
  automáticamente el total vendido en el turno (desglosado por medio de
  pago) y la diferencia entre lo esperado y lo contado.
- **Cobro de pedidos**: el cajero cobra pedidos que depósito marcó como
  "listos". Medios de pago: efectivo (con cálculo automático de vuelto),
  tarjeta de débito, tarjeta de crédito, transferencia. El cajero puede
  aplicar un descuento propio al momento de cobrar (hasta 70%), aparte del
  que ya traiga el pedido.
- **Impresión térmica**: al confirmar el pago se imprime automáticamente
  un ticket o una factura (con datos fiscales) según elija el cajero, y
  también un comprobante de cierre de caja con el resumen del turno. Se
  puede reimprimir un ticket ya emitido, y el sistema puede chequear si la
  impresora configurada está disponible.
- **Reportes descargables** (solo para el rol Administrador), en PDF o
  Excel:
  - **Reporte de Stock** — todas las variantes con cantidad, reservado,
    disponible, mínimo y estado.
  - **Balance de Ventas** — cobros en un rango de fechas, desglosados por
    medio de pago.
  - **Extracto de Caja** — sesiones de caja del período, con apertura,
    cierre, cajero responsable y total vendido.
  Los PDF se pueden generar en hoja **A4** (por defecto) u **Oficio**, con
  orientación horizontal automática cuando el reporte tiene muchas
  columnas, y pie de página con numeración.

---

## 7. Dashboard

Exclusivo del rol Administrador (el resto de los roles ven una pantalla
simplificada de accesos rápidos a lo suyo). Muestra de un vistazo:

- Ventas de hoy, de la semana y del período elegido (7/30/90 días), cada
  una comparada contra el período anterior.
- Ticket promedio.
- Balance del mes: ingresos vs. gastos operativos (módulo de Costos) y
  margen, con aviso si hay gastos pendientes.
- Gráfico de evolución de ventas diarias.
- Cola de pedidos activos (pendientes / en preparación / listos), con
  acceso directo a cada lista.
- Top 5 productos por ingresos del mes.
- Distribución de ventas por medio de pago.
- Resumen de stock (variantes ok / stock bajo / sin stock).
- Feed de últimas ventas (cliente, medio de pago, cajero, monto).
- Acceso directo al panel de reportes descargables de Caja.

---

## 8. Showroom (tablets)

Pantalla pensada para usarse parada, con el cliente al lado, en las
tablets del local (objetivos táctiles grandes, sin depender de "hover"):

- Grilla de productos con imagen, precio y **badge de stock en vivo**
  (disponible / bajo / sin stock).
- Búsqueda por nombre, código o marca, filtros por categoría y marca.
- **Consulta rápida de stock** aparte, por SKU, código o nombre — para
  responder al toque si hay disponibilidad de algo puntual sin salir de
  la pantalla.
- Quienes pueden vender (admin, encargada de ventas, vendedor) arman el
  pedido directamente desde acá: agregan productos/variantes a la nota de
  pedido y la envían a depósito y caja con un botón.

### Pantalla de Pedidos

Una sola pantalla que cambia según quién la mira:
- **Depósito** ve los pedidos pendientes/en preparación, marca cada ítem
  como preparado y, cuando están todos, pasa el pedido a "Listo para
  cobrar".
- **Vendedor** ve sus propios pedidos con su estado y puede editar datos
  del cliente mientras siga pendiente.
- **Caja** ve los pedidos ya listos para cobrar.
- **Admin** ve todo.

Todo esto se actualiza solo en pantalla (sin recargar) apenas otro rol
cambia algo — por ejemplo, el vendedor ve en el momento cuándo depósito
terminó de preparar su pedido.

---

## 9. Notificaciones en tiempo real

El sistema usa WebSocket (Django Channels) para avisar sin necesidad de
recargar la pantalla: cambios de estado de un pedido, alertas de stock
bajo/crítico/sin stock, y demás eventos relevantes según el rol conectado.

---

## 10. Acceso multi-dispositivo

- **PC servidor**: corre la base de datos, el backend y sirve el
  frontend — es el origen de verdad.
- **Tablets**: instalan el frontend como PWA (app instalable, funciona sin
  navegador abierto) y siempre trabajan contra el servidor en vivo.
- **Notebook del propietario**: mantiene una base de datos propia,
  sincronizada automáticamente cada 5 minutos con el servidor mientras
  esté en la misma red WiFi (espejo de solo lectura — ver
  `docs/sync_notebook.md`). Fuera del local, conserva los últimos datos
  sincronizados.
