"""Panel web y API. El mismo código atiende en tu computadora (main.py) y en Vercel (api/index.py).

Rutas:
    GET    /api/estado          qué está configurado y si hay sesión (público, sin datos personales)
    GET    /api/rueda           la rueda de los sentimientos (público)
    GET    /api/registros       tus registros (requiere sesión fuera de tu computadora)
    DELETE /api/registros/<id>  borrar un registro (ídem)
    POST   /api/telegram        webhook del bot (solo Telegram, con su clave secreta)
    GET    /auth/google         lleva a Google para elegir la cuenta
    GET    /auth/google/callback  Google vuelve aquí: si el correo está autorizado, abre la sesión
    GET    /entrar?t=…          enlace que manda /panel: abre la sesión
    GET    /salir               cierra la sesión
"""

from __future__ import annotations

import hmac
import html
import json
import logging
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import google, rueda, sesion
from .bd import BaseDeDatos
from .bot import Bot, conectar_webhook, es_dueno
from .config import LOCALES, RAIZ, Configuracion
from .telegram import ErrorTelegram

log = logging.getLogger("emociones.web")

PUBLICO = (RAIZ / "public").resolve()
TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}
SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
}
MAX_AVISO = 1_000_000  # bytes aceptados en un aviso de Telegram

# Webhooks que esta instancia ya registró en Telegram (en Vercel, una vez por instancia).
_webhooks_conectados: set[str] = set()


