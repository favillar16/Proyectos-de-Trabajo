"""
Recalcula `Stock.cantidad_reservada` a partir de los pedidos vivos.

Por qué existe: hasta el 23/09/2026 sacar un ítem de un pedido no liberaba su
reserva, y esa mercadería quedó trabada — en depósito, pero sin poder
venderse. El arreglo evita casos nuevos, pero no limpia los que ya quedaron en
la base del local. Caso real: el piso 71220 ajustado a 220 m² seguía
ofreciendo 133 para vender.

La reserva correcta de una variante es la suma de sus ítems en pedidos
`pendiente`, `en_preparacion` o `listo`: los ítems no se editan después de
creado el pedido, al cobrar la reserva se consume y al cancelar se libera.

Cada corrección pasa por `Stock.registrar_movimiento()`, así que queda en el
historial de la variante como una liberación (o reserva) más.

    python manage.py recalcular_reservas --dry-run
    python manage.py recalcular_reservas
    python manage.py recalcular_reservas --sku PORC-0001

Idempotente: una segunda pasada no encuentra diferencias.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from apps.inventario.models import MovimientoStock, Stock
from apps.usuarios.models import Usuario
from apps.ventas.models import ItemPedido, NotaPedido

ESTADOS_CON_RESERVA = NotaPedido.ESTADOS_CON_RESERVA


class Command(BaseCommand):
    help = 'Recalcula lo reservado de cada variante a partir de los pedidos vivos'

    def add_arguments(self, parser):
        parser.add_argument('--sku', default='', help='Solo esta variante.')
        parser.add_argument(
            '--usuario', default='',
            help='Username que queda como responsable del movimiento. '
                 'Por defecto, el primer admin activo.')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opciones):
        if opciones['usuario']:
            usuario = Usuario.objects.filter(username=opciones['usuario']).first()
            if usuario is None:
                raise CommandError(f'No existe el usuario {opciones["usuario"]!r}')
        else:
            usuario = Usuario.objects.filter(rol='admin', activo=True).order_by('id').first()
            if usuario is None:
                raise CommandError('No hay ningún admin activo; pasar --usuario.')

        dry = opciones['dry_run']

        stocks = Stock.objects.select_related('variante')
        if opciones['sku']:
            stocks = stocks.filter(variante__sku=opciones['sku'])
            if not stocks.exists():
                raise CommandError(f'No existe la variante {opciones["sku"]!r}')

        corregidas = fallidas = 0
        with transaction.atomic():
            # Primero se traban los stocks y recién después se suman los
            # pedidos: un pedido que entre durante la pasada espera acá.
            stocks = list(stocks.select_for_update().order_by('variante__sku'))
            esperado = dict(
                ItemPedido.objects
                .filter(pedido__estado__in=ESTADOS_CON_RESERVA)
                .values('variante_id')
                .annotate(total=Sum('cantidad'))
                .values_list('variante_id', 'total')
            )

            for stock in stocks:
                debe = esperado.get(stock.variante_id) or Decimal('0')
                diferencia = stock.cantidad_reservada - debe
                if diferencia == 0:
                    continue

                etiqueta = (f'{stock.variante.sku}: reservado {stock.cantidad_reservada:.2f}, '
                            f'pedidos vivos {debe:.2f}')
                if dry:
                    self.stdout.write(f'  {etiqueta} → corregiría')
                    corregidas += 1
                    continue

                tipo = (MovimientoStock.TIPO_LIBERACION if diferencia > 0
                        else MovimientoStock.TIPO_RESERVA)
                try:
                    with transaction.atomic():
                        stock.registrar_movimiento(
                            tipo=tipo, cantidad=abs(diferencia), usuario=usuario,
                            referencia_tipo='recalculo_reservas',
                            observaciones=f'Recálculo de reservas — {etiqueta}',
                        )
                except ValidationError as e:
                    # Faltan reservas y no hay stock que las cubra: eso lo
                    # tiene que mirar una persona, no un comando.
                    self.stdout.write(self.style.ERROR(
                        f'  {etiqueta} → sin corregir: {"; ".join(e.messages)}'))
                    fallidas += 1
                    continue
                self.stdout.write(f'  {etiqueta} → corregido')
                corregidas += 1

        modo = ' (dry-run, no se cambió nada)' if dry else ''
        self.stdout.write(self.style.SUCCESS(
            f'{corregidas} variante(s) con diferencias{modo}, {fallidas} sin corregir.'))
