"""Inicio de sesión con Google (OpenID Connect: flujo de código con PKCE), sin dependencias."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

AUTORIZACION = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
EMISORES = {"https://accounts.google.com", "accounts.google.com"}


class ErrorGoogle(Exception):
    pass


def _b64url(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def nuevo_intento() -> tuple[str, str]:
    """(state, code_verifier) al azar para un inicio de sesión."""
    return secrets.token_urlsafe(24), secrets.token_urlsafe(48)


def desafio(verificador: str) -> str:
    return _b64url(hashlib.sha256(verificador.encode()).digest())


def url_autorizacion(client_id: str, redirect_uri: str, state: str, verificador: str) -> str:
    """La página de Google donde la persona elige su cuenta."""
    parametros = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "code_challenge": desafio(verificador),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTORIZACION}?{urllib.parse.urlencode(parametros)}"


def pedir_token(datos: dict) -> dict:
    """Canjea el código que devuelve Google por los tokens de la cuenta."""
    pedido = urllib.request.Request(
        TOKEN, data=urllib.parse.urlencode(datos).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=15) as respuesta:
            return json.load(respuesta)
    except urllib.error.HTTPError as error:
        with error:
            detalle = error.read()[:300]
        raise ErrorGoogle(f"Google respondió {error.code}: {detalle!r}") from None
    except (OSError, ValueError) as error:
        raise ErrorGoogle(f"no pude hablar con Google: {error}") from None


def correo_verificado(respuesta: dict, client_id: str, ahora: float | None = None) -> str:
    """El correo del id_token, después de validar que es para esta aplicación y está vigente.

    El id_token llega directo de Google por HTTPS (no pasa por el navegador), así que según
    OpenID Connect alcanza con validar su contenido, sin verificar la firma.
    """
    try:
        carga = respuesta["id_token"].split(".")[1]
        datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
    except (KeyError, IndexError, ValueError, AttributeError, TypeError):
        raise ErrorGoogle("Google no devolvió un id_token válido") from None
    audiencia = datos.get("aud")
    if datos.get("iss") not in EMISORES:
        raise ErrorGoogle("el id_token no es de Google")
    if audiencia != client_id and not (isinstance(audiencia, list) and client_id in audiencia):
        raise ErrorGoogle("el id_token es para otra aplicación")
    if float(datos.get("exp", 0)) < (time.time() if ahora is None else ahora):
        raise ErrorGoogle("el id_token venció")
    if datos.get("email_verified") not in (True, "true"):
        raise ErrorGoogle("el correo de la cuenta no está verificado")
    correo = str(datos.get("email", "")).strip().lower()
    if not correo:
        raise ErrorGoogle("Google no devolvió el correo")
    return correo
