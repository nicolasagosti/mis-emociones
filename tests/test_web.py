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
        usuario = self.bd.crear_usuario()["id"]  # en tu computadora: la única cuenta
        viejo, _ = self.bd.crear_registro(usuario, 1_000, "viejo", None, None, [("triste", "tristeza")])
        nuevo, _ = self.bd.crear_registro(usuario, 2_000, "nuevo", None, None, [("feliz", "felicidad")])
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
        usuario = self.bd.usuario_por_telegram(7)["id"]  # el dueño de antes ya tiene cuenta
        self.bd.crear_registro(usuario, int(time.time()), "llueve", None, 7, [("triste", "tristeza")])
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
        self.assertIsNone(self.bd.usuario_por_telegram(7))

        valido = {**tipo, "X-Telegram-Bot-Api-Secret-Token": sesion.secreto_webhook(TOKEN)}
        self.assertEqual(self.pedir("/api/telegram", "POST", valido, aviso)[0], 200)
        [registro] = self.bd.listar_registros(self.bd.usuario_por_telegram(7)["id"])
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

    def test_entra_alguien_con_quien_compartiste(self):
        yo = self.bd.crear_usuario(correo="yo@gmail.com")
        self.bd.compartir(yo["id"], "psico@gmail.com", 0)
        self.correo = "Psico@gmail.com"
        parametros, cookie = self.ir_a_google()
        self.assertEqual(self.volver(parametros["state"], cookie)[0], 303)

    def test_cualquier_cuenta_de_google_entra_con_su_propio_diario(self):
        self.correo = "Nueva@gmail.com"
        parametros, cookie = self.ir_a_google()
        estado, cabeceras, _ = self.volver(parametros["state"], cookie)
        self.assertEqual(estado, 303)
        [sesion_nueva] = [c for c in cabeceras.get_all("Set-Cookie") if c.startswith("sesion=")]
        estado = json.loads(self.pedir("/api/estado", cabeceras={"Cookie": sesion_nueva.split(";")[0]})[2])
        self.assertEqual((estado["cuenta"]["correo"], estado["compartidos"]), ("nueva@gmail.com", []))