class Panel(BaseHTTPRequestHandler):
    config = Configuracion()

    def do_GET(self) -> None:
        self._atender(self._get)

    def do_POST(self) -> None:
        self._atender(self._post)

    def do_DELETE(self) -> None:
        self._atender(self._delete)

    def _atender(self, metodo) -> None:
        if not self._host_permitido():
            return
        try:
            metodo()
        except Exception:
            log.exception("Error al atender %s %s", self.command, urlsplit(self.path).path)
            self._error(500)

    def _get(self) -> None:
        url = urlsplit(self.path)
        consulta = parse_qs(url.query)
        if url.path == "/api/estado":
            self._json(self._estado())
        elif url.path == "/api/rueda":
            self._json(rueda.como_json())
        elif url.path == "/api/registros":
            bd = self._bd_autorizada()
            if bd:
                desde = consulta.get("desde", [""])[0]
                self._json({"registros": bd.listar_registros(desde=int(desde) if desde.isdigit() else None)})
        elif url.path == "/auth/google":
            self._google_ida()
        elif url.path == "/auth/google/callback":
            self._google_vuelta(consulta)
        elif url.path == "/entrar":
            self._entrar(consulta.get("t", [""])[0])
        elif url.path == "/salir":
            self._redirigir("/", self._cookie("sesion", "", 0))
        elif url.path == "/":
            self._archivo("index.html")
        elif url.path.startswith("/estatico/"):
            self._archivo(url.path.removeprefix("/"))
        else:
            self._error(404)

    def _post(self) -> None:
        if urlsplit(self.path).path == "/api/telegram":
            self._webhook()
        else:
            self._error(404)

    def _delete(self) -> None:
        partes = urlsplit(self.path).path.strip("/").split("/")
        if len(partes) != 3 or partes[:2] != ["api", "registros"] or not partes[2].isdigit():
            self._error(404)
            return
        bd = self._bd_autorizada()
        if bd is None:
            return
        if bd.borrar_registro(int(partes[2])):
            self._enviar(204, b"", "text/plain")
        else:
            self._error(404)

    # --- Sesión y configuración -------------------------------------------------------

    def _bd(self) -> BaseDeDatos | None:
        return BaseDeDatos(self.config.base_de_datos) if self.config.base_de_datos else None

    def _bd_autorizada(self) -> BaseDeDatos | None:
        """La base de datos, si quien pide puede ver los datos; si no, responde el error."""
        bd = self._bd()
        if bd is None:
            self._error(503)
        elif self.config.requiere_sesion and self._sujeto(bd) is None:
            self._error(401)
        else:
            return bd
        return None

    def _cookies(self) -> SimpleCookie:
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            pass
        return cookies

    def _sujeto(self, bd: BaseDeDatos) -> str | None:
        """Quién tiene la sesión abierta («t:<id>» o «g:<correo>»), si todavía puede entrar."""
        cookie = self._cookies().get("sesion")
        sujeto = sesion.verificar(self.config.clave_sesion, "sesion", cookie.value if cookie else None)
        return sujeto if self._puede_entrar(bd, sujeto) else None

    def _puede_entrar(self, bd: BaseDeDatos, sujeto: str | None) -> bool:
        tipo, _, valor = (sujeto or "").partition(":")
        if tipo == "t" and valor.isdigit():
            return es_dueno(bd, self.config.permitidos, int(valor))
        if tipo == "g":
            return valor in self.config.google_correos
        return False

    def _estado(self) -> dict:
        cfg = self.config
        bd = None
        if cfg.base_de_datos:
            try:
                bd = BaseDeDatos(cfg.base_de_datos)
            except Exception:
                log.exception("No pude conectar con la base de datos")
        return {
            "requiere_sesion": cfg.requiere_sesion,
            "sesion": not cfg.requiere_sesion or (bd is not None and self._sujeto(bd) is not None),
            "vercel": cfg.en_vercel,
            "base_de_datos": bd is not None,
            "google": cfg.google_listo,
            "token": bool(cfg.token),
            "bot": self._estado_bot(bd is not None),
        }

    def _estado_bot(self, hay_bd: bool) -> str:
        """En producción de Vercel, conecta el webhook del bot la primera vez."""
        cfg = self.config
        if not cfg.token:
            return "falta_token"
        if not cfg.en_vercel:
            return "local"
        if not cfg.produccion:
            return "solo_produccion"
        if not hay_bd:
            return "espera_base_de_datos"
        url = f"{cfg.url_publica}/api/telegram"
        if url not in _webhooks_conectados:
            try:
                conectar_webhook(cfg.api(cfg.token), url, cfg.token)
            except ErrorTelegram as error:
                log.warning("No pude conectar el webhook: %s", error)
                return "token_invalido" if error.codigo in (401, 404) else "error"
            except OSError as error:
                log.warning("No pude conectar el webhook: %s", error)
                return "error"
            _webhooks_conectados.add(url)
            log.info("Webhook del bot conectado a %s", url)
        return "conectado"

    def _entrar(self, firma: str) -> None:
        """El enlace de /panel: solo lo genera el bot, para el dueño."""
        bd = self._bd()
        sujeto = sesion.verificar(self.config.clave_sesion, "entrar", firma)
        if bd is None or not (sujeto or "").startswith("t:") or not self._puede_entrar(bd, sujeto):
            self._pagina(403, "El enlace venció o no es válido",
                         "Pídele uno nuevo a tu bot de Telegram con el comando /panel.")
            return
        self._abrir_sesion(sujeto)

    def _google_ida(self) -> None:
        cfg = self.config
        if not cfg.google_listo:
            self._pagina(503, "El inicio con Google no está configurado",
                         "Faltan GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET o GOOGLE_CORREOS en la configuración.")
            return
        # state evita que otro sitio complete un inicio de sesión a tu nombre; el verificador
        # (PKCE) hace que el código que devuelve Google no sirva sin esta misma cookie.
        state, verificador = google.nuevo_intento()
        destino = google.url_autorizacion(cfg.google_id, self._vuelta_google(), state, verificador)
        self._redirigir(destino, self._cookie("google", f"{state}.{verificador}", 600, "/auth/google"))

    def _google_vuelta(self, consulta: dict[str, list[str]]) -> None:
        cfg = self.config
        borrar = self._cookie("google", "", 0, "/auth/google")
        guardado = self._cookies().get("google")
        state, _, verificador = (guardado.value if guardado else "").partition(".")
        recibido = consulta.get("state", [""])[0]
        codigo = consulta.get("code", [""])[0]
        if not (cfg.google_listo and state and codigo and hmac.compare_digest(state.encode(), recibido.encode())):
            self._pagina(400, "No se pudo iniciar sesión",
                         "El intento venció o se canceló. Vuelve a tocar «Entrar con Google».", borrar)
            return
        try:
            respuesta = cfg.google_token({
                "code": codigo, "client_id": cfg.google_id, "client_secret": cfg.google_secreto,
                "redirect_uri": self._vuelta_google(), "grant_type": "authorization_code",
                "code_verifier": verificador,
            })
            correo = google.correo_verificado(respuesta, cfg.google_id)
        except google.ErrorGoogle as error:
            log.warning("No se pudo iniciar sesión con Google: %s", error)
            self._pagina(403, "No pude verificar tu cuenta de Google", "Vuelve a intentarlo en un momento.", borrar)
            return
        if correo not in cfg.google_correos:
            log.warning("Intento de entrar con una cuenta de Google no autorizada: %s", correo)
            self._pagina(403, "Esta cuenta no tiene acceso",
                         f"{correo} no está autorizada para ver este panel.", borrar)
            return
        self._abrir_sesion(f"g:{correo}", borrar)

    def _vuelta_google(self) -> str:
        return f"{self.config.url_publica}/auth/google/callback"

    def _abrir_sesion(self, sujeto: str, *otras_cookies: str) -> None:
        valor = sesion.firmar(self.config.clave_sesion, "sesion", sujeto, sesion.DURACION_SESION)
        self._redirigir("/", self._cookie("sesion", valor, sesion.DURACION_SESION), *otras_cookies)

    def _cookie(self, nombre: str, valor: str, duracion: int, ruta: str = "/") -> str:
        partes = [f"{nombre}={valor}", f"Path={ruta}", f"Max-Age={duracion}", "HttpOnly", "SameSite=Lax"]
        if self.config.url_publica.startswith("https://"):
            partes.append("Secure")
        return "; ".join(partes)

    def _webhook(self) -> None:
        cfg = self.config
        secreto = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "").encode()
        if not cfg.token or not hmac.compare_digest(secreto, sesion.secreto_webhook(cfg.token).encode()):
            self._error(403)
            return
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > MAX_AVISO:
            self._error(413)
            return
        try:
            novedad = json.loads(self.rfile.read(largo))
        except ValueError:
            self._error(400)
            return
        bd = self._bd()
        if bd is None:
            self._error(503)  # Telegram vuelve a intentar más tarde
            return
        try:
            with bd.abierta():
                bot = Bot(cfg.api(cfg.token), bd, cfg.permitidos, url_panel=cfg.url_publica,
                          clave=cfg.clave_sesion, zona=cfg.zona)
                bot.procesar(novedad)
        except Exception:
            # Se responde 200 igual: si Telegram reintentara, podría duplicar el registro.
            log.exception("Error al procesar un aviso de Telegram")
        self._json({"ok": True})

    def _host_permitido(self) -> bool:
        """Si el panel escucha solo en esta computadora, rechaza otros nombres de host
        (evita que una página web ajena lea tus datos con un ataque de DNS rebinding)."""
        if not self.config.solo_local:
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host in LOCALES:
            return True
        self._error(403)
        return False

    # --- Respuestas --------------------------------------------------------------------

    def _archivo(self, nombre: str) -> None:
        ruta = (PUBLICO / nombre).resolve()
        if PUBLICO not in ruta.parents or not ruta.is_file():
            self._error(404)
            return
        self._enviar(200, ruta.read_bytes(), TIPOS.get(ruta.suffix, "application/octet-stream"))

    def _pagina(self, codigo: int, titulo: str, texto: str, *cookies: str) -> None:
        cuerpo = (
            '<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Mis emociones</title><link rel="stylesheet" href="/estatico/estilos.css"></head>'
            f'<body><main class="acceso"><section class="tarjeta"><h1>{html.escape(titulo)}</h1>'
            f'<p>{html.escape(texto)}</p><p><a href="/">Volver al inicio</a></p></section></main></body></html>'
        )
        self._enviar(codigo, cuerpo.encode(), TIPOS[".html"], cookies)

    def _redirigir(self, destino: str, *cookies: str) -> None:
        self.send_response(303)
        self.send_header("Location", destino)
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self._cabeceras_seguridad()
        self.end_headers()

    def _json(self, datos: dict) -> None:
        self._enviar(200, json.dumps(datos, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _error(self, codigo: int) -> None:
        self._enviar(codigo, json.dumps({"error": codigo}).encode(), "application/json")

    def _enviar(self, codigo: int, cuerpo: bytes, tipo: str, cookies: tuple[str, ...] = ()) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self._cabeceras_seguridad()
        self.end_headers()
        self.wfile.write(cuerpo)

    def _cabeceras_seguridad(self) -> None:
        for clave, valor in SEGURIDAD.items():
            self.send_header(clave, valor)

    def log_message(self, formato: str, *args) -> None:
        log.debug(formato, *args)


def manejador(config: Configuracion) -> type[Panel]:
    """Una clase de Panel con su configuración (Vercel busca una variable `handler` así)."""
    return type("handler", (Panel,), {"config": config})


def crear_servidor(config: Configuracion, host: str = "127.0.0.1", puerto: int = 8000) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer((host, puerto), manejador(config))
    servidor.daemon_threads = True
    return servidor
