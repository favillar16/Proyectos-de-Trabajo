/**
 * Contenido de la ayuda contextual, por pantalla.
 *
 * Está escrito para la persona que va a usar el sistema en el mostrador, no
 * para quien lo programó: responde dudas concretas ("¿por qué no me deja
 * cobrar?") en vez de describir funciones. Si algo se explica dos veces en
 * el local, va acá.
 *
 * Cada entrada se muestra según la ruta actual. Los bloques con `roles` solo
 * se muestran a esos roles, para que a la vendedora no le aparezcan
 * instrucciones de caja que no puede ejecutar.
 *
 * Para agregar ayuda a una pantalla nueva: sumar una clave con la ruta.
 */

export const ATAJOS_GLOBALES = [
  { teclas: 'F1', descripcion: 'Abrir y cerrar esta ayuda' },
  { teclas: 'Esc', descripcion: 'Cerrar la ayuda o el panel abierto' },
]

/**
 * Duda general que no depende de la pantalla. Se muestra al final siempre.
 */
export const AYUDA_GENERAL = {
  titulo: 'Si algo no funciona',
  bloques: [
    {
      titulo: 'La pantalla no carga o quedó en blanco',
      items: [
        'Bajar el dedo desde arriba para recargar, o pulsar F5 en las PC.',
        'Si sigue igual, revisar que la PC servidor esté encendida: sin esa máquina prendida ningún dispositivo funciona.',
      ],
    },
    {
      titulo: 'Dice "sin conexión" o no guarda los cambios',
      items: [
        'El sistema anda por la red WiFi del local, no por internet. Verificar que la tablet esté conectada a la red del negocio y no a otra.',
        'Los datos de stock, pedidos y caja siempre se piden en vivo al servidor: si no hay red, no se muestran datos viejos a propósito, para que nadie venda algo que ya no está.',
      ],
    },
    {
      titulo: 'Me olvidé la contraseña',
      items: [
        'Solo el administrador puede cambiarla. No hay recuperación por correo: el sistema no tiene internet.',
      ],
    },
  ],
}

