"""
Armado del JSON que consume el generador de XML del SIFEN.

El sidecar Node usa `facturacionelectronicapy-xmlgen`, la librería que la
DNIT publica como referencia, y esa librería recibe dos objetos:

  · `params` — los datos fijos del contribuyente emisor (RUC, timbrado,
    establecimientos). Cambian de año en año, no de factura en factura.
  · `data`   — los datos variables de ESTE documento: receptor, ítems,
    condición de pago, totales.

Este módulo traduce el modelo del sistema a esos dos objetos. Es el único
lugar donde se conoce la forma que espera xmlgen: si la librería cambia su
contrato, se cambia acá.

⚠️ La estructura no se inventó: está transcrita del README de
facturacionelectronicapy-xmlgen (revisado el 14/09/2026) y los códigos salen
de `codigos.py`, que a su vez está contrastado contra el Manual Técnico V150.
Es la misma disciplina que se aplicó al dígito verificador: cuando falta
documentación oficial, manda la implementación de referencia del organismo,
no lo que uno supone.

A diferencia de `emisor.py`, acá **sí se puede lanzar**. El armado del
payload ocurre en el worker de la cola, no durante el cobro: cuando esto
corre, la venta ya terminó y el cliente ya se fue. Un error tiene que
frenar el envío y quedar visible, no colarse como un DE mal formado.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from . import codigos

# Versión del Manual Técnico que declara el XML. Va también en el QR.
VERSION_MANUAL = 150

# Moneda: el negocio factura solo en guaraníes. Si algún día vende en
# dólares hay que sumar el tipo de cambio (campos `cambio` de xmlgen).
MONEDA = 'PYG'

# Presencia de la operación (campo E011 del manual). 1 = operación
# presencial, que es lo que pasa siempre en un mostrador.
PRESENCIA_PRESENCIAL = 1

# Tabla 5 del Manual Técnico (Codificaciones), traducida desde
# Producto.UNIDADES. El SIFEN no acepta la unidad como texto libre.
UNIDAD_MEDIDA_SIFEN = {
    'm2':    109,   # M2  — metros cuadrados
    'ml':    660,   # ml  — metro lineal
    'pieza':  77,   # UNI — unidad
    'juego':  77,   # UNI — un juego se vende como una unidad
    'caja':   77,   # UNI — la caja es la unidad de venta
}
UNIDAD_MEDIDA_POR_DEFECTO = 77   # UNI

# Precisión del descuento por unidad (dDescItem).
#
# Hace falta tanta por una razón concreta del rubro: acá se vende por metro
# cuadrado, así que la cantidad es fraccionaria (2,35 m²). El SIFEN pide el
# descuento POR UNIDAD, y entonces la línea vale (precio − descuento) × 2,35.
# Con cualquier precisión finita, ese producto no cae exactamente en un
# número entero de guaraníes: queda un residuo.
#
# No es un error que se pueda "arreglar" — es aritmética. Lo que se puede es
# acotarlo muy por debajo de la unidad mínima de la moneda: con 8 decimales
# el residuo de una línea queda del orden de 10⁻⁷ Gs, y el de un comprobante
# entero muy por debajo de 1 Gs.
#
# ⚠️ Cuánta diferencia tolera el SIFEN al recalcular los totales es algo que
# solo se puede confirmar contra su ambiente de pruebas, que necesita la
# habilitación. Hasta entonces esto queda como el mejor esfuerzo verificable
# localmente. Ver docs/migracion_ekuatia.md.
PRECISION_DESCUENTO = Decimal('0.00000001')

# Tolerancia con la que se considera que el comprobante "cuadra": menos de un
# guaraní. El guaraní no tiene centavos, así que por debajo de eso no hay
# diferencia representable en la moneda.
TOLERANCIA_CUADRE = Decimal('1')

# Afectación del IVA (Tabla 6) derivada de la tasa del producto. El SIFEN
# distingue "exento" de "gravado al 0%": acá tasa 0 significa exento.
AFECTACION_POR_TASA = {
    codigos.TASA_10: codigos.IVA_GRAVADO,
    codigos.TASA_5:  codigos.IVA_GRAVADO,
    codigos.TASA_0:  codigos.IVA_EXENTO,
}


# ─── Ambiente de pruebas de la DNIT ──────────────────────────────────────────
#
# La Guía de Pruebas §2 ("Set de Pruebas") exige que los documentos del
# ambiente de test lleven un texto literal, en dos lugares:
#
#   · el nombre o razón social del EMISOR, y
#   · la descripción del PRIMER ítem de mercadería.
#
# Es una marca para que un documento de prueba no pueda confundirse con uno
# real. El resto de los datos —RUC, dirección, receptor— tienen que ser los
# verdaderos, tal como figuran en Marangatú.
#
# ⚠️ Esto NO lo hace la librería. Se revisó `xmlgen` y su opción `config.test`
# no marca el documento de ninguna manera: es andamiaje que quedó de la
# implementación de la NT 013 en 2023, cuando la fórmula del IVA entró en test
# un mes antes que en producción. Las dos fechas ya pasaron y hoy los dos
# caminos calculan igual (ver jsonDteItem.service.js, "Vigencia en test y
# produccion"). O sea que sin este bloque los documentos de prueba saldrían
# sin la leyenda y la DNIT los devolvería.
LEYENDA_AMBIENTE_PRUEBA = (
    'DOCUMENTO ELECTRÓNICO SIN VALOR COMERCIAL NI FISCAL - '
    'GENERADO EN AMBIENTE DE PRUEBA'
)


def en_ambiente_de_pruebas() -> bool:
    """¿Se está emitiendo contra el ambiente de test de la DNIT?"""
    return getattr(settings, 'SIFEN', {}).get('ambiente', 'test') != 'produccion'


def _marcar_como_prueba(params: dict, data: dict) -> None:
    """
    Pone la leyenda obligatoria del ambiente de test.

    Muta `params` y `data` al final del armado, a propósito: así el payload se
    construye una sola vez, igual para los dos ambientes, y la marca es un
    paso aparte que se ve y se puede probar. Si estuviera repartida adentro del
    armado habría que acordarse de ella en cada tipo de documento.
    """
    params['razonSocial'] = LEYENDA_AMBIENTE_PRUEBA
    params['nombreFantasia'] = LEYENDA_AMBIENTE_PRUEBA
    if data.get('items'):
        data['items'][0]['descripcion'] = LEYENDA_AMBIENTE_PRUEBA


class DatosIncompletos(ValueError):
    """
    Falta información para armar el documento.

    Se lanza con el detalle de qué falta y de dónde tendría que salir. No es
    un error de programación: son datos que el sistema todavía no captura.
    """


def _dec(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _gs(valor) -> Decimal:
    """Redondea a guaraníes enteros. El guaraní no tiene centavos."""
    return _dec(valor).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def _fiscal() -> dict:
    """Los datos fiscales configurados del emisor."""
    return getattr(settings, 'DATOS_FISCALES', {})


# ─── params: el contribuyente emisor ─────────────────────────────────────────

def construir_params(documento=None) -> dict:
    """
    Datos fijos del emisor.

    Si se pasa un `documento`, los datos que el DE tiene guardados como
    snapshot ganan sobre los de settings. Es la misma razón por la que existe
    el snapshot: retransmitir un documento de hace seis meses tiene que
    mandar el timbrado que tenía entonces, no el vigente hoy.

    Los datos que el snapshot NO guarda (domicilio desglosado, actividad
    económica, régimen) salen igual de settings. Es una limitación conocida:
    si esos cambian, una retransmisión vieja saldría con los nuevos. En la
    práctica casi nunca cambian, y snapshotearlos exige una migración.
    """
    fiscal = _fiscal()

    def dato(clave, campo_snapshot=None):
        if documento is not None and campo_snapshot:
            valor = getattr(documento, campo_snapshot, '') or ''
            if str(valor).strip():
                return valor
        return fiscal.get(clave, '')

    ruc_completo = str(dato('ruc', 'emisor_ruc')).strip()
    faltantes = [nombre for nombre, valor in [
        ('FISCAL_RUC', ruc_completo),
        ('FISCAL_RAZON_SOCIAL', dato('razon_social', 'emisor_razon_social')),
        ('FISCAL_TIMBRADO', dato('timbrado', 'emisor_timbrado')),
        ('FISCAL_TIMBRADO_INICIO', fiscal.get('timbrado_inicio')),
        ('FISCAL_ACTIVIDAD_CODIGO', fiscal.get('actividad_economica')),
        ('FISCAL_DEPARTAMENTO', fiscal.get('departamento')),
        ('FISCAL_DISTRITO', fiscal.get('distrito')),
        ('FISCAL_CIUDAD', fiscal.get('ciudad')),
    ] if not str(valor or '').strip()]
    if faltantes:
        raise DatosIncompletos(
            'Faltan datos fiscales para armar el XML: ' + ', '.join(faltantes)
            + '. Correr: python manage.py verificar_fiscal')

    return {
        'version': VERSION_MANUAL,
        'ruc': ruc_completo,
        'razonSocial': dato('razon_social', 'emisor_razon_social'),
        'nombreFantasia': fiscal.get('nombre_fantasia') or dato(
            'razon_social', 'emisor_razon_social'),
        'actividadesEconomicas': [{
            'codigo': str(fiscal.get('actividad_economica')),
            'descripcion': fiscal.get('actividad_desc', ''),
        }],
        'timbradoNumero': str(dato('timbrado', 'emisor_timbrado')),
        # Fecha de INICIO de vigencia del timbrado (campo dFeIniT), no la de
        # vencimiento. Son datos distintos y el SIFEN valida contra el
        # timbrado registrado: mandar una por la otra es rechazo seguro.
        'timbradoFecha': str(fiscal['timbrado_inicio']),
        'tipoContribuyente': int(fiscal.get('tipo_contribuyente', 2)),
        'tipoRegimen': int(fiscal.get('tipo_regimen') or codigos.REGIMEN_CONTABLE),
        'establecimientos': [{
            'codigo': str(fiscal.get('establecimiento', '001')),
            'direccion': dato('direccion', 'emisor_direccion'),
            'numeroCasa': str(fiscal.get('numero_casa') or '0'),
            'departamento': int(fiscal['departamento']),
            'departamentoDescripcion': fiscal.get('departamento_desc', ''),
            'distrito': int(fiscal['distrito']),
            'distritoDescripcion': fiscal.get('distrito_desc', ''),
            'ciudad': int(fiscal['ciudad']),
            'ciudadDescripcion': fiscal.get('ciudad_desc', ''),
            'telefono': dato('telefono', 'emisor_telefono'),
            'email': fiscal.get('email', ''),
        }],
    }


# ─── data: el documento concreto ─────────────────────────────────────────────

def _cliente(documento) -> dict:
    """
    Bloque del receptor.

    La naturaleza (contribuyente o no) ya la decidió `codigos.naturaleza_
    receptor()` al emitir, mirando si vino un RUC. Acá solo se traduce.
    """
    es_contribuyente = (
        documento.receptor_naturaleza == codigos.RECEPTOR_CONTRIBUYENTE)

    cliente = {
        'contribuyente': es_contribuyente,
        'razonSocial': documento.receptor_razon_social,
        'tipoOperacion': (codigos.OPERACION_B2B if es_contribuyente
                          else codigos.OPERACION_B2C),
        'direccion': documento.receptor_direccion or '',
        'pais': 'PRY',
        'paisDescripcion': 'Paraguay',
        'telefono': documento.receptor_telefono or '',
        'email': documento.receptor_email or '',
    }

    if es_contribuyente:
        cliente['ruc'] = documento.receptor_ruc
        # El SIFEN pide si el receptor es persona física o jurídica. El
        # sistema no lo captura: se asume jurídica, que es lo habitual en
        # quien pide factura con RUC. Si algún día se registra de verdad,
        # sale de acá.
        cliente['tipoContribuyente'] = codigos.RECEPTOR_PERSONA_JURIDICA
    else:
        # No es contribuyente: el SIFEN exige tipo y número de documento.
        #
        # Ojo que "no contribuyente" no quiere decir "sin identificar". La
        # pantalla de caja pide "RUC/CI", así que acá puede venir una cédula
        # perfectamente válida — y en ese caso hay que declararla como
        # cédula, no como RUC. Solo cuando no vino nada va "innominado"
        # (código 5), que es el caso de la venta de mostrador anónima.
        identificacion = (documento.receptor_ruc or '').strip()
        if identificacion:
            cliente['documentoTipo'] = codigos.IDENTIDAD_CEDULA_PY
            cliente['documentoNumero'] = identificacion
        else:
            _exigir_receptor_identificado(documento)
            cliente['documentoTipo'] = codigos.IDENTIDAD_INNOMINADO
            cliente['documentoNumero'] = '0'

    # La dirección del receptor obliga al domicilio desglosado. Si no se
    # tiene, es mejor no mandar dirección que mandarla sin departamento:
    # el SIFEN valida el grupo completo.
    #
    # Salvo en la nota de remisión, donde la dirección del receptor es
    # OBLIGATORIA — y tiene sentido: una remisión declara adónde va la
    # mercadería, así que sin dirección el documento no dice nada. Cuando el
    # receptor no tiene una cargada se usa la de entrega del traslado, que es
    # el dato correcto para este documento.
    traslado = (getattr(documento.pago.pedido, 'datos_traslado', None)
                if documento.tipo_documento == codigos.TIPO_DE_NOTA_REMISION
                else None)

    # Ojo con el orden de los errores: si NO hay datos de traslado, el mensaje
    # útil es ese —"cargá el traslado"—, no "falta la dirección del receptor",
    # que es una consecuencia. `_cliente()` corre antes que `_bloque_remision()`,
    # así que acá se deja pasar el caso sin traslado para que el error salga
    # del lugar que sabe explicarlo.
    if traslado is not None:
        if not cliente['direccion']:
            cliente['direccion'] = traslado.direccion_entrega or ''
        if not cliente['direccion']:
            raise DatosIncompletos(
                f'La nota de remisión {documento.numero_completo} no tiene '
                f'dirección del receptor ni dirección de entrega cargada. El '
                f'SIFEN la exige para este tipo de documento: una remisión '
                f'tiene que decir adónde va la mercadería.')
        # Declarar la dirección activa el grupo del domicilio completo: el
        # SIFEN no acepta una calle sin ciudad, distrito y departamento. Se
        # toman los del destino del traslado y, si no están cargados, los del
        # local — que es un dato real y validable, no un relleno.
        cliente.update(_domicilio_receptor_remision(traslado))
    elif not cliente['direccion']:
        cliente.pop('direccion')

    return cliente


# Largo máximo de los campos de dirección del grupo de transporte. Lo valida
# xmlgen (4 a 60) y lo hereda del manual. La dirección del local supera los 60
# caracteres, así que recortar no es opcional: sin esto el documento vuelve
# rechazado por un campo que además es accesorio.
LARGO_MAX_DIRECCION_TRANSPORTE = 60


def _direccion_transporte(texto: str) -> str:
    return str(texto or '').strip()[:LARGO_MAX_DIRECCION_TRANSPORTE]


def _domicilio_receptor_remision(traslado) -> dict:
    """
    Domicilio desglosado del receptor, solo para la nota de remisión.

    El SIFEN pide el grupo entero o nada: declarar la calle obliga a declarar
    número de casa, ciudad, distrito y departamento. Se prefieren los datos
    del destino real del traslado; si no están, los del local.
    """
    fiscal = _fiscal()
    lee = lambda campo, alterno: getattr(traslado, campo, None) or fiscal.get(alterno)
    return {
        'numeroCasa': (getattr(traslado, 'entrega_numero_casa', '') or '0'),
        'departamento': lee('entrega_departamento', 'departamento'),
        'departamentoDescripcion': (
            getattr(traslado, 'entrega_departamento_desc', '')
            or fiscal.get('departamento_desc', '')),
        'distrito': lee('entrega_distrito', 'distrito'),
        'distritoDescripcion': (getattr(traslado, 'entrega_distrito_desc', '')
                                or fiscal.get('distrito_desc', '')),
        'ciudad': lee('entrega_ciudad', 'ciudad'),
        'ciudadDescripcion': (getattr(traslado, 'entrega_ciudad_desc', '')
                              or fiscal.get('ciudad_desc', '')),
    }


def _exigir_receptor_identificado(documento):
    """
    Cuándo el SIFEN NO acepta un receptor sin identificar.

    Son dos reglas de las Notas Técnicas, y la primera pega de lleno en este
    rubro:

    · **Por monto** (NT 021, corregida por la NT 024): el receptor no puede
      ser innominado cuando el total llega a 7.000.000 Gs. La NT 021 lo había
      puesto en 35 millones en enero de 2024; la NT 024 lo bajó a 7 millones
      un año después. Siete millones son los pisos de un baño — o sea que acá
      es el caso normal, no el borde.

    · **Por tipo de documento** (NT 023): una nota de crédito, de débito o de
      remisión nunca puede ir a un receptor innominado, sin importar el monto.
      Tiene sentido: corrigen o trasladan algo que ya se le entregó a alguien
      concreto.

    Se valida acá y no al cobrar porque es el único lugar que conoce las dos
    cosas a la vez, el tipo de documento y el total.
    """
    if documento.tipo_documento in codigos.TIPOS_QUE_EXIGEN_RECEPTOR_IDENTIFICADO:
        raise DatosIncompletos(
            f'El documento {documento.numero_completo} es una '
            f'{codigos.DESCRIPCION_TIPO_DE.get(documento.tipo_documento, "nota")} '
            f'y no tiene identificado al receptor. El SIFEN no lo acepta '
            f'(NT 023): hay que cargar el RUC o la cédula del cliente.')

    if _dec(documento.total) >= codigos.MONTO_EXIGE_IDENTIFICAR_RECEPTOR:
        raise DatosIncompletos(
            f'La venta es de {documento.total} Gs y no identifica al cliente. '
            f'Desde la NT 024 el SIFEN exige RUC o cédula del comprador en '
            f'toda operación de '
            f'{codigos.MONTO_EXIGE_IDENTIFICAR_RECEPTOR:,} Gs o más.'
            .replace(',', '.'))


def _items(documento) -> list:
    """
    Los ítems, con el descuento de caja prorrateado.

    El problema que resuelve: en caja se puede cobrar menos que la suma de
    los ítems (descuento porcentual o precio negociado). El SIFEN no acepta
    que los ítems sumen una cosa y el total declare otra, así que la
    diferencia hay que repartirla.

    Se reparte como **descuento por ítem** (`dDescItem` del manual) y no
    inventando precios unitarios: el precio que se declara es el mismo que
    vio el cliente en el comprobante, y el descuento queda explícito. Si se
    tocara el precio unitario, el papel y el XML dirían cosas distintas.

    El último ítem absorbe el residuo del redondeo, igual que
    `emisor.calcular_totales_iva()` absorbe el suyo en la base gravada más
    grande. Sin eso el total del XML puede quedar 1 Gs corrido y el SIFEN
    rechaza el documento entero por un peso.
    """
    # La autofactura no sale de un pedido: lo que se le compró a un particular
    # no está en el catálogo. Sus ítems se escriben a mano y viven en el
    # propio documento.
    if documento.tipo_documento == codigos.TIPO_DE_AUTOFACTURA:
        return _items_autofactura(documento)

    # La nota de débito tampoco. Su monto es un importe NUEVO —un interés, un
    # flete que no se facturó— y no una redistribución del pedido. Prorratear
    # los ítems originales contra un total mayor da descuento negativo, que es
    # exactamente lo que pasaba antes de esta rama.
    if documento.tipo_documento == codigos.TIPO_DE_NOTA_DEBITO:
        return _items_nota_debito(documento)

    pedido = documento.pago.pedido
    items = list(pedido.items.select_related('variante__producto').all())
    if not items:
        raise DatosIncompletos(
            f'El pedido {pedido.pk} no tiene ítems; no se puede armar el DE.')

    total_cobrado = _dec(documento.total)
    suma_items = sum((_dec(i.subtotal) for i in items), Decimal('0'))
    factor = (total_cobrado / suma_items) if suma_items > 0 else Decimal('1')

    salida = []
    acumulado = Decimal('0')
    for posicion, item in enumerate(items):
        producto = item.variante.producto
        cantidad = _dec(item.cantidad)
        precio_unitario = _gs(item.precio_unitario)

        # Lo que este ítem tiene que aportar al total, ya prorrateado.
        objetivo = _gs(_dec(item.subtotal) * factor)
        if posicion == len(items) - 1:
            # El último cierra la cuenta exacta.
            objetivo = total_cobrado - acumulado
        acumulado += objetivo

        bruto = precio_unitario * cantidad
        descuento_total = bruto - objetivo
        # dDescItem es por unidad, no por línea.
        descuento_unitario = (descuento_total / cantidad) if cantidad else Decimal('0')

        if descuento_unitario < 0:
            # Cobrar MÁS que la suma de los ítems no es un descuento, y el
            # SIFEN no tiene dónde declararlo. Pero una diferencia mínima es
            # esperable y legítima: caja redondea el total a guaraníes enteros
            # con ROUND_HALF_UP (apps/caja/views.py), y como acá se vende por
            # m² el total del pedido casi siempre tiene decimales. La mitad de
            # las veces ese redondeo queda por ENCIMA de la suma de los ítems.
            #
            # Hasta un guaraní se absorbe poniendo el descuento en cero: la
            # diferencia queda por debajo de la unidad mínima de la moneda y
            # el cuadre la tolera. Más que eso ya no es redondeo, es un dato
            # incoherente, y hay que verlo.
            if descuento_total > -TOLERANCIA_CUADRE:
                descuento_unitario = Decimal('0')
            else:
                raise DatosIncompletos(
                    f'El ítem {item.pk} del pedido {pedido.pk} quedaría con '
                    f'descuento negativo: se cobró {descuento_total * -1} Gs '
                    f'más de lo que suma el ítem. Revisar el monto cobrado '
                    f'contra el detalle del pedido.')

        tasa = getattr(producto, 'tasa_iva', codigos.TASA_10)
        if tasa not in codigos.TASAS_VALIDAS:
            tasa = codigos.TASA_10

        salida.append({
            # NT 009: el código interno (E701) admite hasta 50 caracteres y
            # el SKU del catálogo llega a 100.
            'codigo': (item.variante.sku
                       or f'ITEM-{item.pk}')[:codigos.LARGO_MAX_CODIGO_ITEM],
            'descripcion': _descripcion_item(item),
            'unidadMedida': UNIDAD_MEDIDA_SIFEN.get(
                producto.unidad_venta, UNIDAD_MEDIDA_POR_DEFECTO),
            'cantidad': float(cantidad),
            'precioUnitario': float(precio_unitario),
            'descuento': float(descuento_unitario.quantize(
                PRECISION_DESCUENTO, rounding=ROUND_HALF_UP)),
            'ivaTipo': AFECTACION_POR_TASA.get(tasa, codigos.IVA_GRAVADO),
            'iva': tasa,
            # Proporción de la base gravada. 100 = el ítem está gravado por
            # completo, que es el caso salvo "gravado parcial".
            'ivaProporcion': 100,
        })

    _verificar_cuadre(salida, total_cobrado, pedido)
    return salida


def _verificar_cuadre(items, total_cobrado, pedido):
    """
    Los ítems tienen que reconstruir el total cobrado.

    El SIFEN recalcula los totales a partir de los ítems y los compara con lo
    declarado. Si no cierran, rechaza el documento entero. Más vale enterarse
    acá —donde el error dice qué pedido es— que en la respuesta del SIFEN.
    """
    reconstruido = sum(
        ((_dec(i['precioUnitario']) - _dec(i['descuento'])) * _dec(i['cantidad'])
         for i in items), Decimal('0'))
    diferencia = abs(reconstruido - total_cobrado)
    if diferencia >= TOLERANCIA_CUADRE:
        raise DatosIncompletos(
            f'Los ítems del pedido {pedido.pk} reconstruyen {reconstruido} '
            f'pero se cobraron {total_cobrado} (diferencia {diferencia}). '
            f'El SIFEN rechazaría el documento: revisar cantidades y precios.')


def _descripcion_item(item) -> str:
    """
    Descripción del ítem tal como va al XML.

    Se arma con producto + variante porque el SIFEN recibe un solo campo de
    texto y "Porcelanato Bianco" sin el color no identifica lo que se vendió.
    """
    variante = item.variante
    partes = [variante.producto.nombre]
    detalle = str(variante).replace(variante.producto.nombre, '').strip(' -—')
    if detalle:
        partes.append(detalle)
    # NT 009 amplió E708 a 2000 caracteres. Recortar el nombre del producto en
    # un comprobante legal es peor que mandarlo largo, así que se usa el tope
    # real del campo y no uno inventado.
    return ' - '.join(partes)[:codigos.LARGO_MAX_DESCRIPCION_ITEM]


def _condicion(documento) -> dict:
    """
    Condición de la operación y forma de pago.

    Hoy el sistema cobra siempre al contado y con un solo medio de pago por
    cobro, así que `entregas` tiene un único elemento. La estructura soporta
    varios porque el SIFEN lo permite; si algún día se cobra mitad efectivo
    y mitad tarjeta, se suma acá.
    """
    if documento.condicion_venta == codigos.CONDICION_CREDITO:
        # El crédito exige plazo o cuotas; el sistema no los registra.
        raise DatosIncompletos(
            'La venta está marcada a crédito, pero el sistema no registra '
            'plazo ni cuotas, que el SIFEN exige para una operación a '
            'crédito. Hay que capturarlos antes de poder facturarla.')

    entrega = {
        'tipo': documento.medio_pago,
        'monto': str(_gs(documento.total)),
        'moneda': MONEDA,
        'cambio': 0,
    }

    if documento.medio_pago in codigos.MEDIOS_CON_TARJETA:
        entrega['infoTarjeta'] = _info_tarjeta(documento)

    if documento.medio_pago in codigos.MEDIOS_CON_CHEQUE:
        entrega['infoCheque'] = _info_cheque(documento)

    return {'tipo': codigos.CONDICION_CONTADO, 'entregas': [entrega]}


def _info_tarjeta(documento) -> dict:
    """
    Grupo E620 (`gPagTarCD`), obligatorio en todo cobro con tarjeta.

    El manual es explícito: el grupo "se activa si E606 = 3 o 4". No es
    opcional, y de sus campos la denominación de la tarjeta y la forma de
    procesamiento tampoco lo son.

    Los datos los captura caja al confirmar el cobro, del voucher de la
    terminal POS (ver apps/caja/pos.py). Si faltan no se puede armar el
    documento — y hay que decirlo claro, porque para cuando esto corre el
    cliente ya se fue y nadie se acuerda con qué tarjeta pagó.
    """
    datos = getattr(documento.pago, 'datos_tarjeta', None)
    if datos is None:
        raise DatosIncompletos(
            f'El cobro {documento.pago.numero_ticket} fue con tarjeta pero no '
            f'tiene los datos que el SIFEN exige (grupo E620): al menos con '
            f'qué tarjeta se pagó. Se cargan en la pantalla de caja, del '
            f'voucher de la terminal.')

    info = {
        'tipo': datos.denominacion,
        'tipoDescripcion': datos.descripcion_sifen,
        'medioPago': datos.forma_procesamiento,
    }
    # Los opcionales solo se mandan si están: un campo vacío es peor que
    # ausente, porque el SIFEN valida longitudes mínimas (por ejemplo el
    # titular es de 4 a 30 caracteres).
    if datos.codigo_autorizacion:
        info['codigoAutorizacion'] = datos.codigo_autorizacion
    if len(datos.titular) >= 4:
        info['titular'] = datos.titular
    if datos.procesadora_ruc:
        info['ruc'] = datos.procesadora_ruc
    if len(datos.procesadora_razon_social) >= 4:
        info['razonSocial'] = datos.procesadora_razon_social
    return info


def _info_cheque(documento) -> dict:
    """
    Grupo E630 (`gPagCheq`), obligatorio en todo cobro con cheque.

    El manual lo activa "si E606 = 2" y sus dos campos son de ocurrencia
    1-1: el número (con ceros a la izquierda hasta ocho) y el banco emisor.

    Los datos los captura caja al cobrar, del cheque mismo — y ahí se exigen
    siempre, esté el SIFEN prendido o no, porque sin ellos el local tampoco
    puede seguirle el rastro al papel (ver apps/caja/cheque.py).
    """
    datos = getattr(documento.pago, 'datos_cheque', None)
    if datos is None:
        raise DatosIncompletos(
            f'El cobro {documento.pago.numero_ticket} fue con cheque pero no '
            f'tiene los datos que el SIFEN exige (grupo E630): el número del '
            f'cheque y el banco emisor.')

    return {
        'numeroCheque': codigos.numero_cheque_sifen(datos.numero),
        'banco': datos.banco,
    }


def _bloque_por_tipo(documento) -> dict:
    """
    La parte del `data` que depende del tipo de documento.

    Cada tipo del SIFEN trae su propio grupo obligatorio. Los tres que el
    sistema puede armar hoy salen completos; los dos que necesitan datos que
    el sistema no captura lanzan un error que dice exactamente qué falta, en
    vez de mandar un documento incompleto.
    """
    tipo = documento.tipo_documento

    if tipo == codigos.TIPO_DE_FACTURA:
        return {'factura': {'presencia': PRESENCIA_PRESENCIAL}}

    if tipo in (codigos.TIPO_DE_NOTA_CREDITO, codigos.TIPO_DE_NOTA_DEBITO):
        if not documento.documento_asociado_cdc:
            raise DatosIncompletos(
                'Una nota de crédito o débito tiene que referenciar el CDC '
                'del documento que corrige (campo documento_asociado_cdc).')
        return {
            'notaCreditoDebito': {'motivo': documento.motivo_nota},
            'documentoAsociado': {
                'formato': codigos.DOCUMENTO_ASOCIADO_ELECTRONICO,
                'cdc': documento.documento_asociado_cdc,
            },
        }

    if tipo == codigos.TIPO_DE_AUTOFACTURA:
        return _bloque_autofactura(documento)

    if tipo == codigos.TIPO_DE_NOTA_REMISION:
        return _bloque_remision(documento)

    raise DatosIncompletos(f'Tipo de documento electrónico desconocido: {tipo}')


def _items_nota_debito(documento) -> list:
    """
    El único renglón de una nota de débito.

    Un débito cobra **una cosa**: el interés, el flete, el ajuste. No es una
    redistribución de la venta original, así que no tiene sentido repetir sus
    ítems — y repetirlos rompía, porque el monto del débito es mayor que la
    suma del pedido y el prorrateo daba descuento negativo.

    La descripción sale del motivo declarado, que es lo que el SIFEN ya tiene
    en el grupo E4: el papel dice lo mismo que el XML.
    """
    total = _dec(documento.total)
    if total <= 0:
        raise DatosIncompletos(
            f'La nota de débito {documento.numero_completo} no tiene monto.')

    if _dec(documento.iva_10) > 0:
        tasa = codigos.TASA_10
    elif _dec(documento.iva_5) > 0:
        tasa = codigos.TASA_5
    else:
        tasa = codigos.TASA_0

    descripcion = codigos.MOTIVOS_NOTA.get(
        documento.motivo_nota, 'Ajuste sobre documento anterior')

    return [{
        'codigo': 'ND-001',
        'descripcion': descripcion[:codigos.LARGO_MAX_DESCRIPCION_ITEM],
        'unidadMedida': UNIDAD_MEDIDA_POR_DEFECTO,
        'cantidad': 1.0,
        'precioUnitario': float(total),
        'descuento': 0,
        'ivaTipo': AFECTACION_POR_TASA.get(tasa, codigos.IVA_GRAVADO),
        'iva': tasa,
        'ivaProporcion': 100,
    }]


def _bloque_autofactura(documento) -> dict:
    """
    Grupo E7 (`gCamAE`): quién vendió y dónde ocurrió la operación.

    La autofactura documenta una **compra** a alguien que no puede emitir
    factura, así que lo que describe no es un cliente sino una contraparte.
    Los nombres de las claves son los de `xmlgen`, verificados contra
    `jsonDteMain.service.js`.

    El SIFEN pide el lugar de la transacción **aparte** del domicilio del
    vendedor: no tienen por qué coincidir.
    """
    datos = getattr(documento, 'datos_autofactura', None)
    if datos is None:
        raise DatosIncompletos(
            f'La autofactura {documento.numero_completo} no tiene cargados '
            f'los datos del vendedor no contribuyente ni el lugar de la '
            f'transacción. Sin eso no se puede armar el documento.')

    return {
        'autoFactura': {
            'tipoVendedor': datos.naturaleza_vendedor,
            'documentoTipo': datos.tipo_documento_vendedor,
            'documentoNumero': datos.numero_documento_vendedor,
            'nombre': datos.nombre_vendedor,
            'direccion': datos.direccion_vendedor,
            'numeroCasa': datos.numero_casa_vendedor or '0',
            'departamento': datos.departamento_vendedor,
            'departamentoDescripcion': datos.departamento_vendedor_desc,
            'distrito': datos.distrito_vendedor,
            'distritoDescripcion': datos.distrito_vendedor_desc,
            'ciudad': datos.ciudad_vendedor,
            'ciudadDescripcion': datos.ciudad_vendedor_desc,
            'ubicacion': {
                'lugar': datos.lugar_transaccion,
                'departamento': datos.departamento_transaccion,
                'departamentoDescripcion': datos.departamento_transaccion_desc,
                'distrito': datos.distrito_transaccion,
                'distritoDescripcion': datos.distrito_transaccion_desc,
                'ciudad': datos.ciudad_transaccion,
                'ciudadDescripcion': datos.ciudad_transaccion_desc,
            },
        },
    }


def _items_autofactura(documento) -> list:
    """
    Los ítems de una autofactura, que se escriben a mano.

    No salen del pedido como los de los otros documentos: lo que se le compró
    a un particular no está en el catálogo ni pasó por el stock. Por eso no
    hay prorrateo de descuento acá — no hubo negociación sobre un precio de
    lista, el precio es el que se pactó.
    """
    items = list(documento.items_autofactura.all())
    if not items:
        raise DatosIncompletos(
            f'La autofactura {documento.numero_completo} no tiene ítems: hay '
            f'que cargar qué se compró.')

    salida = []
    for posicion, item in enumerate(items, start=1):
        salida.append({
            'codigo': f'AF{posicion:04d}',
            'descripcion': item.descripcion[:codigos.LARGO_MAX_DESCRIPCION_ITEM],
            'unidadMedida': UNIDAD_MEDIDA_POR_DEFECTO,
            'cantidad': float(item.cantidad),
            'precioUnitario': float(_gs(item.precio_unitario)),
            'descuento': 0,
            'ivaTipo': AFECTACION_POR_TASA.get(item.tasa_iva,
                                               codigos.IVA_EXENTO),
            'iva': item.tasa_iva,
            'ivaProporcion': 100,
        })
    return salida


def _bloque_remision(documento) -> dict:
    """
    Grupos E6 y E10: motivo del traslado y transporte.

    Los datos salen de `DatosTraslado`, que cuelga del pedido y no del cobro
    — una remisión describe un movimiento de mercadería, no una venta. Por
    eso puede faltar: se carga al preparar la entrega, no al cobrar.
    """
    traslado = getattr(documento.pago.pedido, 'datos_traslado', None)
    if traslado is None:
        raise DatosIncompletos(
            f'El pedido {documento.pago.pedido_id} no tiene datos de '
            f'traslado cargados (motivo, vehículo, dirección de entrega). '
            f'Sin eso no se puede emitir la nota de remisión.')

    if not traslado.kilometros:
        raise DatosIncompletos(
            f'El traslado del pedido {documento.pago.pedido_id} no tiene los '
            f'kilómetros estimados de recorrido. La NT 010 los volvió '
            f'obligatorios en la nota de remisión (campo E505).')

    remision = {
        'motivo': traslado.motivo,
        'tipoResponsable': traslado.responsable,
        'kms': traslado.kilometros,
    }

    # La factura que respalda el traslado, cuando existe. El SIFEN la pide
    # para el motivo "traslado por venta".
    factura = documento.pago.documento_electronico
    if factura is not None:
        remision['fechaFactura'] = factura.fecha_emision.date().isoformat()

    vehiculo = {
        'tipo': traslado.vehiculo_tipo or 'Camion',
        'marca': traslado.vehiculo_marca or 'S/D',
        'tipoIdentificacion': traslado.tipo_identificacion_vehiculo,
    }
    if traslado.vehiculo_matricula:
        vehiculo['numeroMatricula'] = traslado.vehiculo_matricula
    else:
        vehiculo['numeroVehiculo'] = traslado.vehiculo_numero

    # ⚠️ Los nombres de las dos fechas son `inicioEstimadoTranslado` y
    # `finEstimadoTranslado` — con "Transl", no "Trasl". Parece un error de
    # tipeo de la librería y lo es, pero es el nombre real de la clave
    # (verificado en jsonDeMain.service.js y jsonDeMainValidate.service.js).
    # Escribirlo "bien" hace que xmlgen no vea el campo y lo rechace por
    # obligatorio, que es exactamente lo que pasaba.
    #
    # Las DOS son obligatorias. El sistema solo captura la de inicio, porque
    # en la práctica la entrega es el mismo día; cuando no hay fecha de fin se
    # declara la de inicio antes que omitir el campo y que el documento vuelva
    # rechazado.
    fin = traslado.fecha_fin_traslado or traslado.fecha_inicio_traslado
    transporte = {
        'tipo': traslado.tipo_transporte,
        'modalidad': traslado.modalidad,
        'responsableFlete': traslado.responsable_flete,
        'inicioEstimadoTranslado': traslado.fecha_inicio_traslado.isoformat(),
        'finEstimadoTranslado': fin.isoformat(),
        'vehiculos': [vehiculo],
        'salida': _domicilio_salida(traslado),
        'entrega': _domicilio_entrega(traslado),
    }

    # NT 007: en la nota de remisión el campo de información del Fisco
    # (B006 dInfoFisc) es OBLIGATORIO y tiene que llevar la leyenda del
    # art. 3 inc. 7 de la RG 41/2014. Es un texto legal: no se inventa acá
    # ni se deduce — lo confirma la contadora y se carga en el .env.
    # En xmlgen ese campo se llama 'descripcion' (verificado en
    # jsonDeMain.service.ts, no deducido del README).
    leyenda = str(_fiscal().get('leyenda_remision') or '').strip()
    if not leyenda:
        raise DatosIncompletos(
            'La nota de remisión necesita la leyenda del art. 3 inc. 7 de la '
            'RG 41/2014 en el campo de información al Fisco, que la NT 007 '
            'volvió obligatoria. Es un texto legal: hay que pedírselo a la '
            'contadora y cargarlo en FISCAL_LEYENDA_REMISION del .env.')

    if traslado.transportista_nombre:
        transporte['transportista'] = _transportista(traslado, documento)

    return {'remision': remision, 'transporte': transporte,
            'descripcion': leyenda}


def _transportista(traslado, documento) -> dict:
    """
    Grupo E10.4: la empresa transportista y su chofer.

    El SIFEN no acepta un transportista a medias. Si se declara uno, exige
    identificarlo (tipo y número de documento, o RUC), su dirección, y —si
    hay chofer— el documento y la dirección del chofer también. Son cinco
    campos que la primera versión no mandaba, y cada uno de ellos solo hacía
    falta para la remisión, que es el único documento que llegó a armarse sin
    haberse probado nunca contra la librería.

    Cuando el que traslada es el propio negocio —el caso normal acá, que
    entrega con su camión— la dirección del transportista es la del local y
    el documento es el RUC del emisor. Se completa con eso antes que dejar el
    grupo incompleto.
    """
    fiscal = _fiscal()
    propio = codigos.es_ruc(traslado.transportista_ruc)

    transportista = {
        'nombre': traslado.transportista_nombre,
        'contribuyente': bool(propio),
        'direccion': _direccion_transporte(
            traslado.transportista_direccion or fiscal.get('direccion', '')),
    }

    if propio:
        transportista['ruc'] = traslado.transportista_ruc
    else:
        # El SIFEN pide tipo Y número aunque no sea contribuyente. Si no se
        # cargó la cédula del transportista, se declara el documento del
        # emisor: el traslado lo hace el negocio con su propio vehículo, que
        # es el caso habitual del rubro.
        transportista['documentoTipo'] = codigos.IDENTIDAD_CEDULA_PY
        transportista['documentoNumero'] = (
            traslado.transportista_documento
            or str(documento.emisor_ruc or fiscal.get('ruc', '')).split('-')[0])

    if traslado.conductor_nombre:
        transportista['chofer'] = {
            'nombre': traslado.conductor_nombre,
            'documento': traslado.conductor_documento,
            # xmlgen los valida por separado del 'documento' de arriba.
            'documentoNumero': traslado.conductor_documento,
            'direccion': _direccion_transporte(
                traslado.conductor_direccion
                or traslado.transportista_direccion
                or fiscal.get('direccion', '')),
        }

    return transportista


def _domicilio_salida(traslado) -> dict:
    """
    Local de salida de la mercadería (grupo E10.1).

    Casi siempre es el propio negocio, así que se cae en el domicilio fiscal.
    `DatosTraslado` tiene campos propios para el caso en que salga de otro
    lado —un depósito, la casa de un proveedor—, y ahí ganan esos.

    El SIFEN exige ciudad y número de casa; la dirección sola no le alcanza.
    """
    fiscal = _fiscal()
    return {
        'direccion': traslado.direccion_salida or fiscal.get('direccion', ''),
        'numeroCasa': (traslado.salida_numero_casa
                       or str(fiscal.get('numero_casa') or '0')),
        'ciudad': traslado.salida_ciudad or fiscal.get('ciudad'),
        'ciudadDescripcion': (traslado.salida_ciudad_desc
                              or fiscal.get('ciudad_desc', '')),
        'distrito': fiscal.get('distrito'),
        'distritoDescripcion': fiscal.get('distrito_desc', ''),
        'departamento': fiscal.get('departamento'),
        'departamentoDescripcion': fiscal.get('departamento_desc', ''),
    }


def _domicilio_entrega(traslado) -> dict:
    """
    Dirección de llegada, desglosada como la pide el SIFEN.

    Si no se cargaron los códigos geográficos se cae en los del local: es
    preferible declarar el domicilio fiscal del negocio, que es un dato real
    y validable, antes que mandar el grupo incompleto y que lo rechacen.
    """
    fiscal = _fiscal()
    return {
        'direccion': traslado.direccion_entrega,
        'numeroCasa': traslado.entrega_numero_casa or '0',
        'departamento': traslado.entrega_departamento or fiscal.get('departamento'),
        'departamentoDescripcion': (traslado.entrega_departamento_desc
                                    or fiscal.get('departamento_desc', '')),
        'distrito': traslado.entrega_distrito or fiscal.get('distrito'),
        'distritoDescripcion': (traslado.entrega_distrito_desc
                                or fiscal.get('distrito_desc', '')),
        'ciudad': traslado.entrega_ciudad or fiscal.get('ciudad'),
        'ciudadDescripcion': (traslado.entrega_ciudad_desc
                              or fiscal.get('ciudad_desc', '')),
    }


def construir_data(documento) -> dict:
    """
    El `data` completo de un DocumentoElectronico.

    Devuelve el dict listo para mandarle al sidecar. No transmite nada ni
    toca la base.
    """
    data = {
        'tipoDocumento': documento.tipo_documento,
        'establecimiento': documento.establecimiento,
        'punto': documento.punto_expedicion,
        'numero': f'{documento.numero:07d}',
        'codigoSeguridadAleatorio': documento.codigo_seguridad,
        # xmlgen espera la fecha sin zona horaria. Se manda la hora local,
        # que es la que figura en el comprobante que recibió el cliente.
        'fecha': _fecha_local(documento.fecha_emision),
        'tipoEmision': codigos.EMISION_NORMAL,
        'tipoImpuesto': codigos.IMPUESTO_IVA,
        'moneda': MONEDA,
        'cliente': _cliente(documento),
        'condicion': _condicion(documento),
        'items': _items(documento),
    }

    # NT 006: el tipo de transacción NO se informa cuando el documento no es
    # una factura o una autofactura. Mandarlo en una nota de crédito, débito
    # o remisión es rechazo (validación D011a, código 1216). La primera
    # versión lo mandaba siempre.
    if documento.tipo_documento in codigos.TIPOS_CON_TIPO_TRANSACCION:
        data['tipoTransaccion'] = codigos.TRANSACCION_VENTA_MERCADERIA

    data.update(_bloque_por_tipo(documento))
    return data


def _fecha_local(momento) -> str:
    """Fecha y hora del DE en formato ISO sin zona, como la espera xmlgen."""
    from django.utils import timezone
    local = timezone.localtime(momento) if timezone.is_aware(momento) else momento
    return local.strftime('%Y-%m-%dT%H:%M:%S')


def construir(documento) -> dict:
    """
    Atajo: devuelve {'params': ..., 'data': ...} para mandarle al sidecar.

    Es el único punto por donde el payload sale hacia el sidecar, así que es
    acá donde se aplica la marca del ambiente de pruebas: no hay forma de
    armar un documento y saltearla por accidente.
    """
    params = construir_params(documento)
    data = construir_data(documento)
    if en_ambiente_de_pruebas():
        _marcar_como_prueba(params, data)
    return {'params': params, 'data': data}
