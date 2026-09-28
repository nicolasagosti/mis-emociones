"""Enlaces de acceso y cookies de sesión firmados con HMAC.

No se guarda nada en el servidor: la firma se hace con una clave derivada del token del bot,
así que solo quien controla el bot puede generar enlaces válidos (con el comando /panel).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

DURACION_ENLACE = 10 * 60             # el enlace que manda /panel
DURACION_SESION = 30 * 24 * 60 * 60   # la cookie del navegador


def _clave(token: str, uso: str) -> bytes:
    return hmac.new(token.encode(), f"mis-emociones/{uso}".encode(), hashlib.sha256).digest()


def _firma(token: str, uso: str, datos: str) -> str:
    digest = hmac.new(_clave(token, uso), datos.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def firmar(token: str, uso: str, usuario_id: int, duracion: int, ahora: float | None = None) -> str:
    """«usuario.vencimiento.firma». `uso` separa enlaces de sesiones: uno no sirve como el otro."""
    vence = int(time.time() if ahora is None else ahora) + duracion
    datos = f"{usuario_id}.{vence}"
    return f"{datos}.{_firma(token, uso, datos)}"


def verificar(token: str, uso: str, valor: str | None, ahora: float | None = None) -> int | None:
    """El usuario, si la firma es válida y no venció; si no, None."""
    if not token or not valor:
        return None
    try:
        usuario, vence, firma = valor.split(".")
        usuario_id, vencimiento = int(usuario), int(vence)
    except ValueError:
        return None
    if not hmac.compare_digest(firma, _firma(token, uso, f"{usuario}.{vence}")):
        return None
    if vencimiento < (time.time() if ahora is None else ahora):
        return None
    return usuario_id


def secreto_webhook(token: str) -> str:
    """Telegram lo manda en cada aviso al webhook; así se sabe que el aviso es auténtico."""
    return hmac.new(token.encode(), b"mis-emociones/webhook", hashlib.sha256).hexdigest()