export const AYUDA_POR_RUTA = {
  '/showroom': {
    titulo: 'Showroom',
    resumen: 'El catálogo para mostrarle al cliente y armar el pedido.',
    bloques: [
      {
        titulo: 'Para qué sirve esta pantalla',
        items: [
          'Es la vista pensada para mostrarle al cliente: fotos grandes, precios y qué hay disponible.',
          'Desde acá se arma la nota de pedido con lo que el cliente elige.',
        ],
      },
      {
        titulo: 'Consultar un producto con el lector',
        items: [
          'Pasar el lector por el código de la caja abre la ficha de esa variante con su stock, sin buscar nada.',
          'Si el código corresponde a un producto con varias variantes, el sistema muestra la lista para elegir cuál.',
        ],
      },
      {
        titulo: 'Qué significa el stock que veo',
        items: [
          'El número que aparece es el stock DISPONIBLE, que ya descuenta lo reservado por otros pedidos todavía sin pagar.',
          'Por eso puede haber material en el depósito y aun así figurar en cero: está comprometido en otra venta.',
        ],
      },
      {
        titulo: 'El precio que veo no es el que quiero cobrar',
        items: [
          'Los precios se cargan con IVA incluido, que es como se cotiza en el mostrador.',
          'Para clientes con precio negociado (constructoras, mayoristas) el ajuste se hace en el pedido, no cambiando el precio del producto.',
        ],
      },
    ],
  },

  '/productos': {
    titulo: 'Productos',
    resumen: 'Alta y edición del catálogo: productos, variantes y fotos.',
    roles: ['admin', 'encargada_ventas', 'deposito'],
    bloques: [
      {
        titulo: 'Producto y variante: la diferencia',
        items: [
          'El PRODUCTO es el modelo ("Porcelanato Alesso Bege"). La VARIANTE es lo que se vende de verdad: un color y una medida concretos, con su propio precio y su propio stock.',
          'Un producto sin variantes no se puede vender. Siempre hay que cargar al menos una.',
          'El código del producto y el SKU de la variante los genera el sistema solo. No hay que escribirlos.',
        ],
      },
      {
        titulo: 'M²/caja y M²/pallet',
        items: [
          'M²/caja se puede escribir directo, o dejar que el sistema lo calcule con las medidas de la pieza y cuántas piezas entran en la caja.',
          'M²/pallet solo se habilita después de cargar m²/caja, porque el sistema necesita ese dato para convertir.',
          'Estos números son los que después permiten cargar stock en cajas o en pallets en vez de contar metro por metro.',
        ],
      },
      {
        titulo: 'El código de barras de la variante',
        items: [
          'Si la caja del producto trae código impreso, poner el cursor en el campo «Código de barras» y pasar el lector: se completa solo.',
          'Si el producto no trae código, dejarlo vacío. El sistema le genera uno interno y desde Inventario se imprime la etiqueta para pegarle.',
          'Un mismo código no puede estar en dos variantes: si ya está usado, el sistema avisa a cuál pertenece.',
        ],
      },
      {
        titulo: 'Cargar el stock inicial',
        items: [
          'Se puede cargar en metros, en cajas o en pallets. Los botones de caja y pallet aparecen solo si están cargados los m²/caja y m²/pallet.',
          'Si se borra el m²/caja después de haber elegido "cajas", el sistema vuelve solo a metros para que el alta no falle.',
        ],
      },
      {
        titulo: 'Eliminar un producto',
        items: [
          'Solo el administrador ve el botón de eliminar.',
          'Si el producto ya tuvo ventas o movimientos de stock, el sistema NO lo borra: ofrece desactivarlo. Eso lo saca del catálogo y del showroom pero conserva el historial, que es lo que corresponde.',
        ],
      },
    ],
  },

  '/pedidos': {
    titulo: 'Pedidos',
    resumen: 'Las notas de pedido y por qué estado va cada una.',
    bloques: [
      {
        titulo: 'Los estados, en orden',
        items: [
          'PENDIENTE — recién armado. Al crearlo, el sistema ya reservó el material.',
          'EN PREPARACIÓN — el depósito lo está juntando.',
          'LISTO — preparado, esperando que el cliente pase por caja.',
          'PAGADO — se cobró. Recién en este momento el stock se descuenta de verdad.',
          'CANCELADO — se liberó la reserva y el material volvió a estar disponible.',
        ],
      },
      {
        titulo: 'Armar el pedido con el lector',
        items: [
          'Escanear un producto lo agrega directo a la nota de pedido. Si ya estaba, le suma uno más.',
          'Nunca agrega más de lo que hay disponible: si el producto está sin stock, avisa y no lo carga.',
        ],
      },
      {
        titulo: '¿Por qué el stock baja antes de cobrar?',
        items: [
          'No baja: se RESERVA. El material sigue contado en el depósito pero queda apartado para ese cliente, así dos vendedoras no venden el mismo lote.',
          'La baja real ocurre cuando la caja confirma el pago.',
          'Si el pedido se cancela, la reserva se libera sola.',
        ],
      },
      {
        titulo: 'La pantalla se actualiza sola',
        items: [
          'Los pedidos se actualizan en vivo entre dispositivos. Si la caja cobra un pedido, la tablet lo ve cambiar sin recargar.',
          'Si dejó de actualizarse, es señal de que se cortó la red: recargar la pantalla.',
        ],
      },
    ],
  },

  '/caja': {
    titulo: 'Caja',
    resumen: 'Cobros, sesión de caja y comprobantes.',
    roles: ['admin', 'cajero'],
    bloques: [
      {
        titulo: 'Antes de poder cobrar',
        items: [
          'Hay que ABRIR LA SESIÓN de caja con el monto inicial. Sin sesión abierta el sistema no deja registrar ningún cobro.',
          'Cada cajero puede tener una sola sesión abierta a la vez. Si dice que ya hay una abierta, es porque quedó sin cerrar de un turno anterior.',
        ],
      },
      {
        titulo: 'Cobrar un pedido',
        items: [
          'Se busca el pedido, se elige el medio de pago y se confirma.',
          'Al confirmar pasan tres cosas juntas: se descuenta el stock, se marca el pedido como pagado y sale el comprobante impreso.',
          'Si la impresora falla, el cobro igual queda registrado. El comprobante se puede reimprimir.',
        ],
      },
      {
        titulo: 'Ticket o factura',
        items: [
          'El TICKET es el comprobante interno de la venta.',
          'La FACTURA lleva los datos fiscales y exige cargar RUC y razón social del cliente. Sin esos dos datos el sistema no la emite.',
        ],
      },
      {
        titulo: 'Cerrar la caja',
        items: [
          'Al cerrar se cuenta el efectivo y el sistema compara contra lo que registró, mostrando la diferencia si la hay.',
          'Conviene cerrar todos los días aunque no haya diferencia: es lo que deja el arqueo registrado.',
        ],
      },
    ],
  },

  '/inventario': {
    titulo: 'Inventario',
    resumen: 'Stock, movimientos y ajustes.',
    roles: ['admin', 'deposito', 'encargada_ventas'],
    bloques: [
      {
        titulo: 'Los tres números del stock',
        items: [
          'CANTIDAD — lo que hay físicamente en el depósito.',
          'RESERVADO — lo comprometido en pedidos todavía sin cobrar.',
          'DISPONIBLE — cantidad menos reservado. Es lo que realmente se puede vender.',
        ],
      },
      {
        titulo: 'Corregir el stock',
        items: [
          'Todo cambio de stock queda registrado como un movimiento, con quién lo hizo y cuándo. No se puede modificar el número "a mano" sin dejar rastro, y es a propósito.',
          'Si el conteo físico no coincide, se carga un AJUSTE explicando el motivo. Eso deja el historial correcto.',
        ],
      },
      {
        titulo: 'Entró mercadería nueva',
        items: [
          'Se carga como movimiento de entrada sobre la variante correspondiente.',
          'Si viene en cajas o pallets, conviene cargarlo en esa unidad y dejar que el sistema convierta: se cometen menos errores que multiplicando a mano.',
          'Con el lector: pasar el código de la caja abre directamente el panel de ajuste de esa variante, sin buscarla.',
        ],
      },
      {
        titulo: 'El lector de código de barras',
        items: [
          'El lector funciona como un teclado: no hay nada que instalar ni configurar. Pasa el código y el sistema reacciona solo.',
          'Se puede escanear con el cursor en el buscador o sin tocar nada: el sistema distingue un escaneo del tipeo por la velocidad.',
          'Si dice "el código no está asignado a ningún producto", es mercadería que todavía no tiene código cargado. Se le carga desde la ficha del producto, en Productos.',
        ],
      },
      {
        titulo: 'Imprimir etiquetas de código de barras',
        items: [
          'El botón «Etiquetas» arma una planilla A4 con lo que se está viendo en la lista: los filtros de arriba son los que eligen qué etiquetar.',
          'Sale por la Epson L1250. Imprimir SIEMPRE a escala 100%: si se elige "ajustar a la página", el código se achica y el lector deja de leerlo.',
          'Las variantes sin código de barras no aparecen en la planilla. El administrador les genera uno interno de una sola vez.',
        ],
      },
    ],
  },

  '/dashboard': {
    titulo: 'Dashboard',
    resumen: 'Los números del negocio.',
    roles: ['admin'],
    bloques: [
      {
        titulo: 'Qué estoy viendo',
        items: [
          'Ventas, cobros y movimiento de stock del período elegido.',
          'Los datos salen de lo que se cargó en el sistema: si una venta no se registró en caja, acá no aparece.',
        ],
      },
    ],
  },

  '/usuarios': {
    titulo: 'Usuarios',
    resumen: 'Quién puede entrar y qué puede hacer.',
    roles: ['admin'],
    bloques: [
      {
        titulo: 'Los roles',
        items: [
          'ADMIN — acceso a todo, incluidos costos y usuarios.',
          'ENCARGADA DE VENTAS — catálogo, pedidos e inventario.',
          'VENDEDOR — showroom y pedidos.',
          'CAJERO — caja y cobros.',
          'DEPÓSITO — inventario y preparación de pedidos.',
        ],
      },
      {
        titulo: 'Dar de baja a alguien',
        items: [
          'No se borra el usuario: se DESACTIVA. Así deja de poder entrar pero se conservan las ventas y movimientos que hizo, que son parte del historial del negocio.',
        ],
      },
    ],
  },

  '/costos': {
    titulo: 'Costos',
    resumen: 'Gastos operativos, proveedores y empleados.',
    roles: ['admin'],
    bloques: [
      {
        titulo: 'Qué va acá',
        items: [
          'Gastos del negocio, proveedores, empleados y pedidos a proveedores.',
          'Es independiente de las ventas y del stock: cargar un gasto no mueve inventario ni caja.',
        ],
      },
    ],
  },
}

/**
 * Devuelve la ayuda de una ruta, filtrando los bloques que no correspondan
 * al rol. Si la ruta no tiene ayuda propia, devuelve null y el panel muestra
 * solo la ayuda general.
 */
export function ayudaDeRuta(pathname, rol) {
  const entrada = AYUDA_POR_RUTA[pathname]
  if (!entrada) return null
  if (entrada.roles && rol && !entrada.roles.includes(rol)) return null
  return entrada
}
