# Guía de presentación — Demo para propietarios

## Antes de empezar

**Tiempo estimado:** 25–35 minutos  
**Dispositivos:** 1 PC de escritorio + 1 tablet Redmi Pad SE  
**Preparación:** ejecutar `iniciar_demo.bat` y esperar a que ambos servidores estén activos

---

## Credenciales de demo

| Usuario | Contraseña | Rol | Usar para mostrar |
|---|---|---|---|
| admin | demo2025 | Administrador | Todo el sistema |
| vendedor | demo2025 | Vendedor | Showroom + pedidos |
| cajero | demo2025 | Cajero | Módulo de caja |
| deposito | demo2025 | Depósito | Preparación pedidos |

---

## Estructura de la presentación

### Bloque 1 — El problema que resuelve (2 min)

Antes de mostrar el sistema, establecer el contexto. Preguntar al propietario:

> "Hoy cuando un vendedor quiere saber si tiene stock de un porcelanato específico, ¿qué hace?"

Escuchar la respuesta. Típicamente: llamar al depósito, ir físicamente, revisar un cuaderno o una planilla. Luego decir:

> "Lo que vamos a ver resuelve exactamente eso, y además conecta al vendedor con el depósito y la caja en tiempo real."

---

### Bloque 2 — El showroom digital (8 min)

**Entrar como vendedor** (`vendedor` / `demo2025`)

#### 2a. Primera impresión — el catálogo
- Mostrar el grid de productos con imágenes
- Señalar los badges de stock (verde = disponible, amarillo = stock bajo, rojo = sin stock)
- Hacer scroll para mostrar la variedad de categorías
- Mostrar que los productos destacados aparecen primero

**Punto a remarcar:** *"Esto es lo que ve el vendedor en la tablet cuando está atendiendo a un cliente en el showroom."*

#### 2b. Filtros — encontrar un producto en segundos
1. Tocar el botón de filtros
2. Seleccionar categoría "Porcelanatos"
3. Mostrar que se filtra instantáneamente
4. Activar "Con stock" para ver solo lo disponible
5. Cambiar el orden a "Precio: menor a mayor"

**Punto a remarcar:** *"Sin buscar en catálogos físicos ni llamar a nadie."*

#### 2c. Detalle de producto
1. Tocar el "Porcelanato Roma" (producto destacado)
2. Mostrar la galería de imágenes — deslizar entre fotos
3. Mostrar el desglose de stock por variante (Beige disponible, Blanco Nieve bajo, 30×60 sin stock)
4. Señalar la ubicación en depósito: *"Pasillo A — Estante 1"*

**Punto a remarcar:** *"El vendedor puede decirle al cliente exactamente dónde está la mercadería antes de ir a buscarla."*

#### 2d. Consulta rápida de stock (botón flotante)
1. Cerrar el panel de detalle
2. Tocar el botón circular con el ícono de scanner (abajo a la derecha)
3. Escribir "POR" y esperar los resultados
4. Mostrar todos los porcelanatos agrupados con su stock
5. Borrar y escribir "60x60" — mostrar que busca por dimensión también
6. Borrar y escribir "SAN-001" — coincidencia exacta primero

**Punto a remarcar:** *"Tres segundos para saber el stock de cualquier producto. Desde la tablet, sin ir al depósito."*

---

### Bloque 3 — Vista en la tablet (3 min)

**Cambiar al dispositivo tablet**

1. Abrir Chrome en la Redmi Pad SE
2. Navegar a `http://[IP del servidor]:5173`
3. Iniciar sesión como vendedor
4. Mostrar que la interfaz se adapta automáticamente:
   - La barra de navegación está abajo (más fácil para los dedos)
   - Las cards son más grandes y táctiles
   - Los filtros se colapsan para ganar espacio

**Punto a remarcar:** *"El vendedor puede atender al cliente con la tablet en mano, mostrando fotos en alta calidad y consultando stock en el mismo momento."*

5. Mostrar el deslizamiento de imágenes con el dedo en el panel de detalle

---

### Bloque 4 — Carga de un producto nuevo (5 min)

**Volver a la PC, entrar como admin**

