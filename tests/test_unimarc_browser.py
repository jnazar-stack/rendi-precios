import unittest
from unittest.mock import Mock

from unimarc_browser import UnimarcBrowser
from actualizar import CAT, elegir


class TestUnimarc(unittest.TestCase):
    def test_lee_precio_normal_de_tarjeta(self):
        reader = UnimarcBrowser()
        page = Mock()
        page.goto.return_value.status = 200
        page.evaluate.return_value = [
            {"name": "Leche descremada colun 1 l", "brand": "Colun",
             "price": 1090, "href": "/product/leche-descremada-colun-1-l",
             "img": None, "stock": True, "raw": "Leche descremada colun 1 l $1.090"}
        ]
        reader.page = page
        items, status = reader.consultar("leche descremada")
        self.assertEqual(status, "ok")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["p"], 1090)
        self.assertEqual(items[0]["u"], "https://www.unimarc.cl/product/leche-descremada-colun-1-l")
        self.assertIsNotNone(elegir(items, CAT["leche"]))

    def test_respeta_denegacion(self):
        reader = UnimarcBrowser()
        page = Mock()
        page.goto.return_value.status = 403
        reader.page = page
        items, status = reader.consultar("huevo")
        self.assertIsNone(items)
        self.assertEqual(status, "http 403")
        page.evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
