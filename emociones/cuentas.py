"""Cuentas: quién es cada persona (por su Google o su Telegram).

Cualquier persona con una cuenta de Google puede crear la suya: tiene su propio diario, ve los
que otras personas le compartieron (en solo lectura) y puede vincular su Telegram.
"""

from __future__ import annotations

from .bd import BaseDeDatos
from .config import Configuracion


def adoptar_legado(bd: BaseDeDatos, usuario_id: int) -> None:
    """Lo guardado cuando la app tenía un solo dueño pasa a esta cuenta (una sola vez)."""
    if bd.ajuste("legado") is not None:
        return
    bd.adoptar_datos_sin_dueno(usuario_id)
    dueno = bd.ajuste("dueno")  # el Telegram del dueño anterior
    if dueno and dueno.isdigit() and bd.usuario_por_telegram(int(dueno)) is None:
        bd.vincular_telegram(usuario_id, int(dueno))
    bd.guardar_ajuste("legado", str(usuario_id))


def _administrador_unico(config: Configuracion) -> str | None:
    """Con un solo correo en GOOGLE_CORREOS, ese es sin duda el dueño de los datos de antes.
    Con varios no se adivina: los datos quedan con su Telegram hasta que lo vincule a su cuenta."""
    return next(iter(config.google_correos)) if len(config.google_correos) == 1 else None


def usuario_para_correo(bd: BaseDeDatos, config: Configuracion, correo: str) -> dict:
    """La cuenta de este correo de Google (ya verificado por Google); se crea la primera vez que entra."""
    usuario = bd.usuario_por_correo(correo)
    if usuario is not None:
        return usuario
    usuario = bd.crear_usuario(correo=correo)
    if correo == _administrador_unico(config):
        adoptar_legado(bd, usuario["id"])
    return bd.usuario(usuario["id"])


def usuario_para_telegram(bd: BaseDeDatos, config: Configuracion, telegram_id: int) -> dict | None:
    """La cuenta vinculada a este Telegram, si tiene."""
    if config.permitidos and telegram_id not in config.permitidos:
        return None
    usuario = bd.usuario_por_telegram(telegram_id)
    if usuario is not None:
        return usuario
    if bd.ajuste("legado") is None and bd.ajuste("dueno") == str(telegram_id):
        # El dueño de cuando había uno solo sigue usando el bot con sus datos de siempre.
        correo = _administrador_unico(config)
        usuario = (bd.usuario_por_correo(correo) if correo else None) or bd.crear_usuario(correo=correo)
        adoptar_legado(bd, usuario["id"])
        return bd.usuario(usuario["id"])
    if not config.google_listo and not bd.hay_usuarios() and bd.ajuste("dueno") is None:
        # Sin inicio de sesión web (la app en tu computadora): el primero que escribe es el dueño.
        # Solo si el bot nunca tuvo dueño: si no, alguien podría quedarse con los datos de antes.
        usuario = bd.crear_usuario(telegram_id=telegram_id)
        adoptar_legado(bd, usuario["id"])
        return bd.usuario(usuario["id"])
    return None


def vincular_telegram(bd: BaseDeDatos, usuario: dict, telegram_id: int) -> str:
    """Vincula el Telegram a la cuenta. Si ese Telegram ya tenía una cuenta sin correo (la del
    dueño de antes, o la de tu computadora), sus registros se suman a esta.
    Devuelve «vinculado», «fusionado» u «ocupado» (ya es de otra cuenta con su propio correo)."""
    otro = bd.usuario_por_telegram(telegram_id)
    if otro and otro["id"] != usuario["id"]:
        if otro["correo"]:
            return "ocupado"
        bd.fusionar_cuentas(otro["id"], usuario["id"])
        bd.vincular_telegram(usuario["id"], telegram_id)
        return "fusionado"
    bd.vincular_telegram(usuario["id"], telegram_id)
    return "vinculado"