1. Ir a la sección "Productos"
2. Tocar "Nuevo producto"
3. Completar el formulario por pasos:
   - **Paso 1:** código "POR-999", nombre "Porcelanato Demo", categoría Porcelanatos, precio 195.000 Gs.
   - **Paso 2:** agregar variante — color "Gris Antracita", 60×60 cm, stock inicial 20 cajas
   - **Paso 3:** subir una foto de ejemplo (cualquier imagen del celular o escritorio)
4. Guardar

**Punto a remarcar:** *"El administrador carga un producto nuevo en menos de 2 minutos. Inmediatamente aparece en el showroom para todos los vendedores."*

5. Ir al showroom y verificar que aparece el producto recién cargado
6. Buscarlo por código en la consulta rápida

---

### Bloque 5 — Diferenciación por roles (3 min)

**Cerrar sesión e ingresar como cajero**

1. Mostrar que el menú tiene menos opciones — solo lo que el cajero necesita
2. El cajero ve pedidos listos para cobrar (explicar el flujo que viene en la siguiente fase)

**Cerrar sesión e ingresar como depósito**

1. Mostrar el acceso a inventario
2. Mostrar la consulta de stock desde la perspectiva del encargado de depósito

**Punto a remarcar:** *"Cada persona del negocio ve solo lo que le corresponde. El vendedor no puede tocar la caja, el cajero no puede modificar el catálogo."*

---

### Bloque 6 — Lo que viene (2 min)

Explicar brevemente las próximas funcionalidades (sin mostrarlas, aún están en desarrollo):

> **Notas de Pedido:** el vendedor arma la orden con el cliente, el depósito la recibe automáticamente para preparar la mercadería, y caja la ve lista para cobrar. Todo sin papeles ni llamadas.

> **Módulo de caja:** registro de cobros, tickets impresos con la impresora térmica, y cierre de caja al final del día.

> **Dashboard:** ventas del día, stock crítico, movimientos del depósito, todo en una pantalla.

---

## Preguntas frecuentes de propietarios

**"¿Y si se corta internet?"**  
El sistema funciona en red local WiFi dentro del negocio. No necesita internet para operar el día a día. Internet solo es necesario para actualizaciones del sistema.

**"¿Cuándo se pueden empezar a cargar los productos reales?"**  
En cualquier momento. El panel de administración permite cargar desde el primer día. Se recomienda empezar con los productos más vendidos y agregarlos progresivamente.

**"¿Las imágenes se pueden sacar con el celular?"**  
Sí. Las fotos de productos pueden tomarse con cualquier celular y subirse directamente desde la computadora o la tablet.

**"¿Qué pasa si un vendedor se equivoca?"**  
Todos los movimientos de stock quedan registrados con fecha, hora y usuario. El administrador puede ver el historial completo y corregir lo que sea necesario.

**"¿Se puede usar en más de una computadora a la vez?"**  
Sí, ese es el diseño. Las tres PCs del negocio y las tablets pueden usarlo simultáneamente, todos viendo el mismo stock en tiempo real.

**"¿Cuánto tiempo lleva cargarlo todo?"**  
Depende del catálogo. Con fotos y variantes completas, un producto tarda 2–3 minutos. Para un catálogo de 200 productos, se recomienda hacerlo en sesiones de 1 hora durante la semana previa a la puesta en marcha.

---

## Qué NO mostrar en esta demo

- El módulo de caja (no está completo aún)
- Las notas de pedido (sprint siguiente)
- El dashboard (sprint siguiente)
- Cualquier flujo que requiera que dos ventanas estén abiertas simultáneamente

Si el propietario pregunta por estas funciones: *"Eso lo vemos en la presentación del 21 de mayo, que es cuando esa parte queda lista."*

---

## Cierre de la presentación

Terminar con una pregunta concreta:

> "¿Hay algo que vieron hoy que no refleja cómo trabajan ustedes en el negocio? ¿Algo que cambiarían?"

Tomar nota de las respuestas. Son el insumo directo para ajustar la fase 3.

---

*Demo preparada: mayo 2025 — Sistema versión fase 2*
