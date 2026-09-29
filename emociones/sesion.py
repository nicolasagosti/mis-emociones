"""Enlaces de acceso y cookies de sesión firmados con HMAC.

No se guarda nada en el servidor: la firma usa una clave derivada de un secreto de la
configuración (el token del bot o el secreto de Google), así que nadie más puede fabricarlas.
El «sujeto» dice quién entró: «t:<id de Telegram>» o «g:<correo de Google>».
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

DURACION_ENLACE = 10 * 60             # el enlace que manda /panel
DURACION_SESION = 30 * 24 * 60 * 60   # la cookie del navegador


def _clave(secreto: str, uso: str) -> bytes:
    return hmac.new(secreto.encode(), f"mis-emociones/{uso}".encode(), hashlib.sha256).digest()


def _firma(secreto: str, uso: str, datos: str) -> str:
    digest = hmac.new(_clave(secreto, uso), datos.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def firmar(secreto: str, uso: str, sujeto: str, duracion: int, ahora: float | None = None) -> str:
    """«sujeto.vencimiento.firma». `uso` separa enlaces de sesiones: uno no sirve como el otro."""
    vence = int(time.time() if ahora is None else ahora) + duracion
    datos = f"{base64.urlsafe_b64encode(sujeto.encode()).decode().rstrip('=')}.{vence}"
    return f"{datos}.{_firma(secreto, uso, datos)}"


def verificar(secreto: str, uso: str, valor: str | None, ahora: float | None = None) -> str | None:
    """El sujeto, si la firma es válida y no venció; si no, None."""
    if not secreto or not valor:
        return None
    try:
        sujeto, vence, firma = valor.split(".")
        vencimiento = int(vence)
        texto = base64.urlsafe_b64decode(sujeto + "=" * (-len(sujeto) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(firma.encode(), _firma(secreto, uso, f"{sujeto}.{vence}").encode()):
        return None
    if vencimiento < (time.time() if ahora is None else ahora):
        return None
    return texto


def secreto_webhook(token: str) -> str:
    """Telegram lo manda en cada aviso al webhook; así se sabe que el aviso es auténtico."""
    return hmac.new(token.encode(), b"mis-emociones/webhook", hashlib.sha256).hexdigest()
