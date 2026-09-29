import base64
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from emociones import google, sesion
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

    def test_google(self):
        config = desde_entorno({"GOOGLE_CLIENT_ID": " id ", "GOOGLE_CLIENT_SECRET": "s",
                                "GOOGLE_CORREOS": "Yo@Gmail.com, otra@gmail.com,"})
        self.assertEqual(config.google_correos, {"yo@gmail.com", "otra@gmail.com"})
        self.assertTrue(config.google_listo)
        # GOOGLE_CORREOS es opcional: cualquier cuenta de Google puede crear su diario.
        self.assertTrue(desde_entorno({"GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "s"}).google_listo)
        self.assertFalse(desde_entorno({"GOOGLE_CLIENT_ID": "id"}).google_listo)


def id_token(**datos):
    """Un id_token como el que devuelve Google (la firma no se verifica: llega directo por HTTPS)."""
    carga = {"iss": "https://accounts.google.com", "aud": "cliente", "exp": 2000,
             "email": "Yo@Gmail.com", "email_verified": True, **datos}
    return "cabecera." + base64.urlsafe_b64encode(json.dumps(carga).encode()).decode().rstrip("=") + ".firma"


class TestGoogle(unittest.TestCase):
    def test_url_de_autorizacion(self):
        url = urlsplit(google.url_autorizacion("cliente", "https://x.example/auth/google/callback", "st", "ver"))
        parametros = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.assertEqual(url.netloc, "accounts.google.com")
        self.assertEqual(parametros["client_id"], "cliente")
        self.assertEqual(parametros["redirect_uri"], "https://x.example/auth/google/callback")
        self.assertEqual(parametros["scope"], "openid email")
        self.assertEqual(parametros["state"], "st")
        self.assertEqual(parametros["code_challenge"], google.desafio("ver"))
        self.assertEqual(parametros["code_challenge_method"], "S256")

    def test_correo_verificado(self):
        self.assertEqual(google.correo_verificado({"id_token": id_token()}, "cliente", ahora=1000), "yo@gmail.com")

    def test_id_token_invalido(self):
        casos = {
            "otro emisor": id_token(iss="https://evil.example"),
            "otra app": id_token(aud="otro-cliente"),
            "vencido": id_token(exp=999),
            "correo sin verificar": id_token(email_verified=False),
            "sin correo": id_token(email=""),
            "basura": "no-es-un-jwt",
        }
        for motivo, token in casos.items():
            with self.assertRaises(google.ErrorGoogle, msg=motivo):
                google.correo_verificado({"id_token": token}, "cliente", ahora=1000)
        with self.assertRaises(google.ErrorGoogle):
            google.correo_verificado({"error": "invalid_grant"}, "cliente", ahora=1000)


class TestSesion(unittest.TestCase):
    def test_firmar_y_verificar(self):
        for sujeto in ("t:42", "g:alguien.apellido@gmail.com"):
            firma = sesion.firmar("tok", "sesion", sujeto, 60, ahora=1000)
            self.assertEqual(sesion.verificar("tok", "sesion", firma, ahora=1030), sujeto)
            self.assertIsNone(sesion.verificar("tok", "sesion", firma, ahora=1061))   # venció
            self.assertIsNone(sesion.verificar("otro", "sesion", firma, ahora=1030))  # otra clave
            self.assertIsNone(sesion.verificar("tok", "entrar", firma, ahora=1030))   # otro uso

    def test_firmas_alteradas(self):
        sujeto, vence, firma = sesion.firmar("tok", "sesion", "t:42", 60, ahora=1000).split(".")
        otro = sesion.firmar("tok", "sesion", "t:43", 60, ahora=1000).split(".")[0]
        for alterada in (f"{otro}.{vence}.{firma}", f"{sujeto}.99999.{firma}", f"{sujeto}.{vence}.x",
                         f"{sujeto}.{vence}.ñandú", "", "a.b", "%%%.1.x", None):
            self.assertIsNone(sesion.verificar("tok", "sesion", alterada, ahora=1000), alterada)

    def test_clave_de_sesion(self):
        self.assertEqual(desde_entorno({"TELEGRAM_TOKEN": "t", "GOOGLE_CLIENT_SECRET": "g"}).clave_sesion, "t")
        self.assertEqual(desde_entorno({"GOOGLE_CLIENT_SECRET": "g"}).clave_sesion, "g")

    def test_secreto_del_webhook(self):
        self.assertEqual(sesion.secreto_webhook("a"), sesion.secreto_webhook("a"))
        self.assertNotEqual(sesion.secreto_webhook("a"), sesion.secreto_webhook("b"))
        self.assertRegex(sesion.secreto_webhook("a"), r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
