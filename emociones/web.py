"""Panel web y API. El mismo código atiende en tu computadora (main.py) y en Vercel (api/index.py).

Rutas:
    GET    /api/estado          qué está configurado y si hay sesión (público, sin datos personales)
    GET    /api/rueda           la rueda de los sentimientos (público)
    GET    /api/registros       tus registros (requiere sesión fuera de tu computadora)
    DELETE /api/registros/<id>  borrar un registro (ídem)
    POST   /api/telegram        webhook del bot (solo Telegram, con su clave secreta)
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

from . import rueda, sesion
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
        elif url.path == "/entrar":
            self._entrar(consulta.get("t", [""])[0])
        elif url.path == "/salir":
            self._redirigir("/", self._cookie("", 0))
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
        elif self.config.requiere_sesion and self._usuario(bd) is None:
            self._error(401)
        else:
            return bd
        return None

    def _usuario(self, bd: BaseDeDatos) -> int | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        valor = cookie["sesion"].value if "sesion" in cookie else None
        usuario = sesion.verificar(self.config.token, "sesion", valor)
        return usuario if es_dueno(bd, self.config.permitidos, usuario) else None

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
            "sesion": not cfg.requiere_sesion or (bd is not None and self._usuario(bd) is not None),
            "vercel": cfg.en_vercel,
            "base_de_datos": bd is not None,
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
        bd = self._bd()
        usuario = sesion.verificar(self.config.token, "entrar", firma)
        if bd is None or not es_dueno(bd, self.config.permitidos, usuario):
            self._pagina(403, "El enlace venció o no es válido",
                         "Pídele uno nuevo a tu bot de Telegram con el comando /panel.")
            return
        valor = sesion.firmar(self.config.token, "sesion", usuario, sesion.DURACION_SESION)
        self._redirigir("/", self._cookie(valor, sesion.DURACION_SESION))

    def _cookie(self, valor: str, duracion: int) -> str:
        partes = [f"sesion={valor}", "Path=/", f"Max-Age={duracion}", "HttpOnly", "SameSite=Lax"]
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
                          clave=cfg.token, zona=cfg.zona)
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

    def _pagina(self, codigo: int, titulo: str, texto: str) -> None:
        cuerpo = (
            '<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Mis emociones</title><link rel="stylesheet" href="/estatico/estilos.css"></head>'
            f'<body><main class="acceso"><section class="tarjeta"><h1>{html.escape(titulo)}</h1>'
            f'<p>{html.escape(texto)}</p><p><a href="/">Volver al inicio</a></p></section></main></body></html>'
        )
        self._enviar(codigo, cuerpo.encode(), TIPOS[".html"])

    def _redirigir(self, destino: str, cookie: str | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", destino)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self._cabeceras_seguridad()
        self.end_headers()

    def _json(self, datos: dict) -> None:
        self._enviar(200, json.dumps(datos, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _error(self, codigo: int) -> None:
        self._enviar(codigo, json.dumps({"error": codigo}).encode(), "application/json")

    def _enviar(self, codigo: int, cuerpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
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
