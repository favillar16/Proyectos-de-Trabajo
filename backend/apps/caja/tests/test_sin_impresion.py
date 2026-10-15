"""
Ninguna corrida de tests puede imprimir en la térmica: cada ticket es papel
gastado en la PC del local (el 03/10/2026 se encolaron 26).
"""
from unittest import mock

from django.test import SimpleTestCase

from apps.caja.printer import WindowsPrinter


class SinImpresionEnTestsTest(SimpleTestCase):

    def test_la_impresora_queda_vacia(self):
        printer = WindowsPrinter()
        self.assertEqual(printer.nombre, '')
        self.assertEqual(printer.puerto, '')

    def test_imprimir_no_llega_a_la_impresora(self):
        with mock.patch.object(WindowsPrinter, '_por_cola_windows') as cola, \
             mock.patch.object(WindowsPrinter, '_por_puerto') as puerto:
            resultado = WindowsPrinter().imprimir(b'ticket')
        cola.assert_not_called()
        puerto.assert_not_called()
        self.assertEqual(resultado['metodo'], 'ninguno')
