import unittest
from unittest.mock import patch
import actualizar

def sample(*names_prices):
    products = []
    for name, price in names_prices:
        products.append({"@type":"ListItem","item":{"@type":"Product",
            "name":name,"image":"https://example.com/p.jpg",
            "offers":{"@type":"Offer","price":str(price),"availability":"https://schema.org/InStock"}}})
    return '<script type="application/ld+json">' + __import__("json").dumps({
       "@type":"ItemList","itemListElement":products
    }) + '</script>'

class TestLiderCategoria(unittest.TestCase):
    def test_leche(self):
        body=sample(("Leche Descremada Natural 1 L Soprole",1090),("Leche Descremada Natural Caja 1 L 1 L Colun",1190))
        with patch.object(actualizar,"get",return_value=(200,body)):
            items,estado=actualizar.lider_categoria("leche")
        self.assertEqual(estado,"ok")
        p=actualizar.elegir(items,actualizar.CAT["leche"])
        self.assertIsNotNone(p)
        self.assertEqual(p["eq"]["p"],1190)

    def test_papas_con_marca(self):
        with patch.object(actualizar,"get",return_value=(200,sample(("Multi Marca Papa Malla 2 Kg",2890)))):
            items,estado=actualizar.lider_categoria("papas")
        self.assertEqual(estado,"ok")
        self.assertTrue(items[0]["n"].startswith("Papa "))
        self.assertIsNotNone(actualizar.elegir(items,actualizar.CAT["papas"]))

    def test_falsos_positivos(self):
        ejemplos = [
            ("salmon", "Rollitos De Salmón Tempura 400 g El Golfo"),
            ("quinoa", "Avena Quínoa 600 g Vivo"),
            ("oliva", "Aceite Olivado (mezcla De Oliva Extra Virgen) 500 ml"),
            ("arroz", "Arroz Grado 1 Largo 1 kg"),
            ("avena", "Avena Instantanea 500 g Oso"),
            ("pechuga", "Pollo Pechuga Entera Envasada 1 kg"),
            ("lechuga", "Lechuga Salanova Hojas Pote 150 g"),
        ]
        for pid, nombre in ejemplos:
            with self.subTest(pid=pid):
                self.assertFalse(actualizar.lider_nombre_valido(pid,nombre))
        self.assertTrue(actualizar.lider_nombre_valido("salmon","Salmón Filete Atlántico 500 g"))
        self.assertTrue(actualizar.lider_nombre_valido("quinoa","Quínoa Bolsa 400 g Banquete"))

    def test_bloqueo_y_sin_fuente(self):
        with patch.object(actualizar,"get",return_value=(403,"Access Denied")):
            items,estado=actualizar.lider_categoria("leche")
            self.assertIsNone(items)
            self.assertEqual(estado,"http 403")
        # Un producto sin categoría asignada no debe consultar la web.
        with patch.object(actualizar,"get",side_effect=AssertionError("No consultar")), \
             patch.dict(actualizar.LIDER_CATEGORIAS, {}, clear=True):
            items,estado=actualizar.lider_categoria("zanahoria")
            self.assertEqual(items,[])
            self.assertEqual(estado,"sin fuente")

if __name__=="__main__":
    unittest.main()
