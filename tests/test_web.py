import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

from emociones import google, sesion
from emociones.config import Configuracion
from emociones.web import _webhooks_conectados, crear_servidor
from tests.test_bot import APIFalsa
from tests.test_config import id_token
from tests.utiles import nueva_bd

TOKEN = "123:token-de-prueba"


class _NoSeguir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_abrir = urllib.request.build_opener(_NoSeguir).open


class ServidorDePrueba(unittest.TestCase):
    config: dict = {}

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.bd = nueva_bd(self.carpeta.name)
        self.api = APIFalsa()
        config = Configuracion(base_de_datos=self.bd.destino, api=lambda token: self.api, **self.config)
        self.servidor = crear_servidor(config, "127.0.0.1", 0)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.carpeta.cleanup()

    def pedir(self, ruta, metodo="GET", cabeceras=None, cuerpo=None):
        pedido = urllib.request.Request(self.url + ruta, method=metodo, data=cuerpo, headers=cabeceras or {})
        try:
            with _abrir(pedido) as respuesta:
                return respuesta.status, respuesta.headers, respuesta.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.headers, error.read()


class TestPanelLocal(ServidorDePrueba):
    """En tu computadora (127.0.0.1) el panel no pide sesión."""

    def test_pagina_y_estaticos(self):
        estado, _, cuerpo = self.pedir("/")
        self.assertEqual(estado, 200)
        self.assertIn(b"Mis emociones", cuerpo)
        for archivo in ("app.js", "estilos.css"):
            self.assertEqual(self.pedir(f"/estatico/{archivo}")[0], 200)

    def test_estado_y_rueda(self):
        _, _, cuerpo = self.pedir("/api/estado")
        estado = json.loads(cuerpo)
        self.assertEqual((estado["requiere_sesion"], estado["sesion"], estado["base_de_datos"]), (False, True, True))
        self.assertEqual(estado["bot"], "falta_token")
        self.assertEqual(len(json.loads(self.pedir("/api/rueda")[2])["categorias"]), 6)

    def test_registros_filtrados_y_borrado(self):
        viejo, _ = self.bd.crear_registro(1_000, "viejo", None, None, [("triste", "tristeza")])
        nuevo, _ = self.bd.crear_registro(2_000, "nuevo", None, None, [("feliz", "felicidad")])
        _, _, cuerpo = self.pedir("/api/registros?desde=1500")
        self.assertEqual([r["id"] for r in json.loads(cuerpo)["registros"]], [nuevo])
        self.assertEqual(self.pedir(f"/api/registros/{viejo}", "DELETE")[0], 204)
        self.assertEqual(self.pedir(f"/api/registros/{viejo}", "DELETE")[0], 404)

    def test_rechaza_otros_hosts(self):
        self.assertEqual(self.pedir("/api/registros", cabeceras={"Host": "sitio-ajeno.com"})[0], 403)
        self.assertEqual(self.pedir("/api/registros", cabeceras={"Host": "localhost:8000"})[0], 200)

    def test_no_sirve_archivos_fuera_de_public(self):
        for ruta in ("/estatico/../../emociones/bd.py", "/estatico/%2e%2e/index.html", "/estatico/", "/nada"):
            self.assertEqual(self.pedir(ruta)[0], 404, ruta)


