import unittest
import actualizar


class TestCadenasActivas(unittest.TestCase):
    def test_tottus_excluido_y_indices_estables(self):
        self.assertNotIn(4, actualizar.CADENAS_ACTIVAS)
        self.assertEqual(actualizar.CADENAS_ACTIVAS, {
            0: "lider", 1: "unimarc", 2: "jumbo",
            3: "sisa", 5: "alvi"
        })


if __name__ == "__main__":
    unittest.main()