class TestDiarios(ServidorDePrueba):
    """Cada cuenta tiene su diario; los que le compartieron los ve en solo lectura."""

    config = dict(url_publica="https://emociones.example", solo_local=False, en_vercel=True, produccion=True,
                  token=TOKEN, google_id="cliente", google_secreto="secreto", google_correos={"yo@gmail.com"})

    def sesion_de(self, correo):
        return {"Cookie": "sesion=" + sesion.firmar(TOKEN, "sesion", f"g:{correo}", 600)}

    def estado(self, correo):
        return json.loads(self.pedir("/api/estado", cabeceras=self.sesion_de(correo))[2])

    def compartir(self, correo, de="yo@gmail.com", cabeceras=None):
        cabeceras = {**self.sesion_de(de), "Content-Type": "application/json", **(cabeceras or {})}
        return self.pedir("/api/accesos", "POST", cabeceras, json.dumps({"correo": correo}).encode())

    def causas(self, correo, diario=None):
        ruta = "/api/registros" + (f"?diario={diario}" if diario else "")
        estado, _, cuerpo = self.pedir(ruta, cabeceras=self.sesion_de(correo))
        return estado, [r["causa"] for r in json.loads(cuerpo).get("registros", [])]

    def test_cada_cuenta_tiene_su_diario_y_ve_los_que_le_compartieron(self):
        yo = self.estado("yo@gmail.com")["cuenta"]
        self.assertEqual(self.compartir("Psico@Gmail.com")[0], 200)
        psico = self.estado("psico@gmail.com")
        self.assertEqual(psico["cuenta"]["correo"], "psico@gmail.com")
        self.assertEqual(psico["compartidos"], [{"id": yo["id"], "correo": "yo@gmail.com"}])

        mio, _ = self.bd.crear_registro(yo["id"], int(time.time()), "Llueve", None, None, [("triste", "tristeza")])
        self.bd.crear_registro(psico["cuenta"]["id"], int(time.time()), "Consulta", None, None, [])
        self.assertEqual(self.causas("psico@gmail.com"), (200, ["Consulta"]))
        self.assertEqual(self.causas("psico@gmail.com", yo["id"]), (200, ["Llueve"]))
        self.assertEqual(self.causas("yo@gmail.com", psico["cuenta"]["id"])[0], 403)  # a mí no me lo compartió
        # No puede borrar registros de un diario ajeno.
        self.assertEqual(self.pedir(f"/api/registros/{mio}", "DELETE", self.sesion_de("psico@gmail.com"))[0], 404)
        self.assertIsNotNone(self.bd.obtener_registro(mio))

        # Al dejar de compartir, pierde ese diario pero conserva el suyo.
        quitar = self.pedir("/api/accesos/psico%40gmail.com", "DELETE", self.sesion_de("yo@gmail.com"))
        self.assertEqual(quitar[0], 204)
        self.assertEqual(self.causas("psico@gmail.com", yo["id"])[0], 403)
        self.assertEqual(self.causas("psico@gmail.com"), (200, ["Consulta"]))

    def test_una_cuenta_nueva_no_ve_nada_ajeno(self):
        yo = self.estado("yo@gmail.com")["cuenta"]
        self.bd.crear_registro(yo["id"], int(time.time()), "Llueve", None, None, [("triste", "tristeza")])
        nueva = self.estado("nueva@gmail.com")
        self.assertEqual((nueva["cuenta"]["correo"], nueva["compartidos"]), ("nueva@gmail.com", []))
        self.assertEqual(self.causas("nueva@gmail.com"), (200, []))
        self.assertEqual(self.causas("nueva@gmail.com", yo["id"])[0], 403)

    def test_sin_sesion_no_hay_nada(self):
        cabeceras = {"Content-Type": "application/json"}
        self.assertEqual(self.pedir("/api/registros")[0], 401)
        self.assertEqual(self.pedir("/api/accesos", "POST", cabeceras, b'{"correo": "a@b.co"}')[0], 401)

    def test_quien_fue_invitada_puede_compartir_su_diario(self):
        self.compartir("psico@gmail.com")
        self.assertEqual(self.compartir("colega@gmail.com", de="psico@gmail.com")[0], 200)
        colega = self.estado("colega@gmail.com")
        self.assertEqual([d["correo"] for d in colega["compartidos"]], ["psico@gmail.com"])

    def test_correos_invalidos_y_otros_sitios(self):
        for correo in ("", "no-es-correo", "a@b", "dos@gmail.com,tres@gmail.com", "x" * 250 + "@gmail.com"):
            self.assertEqual(self.compartir(correo)[0], 400, correo)
        como_texto = {**self.sesion_de("yo@gmail.com"), "Content-Type": "text/plain"}
        self.assertEqual(self.pedir("/api/accesos", "POST", como_texto, b'{"correo": "a@b.co"}')[0], 415)
        self.assertEqual(self.compartir("psico@gmail.com", cabeceras={"Origin": "https://sitio-ajeno.com"})[0], 403)
        self.assertEqual(self.compartir("psico@gmail.com", cabeceras={"Origin": "https://emociones.example"})[0], 200)

    def test_vincular_y_desvincular_telegram(self):
        yo = self.estado("yo@gmail.com")["cuenta"]
        self.assertFalse(yo["telegram"])
        estado, _, cuerpo = self.pedir("/api/telegram/vincular", "POST", self.sesion_de("yo@gmail.com"))
        enlace = json.loads(cuerpo)["enlace"]
        self.assertTrue(enlace.startswith("https://t.me/emociones_bot?start="))
        codigo = enlace.split("start=", 1)[1]
        self.assertEqual(sesion.verificar_vinculo(TOKEN, codigo), yo["id"])

        # Tocar «Iniciar» en Telegram manda /start <código> al webhook.
        aviso = json.dumps({"update_id": 1, "message": {
            "message_id": 1, "date": int(time.time()), "text": f"/start {codigo}",
            "chat": {"id": 55, "type": "private"}, "from": {"id": 55},
        }}).encode()
        cabeceras = {"Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": sesion.secreto_webhook(TOKEN)}
        self.assertEqual(self.pedir("/api/telegram", "POST", cabeceras, aviso)[0], 200)
        self.assertTrue(self.estado("yo@gmail.com")["cuenta"]["telegram"])

        self.assertEqual(self.pedir("/api/telegram/desvincular", "POST", self.sesion_de("yo@gmail.com"))[0], 200)
        self.assertFalse(self.estado("yo@gmail.com")["cuenta"]["telegram"])


if __name__ == "__main__":
    unittest.main()
