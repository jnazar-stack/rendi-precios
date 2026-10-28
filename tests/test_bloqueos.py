import unittest

from actualizar import es_bloqueo


class TestBloqueos(unittest.TestCase):
    def test_denegaciones_detienen_cadena(self):
        for estado in ("bloqueado", "http 401", "http 403", "http 429"):
            with self.subTest(estado=estado):
                self.assertTrue(es_bloqueo(estado))

    def test_resultados_no_bloquean(self):
        for estado in ("ok", "sin resultados", "sin datos", "http 500", "http 0"):
            with self.subTest(estado=estado):
                self.assertFalse(es_bloqueo(estado))


if __name__ == "__main__":
    unittest.main()