class TestPanelEnVercel(ServidorDePrueba):
    """Publicado en internet: los datos requieren la sesión que abre el enlace de /panel."""

    config = dict(token=TOKEN, url_publica="https://emociones.example", solo_local=False,
                  en_vercel=True, produccion=True)

    def setUp(self):
        super().setUp()
        _webhooks_conectados.clear()
        self.bd.guardar_ajuste("dueno", "7")

    def entrar(self, usuario=7):
        firma = sesion.firmar(TOKEN, "entrar", f"t:{usuario}", 600)
        return self.pedir(f"/entrar?t={firma}")

    def cookie(self, cabeceras):
        return {"Cookie": cabeceras["Set-Cookie"].split(";")[0]}

    def test_sin_sesion_no_hay_datos(self):
        self.assertEqual(self.pedir("/api/registros")[0], 401)
        self.assertEqual(self.pedir("/api/registros/1", "DELETE")[0], 401)
        self.assertEqual(self.pedir("/api/registros", cabeceras={"Cookie": "sesion=7.9999999999.falsa"})[0], 401)

    def test_el_enlace_abre_la_sesion(self):
        estado, cabeceras, _ = self.entrar()
        self.assertEqual(estado, 303)
        self.assertEqual(cabeceras["Location"], "/")
        for atributo in ("HttpOnly", "Secure", "SameSite=Lax"):
            self.assertIn(atributo, cabeceras["Set-Cookie"])
        self.bd.crear_registro(int(time.time()), "llueve", None, 7, [("triste", "tristeza")])
        estado, _, cuerpo = self.pedir("/api/registros", cabeceras=self.cookie(cabeceras))
        self.assertEqual(estado, 200)
        self.assertEqual(len(json.loads(cuerpo)["registros"]), 1)
        _, _, cuerpo = self.pedir("/api/estado", cabeceras=self.cookie(cabeceras))
        self.assertTrue(json.loads(cuerpo)["sesion"])

    def test_enlaces_invalidos(self):
        self.assertEqual(self.entrar(usuario=8)[0], 403)  # no es el dueño
        vencido = sesion.firmar(TOKEN, "entrar", "t:7", -1)
        self.assertEqual(self.pedir(f"/entrar?t={vencido}")[0], 403)
        de_sesion = sesion.firmar(TOKEN, "sesion", "t:7", 600)  # una cookie no sirve como enlace
        self.assertEqual(self.pedir(f"/entrar?t={de_sesion}")[0], 403)
        # …ni un enlace como cookie
        enlace = sesion.firmar(TOKEN, "entrar", "t:7", 600)
        self.assertEqual(self.pedir("/api/registros", cabeceras={"Cookie": f"sesion={enlace}"})[0], 401)

    def test_google_sin_configurar(self):
        self.assertEqual(self.pedir("/auth/google")[0], 503)

    def test_salir(self):
        estado, cabeceras, _ = self.pedir("/salir")
        self.assertEqual(estado, 303)
        self.assertIn("Max-Age=0", cabeceras["Set-Cookie"])

    def test_estado_conecta_el_webhook_una_vez(self):
        _, _, cuerpo = self.pedir("/api/estado")
        estado = json.loads(cuerpo)
        self.assertEqual((estado["sesion"], estado["bot"]), (False, "conectado"))
        metodo, parametros = self.api.llamadas[0]
        self.assertEqual(metodo, "setWebhook")
        self.assertEqual(parametros["url"], "https://emociones.example/api/telegram")
        self.assertEqual(parametros["secret_token"], sesion.secreto_webhook(TOKEN))
        self.pedir("/api/estado")
        self.assertEqual([m for m, _ in self.api.llamadas], ["setWebhook", "setMyCommands"])

    def test_webhook(self):
        aviso = json.dumps({"update_id": 1, "message": {
            "message_id": 1, "date": int(time.time()), "text": "triste: llueve",
            "chat": {"id": 7, "type": "private"}, "from": {"id": 7},
        }}).encode()
        tipo = {"Content-Type": "application/json"}
        self.assertEqual(self.pedir("/api/telegram", "POST", tipo, aviso)[0], 403)
        falso = {**tipo, "X-Telegram-Bot-Api-Secret-Token": "otra-cosa"}
        self.assertEqual(self.pedir("/api/telegram", "POST", falso, aviso)[0], 403)
        self.assertEqual(self.bd.listar_registros(), [])

        valido = {**tipo, "X-Telegram-Bot-Api-Secret-Token": sesion.secreto_webhook(TOKEN)}
        self.assertEqual(self.pedir("/api/telegram", "POST", valido, aviso)[0], 200)
        [registro] = self.bd.listar_registros()
        self.assertEqual(registro["causa"], "Llueve")
        self.assertIn("Guardado", self.api.enviados[-1][0])


class TestInicioConGoogle(ServidorDePrueba):
    config = dict(url_publica="https://emociones.example", solo_local=False, en_vercel=True,
                  produccion=True, google_id="cliente", google_secreto="secreto",
                  google_correos={"yo@gmail.com"})

    def setUp(self):
        self.pedidos_a_google = []
        self.correo = "Yo@Gmail.com"

        def token_falso(datos):
            self.pedidos_a_google.append(datos)
            return {"id_token": id_token(aud="cliente", exp=time.time() + 60, email=self.correo)}

        self.config = {**self.config, "google_token": token_falso}
        super().setUp()

    def ir_a_google(self):
        estado, cabeceras, _ = self.pedir("/auth/google")
        self.assertEqual(estado, 303)
        destino = urlsplit(cabeceras["Location"])
        self.assertEqual(destino.netloc, "accounts.google.com")
        parametros = {k: v[0] for k, v in parse_qs(destino.query).items()}
        return parametros, cabeceras["Set-Cookie"].split(";")[0]

    def volver(self, state, cookie):
        return self.pedir(f"/auth/google/callback?code=codigo-de-google&state={state}",
                          cabeceras={"Cookie": cookie})

    def test_el_estado_ofrece_google(self):
        self.assertTrue(json.loads(self.pedir("/api/estado")[2])["google"])

    def test_inicio_de_sesion(self):
        parametros, cookie = self.ir_a_google()
        self.assertEqual(parametros["redirect_uri"], "https://emociones.example/auth/google/callback")
        estado, cabeceras, _ = self.volver(parametros["state"], cookie)
        self.assertEqual((estado, cabeceras["Location"]), (303, "/"))
        # PKCE: el verificador que se canjea corresponde al desafío que vio Google.
        [pedido] = self.pedidos_a_google
        self.assertEqual(pedido["code"], "codigo-de-google")
        self.assertEqual(google.desafio(pedido["code_verifier"]), parametros["code_challenge"])
        [sesion_nueva] = [c for c in cabeceras.get_all("Set-Cookie") if c.startswith("sesion=")]
        self.assertEqual(self.pedir("/api/registros", cabeceras={"Cookie": sesion_nueva.split(";")[0]})[0], 200)

    def test_state_que_no_coincide(self):
        parametros, cookie = self.ir_a_google()
        self.assertEqual(self.volver("otro-state", cookie)[0], 400)
        self.assertEqual(self.volver(parametros["state"], "")[0], 400)  # sin la cookie del primer paso
        self.assertEqual(self.pedidos_a_google, [])

    def test_correo_no_autorizado(self):
        self.correo = "intruso@gmail.com"
        parametros, cookie = self.ir_a_google()
        estado, cabeceras, cuerpo = self.volver(parametros["state"], cookie)
        self.assertEqual(estado, 403)
        self.assertIn(b"intruso@gmail.com", cuerpo)
        self.assertFalse(any(c.startswith("sesion=") for c in cabeceras.get_all("Set-Cookie") or []))


if __name__ == "__main__":
    unittest.main()
