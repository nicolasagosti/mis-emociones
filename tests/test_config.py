import unittest

from emociones import sesion
from emociones.config import desde_entorno


class TestConfiguracion(unittest.TestCase):
    def test_en_tu_computadora(self):
        config = desde_entorno({"TELEGRAM_TOKEN": " 1:a ", "PUERTO": "9000", "TELEGRAM_USUARIOS": "5, 6"})
        self.assertEqual(config.token, "1:a")
        self.assertEqual(config.permitidos, {5, 6})
        self.assertEqual(config.url_publica, "http://localhost:9000")
        self.assertTrue(config.base_de_datos.endswith("datos/emociones.db"))
        self.assertTrue(config.solo_local)
        self.assertFalse(config.requiere_sesion)

    def test_en_la_red_de_casa_pide_sesion(self):
        self.assertTrue(desde_entorno({"HOST": "0.0.0.0"}).requiere_sesion)

    def test_en_vercel(self):
        config = desde_entorno({
            "VERCEL": "1", "VERCEL_ENV": "production", "VERCEL_PROJECT_PRODUCTION_URL": "mis-emociones.vercel.app",
            "DATABASE_URL": "postgresql://u:c@servidor/bd", "ZONA_HORARIA": "America/Mexico_City",
        })
        self.assertEqual(config.url_publica, "https://mis-emociones.vercel.app")
        self.assertEqual(config.base_de_datos, "postgresql://u:c@servidor/bd")
        self.assertTrue(config.produccion)
        self.assertTrue(config.requiere_sesion)
        self.assertEqual(str(config.zona), "America/Mexico_City")

    def test_en_vercel_sin_base_de_datos_no_usa_sqlite(self):
        config = desde_entorno({"VERCEL": "1", "VERCEL_ENV": "preview"})
        self.assertIsNone(config.base_de_datos)
        self.assertFalse(config.produccion)

    def test_zona_horaria_invalida(self):
        with self.assertLogs("emociones", "WARNING"):
            self.assertIsNone(desde_entorno({"ZONA_HORARIA": "Marte/Olympus"}).zona)

    def test_numeros_invalidos(self):
        with self.assertRaises(ValueError):
            desde_entorno({"TELEGRAM_USUARIOS": "yo"})


class TestSesion(unittest.TestCase):
    def test_firmar_y_verificar(self):
        firma = sesion.firmar("tok", "sesion", 42, 60, ahora=1000)
        self.assertEqual(sesion.verificar("tok", "sesion", firma, ahora=1030), 42)
        self.assertIsNone(sesion.verificar("tok", "sesion", firma, ahora=1061))   # venció
        self.assertIsNone(sesion.verificar("otro", "sesion", firma, ahora=1030))  # otro token
        self.assertIsNone(sesion.verificar("tok", "entrar", firma, ahora=1030))   # otro uso

    def test_firmas_alteradas(self):
        usuario, vence, firma = sesion.firmar("tok", "sesion", 42, 60, ahora=1000).split(".")
        for alterada in (f"43.{vence}.{firma}", f"{usuario}.99999.{firma}", f"{usuario}.{vence}.x", "", "a.b", None):
            self.assertIsNone(sesion.verificar("tok", "sesion", alterada, ahora=1000), alterada)

    def test_secreto_del_webhook(self):
        self.assertEqual(sesion.secreto_webhook("a"), sesion.secreto_webhook("a"))
        self.assertNotEqual(sesion.secreto_webhook("a"), sesion.secreto_webhook("b"))
        self.assertRegex(sesion.secreto_webhook("a"), r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
