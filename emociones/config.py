"""Configuración leída de variables de entorno: el archivo .env en tu computadora,
o Settings → Environment Variables en Vercel."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import tzinfo
from pathlib import Path
from typing import Callable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .telegram import Telegram

RAIZ = Path(__file__).resolve().parent.parent
LOCALES = {"localhost", "127.0.0.1", "::1"}

log = logging.getLogger("emociones")


@dataclass
class Configuracion:
    token: str = ""
    permitidos: set[int] = field(default_factory=set)
    base_de_datos: str | None = None          # ruta de SQLite o URL postgres://…
    url_publica: str = "http://localhost:8000"  # dirección del panel (enlaces de /panel y webhook)
    solo_local: bool = True                   # el panel solo se abre desde esta computadora
    en_vercel: bool = False
    produccion: bool = False                  # despliegue de producción en Vercel
    zona: tzinfo | None = None                # None = la hora de la computadora
    api: Callable[[str], Telegram] = Telegram

    @property
    def requiere_sesion(self) -> bool:
        """Fuera de tu computadora, el panel pide entrar con el enlace de /panel."""
        return not self.solo_local


def _zona(nombre: str) -> tzinfo | None:
    if not nombre:
        return None
    try:
        return ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("ZONA_HORARIA=%s no existe; uso la hora del servidor.", nombre)
        return None


def desde_entorno(entorno: Mapping[str, str] | None = None) -> Configuracion:
    """Lanza ValueError si PUERTO o TELEGRAM_USUARIOS no son números."""
    e = os.environ if entorno is None else entorno
    en_vercel = bool(e.get("VERCEL"))
    host = e.get("HOST", "127.0.0.1").strip()
    puerto = int(e.get("PUERTO", "8000"))
    permitidos = {int(x) for x in e.get("TELEGRAM_USUARIOS", "").replace(" ", "").split(",") if x}

    dominio = e.get("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
    if e.get("URL_PANEL"):
        url_publica = e["URL_PANEL"].strip().rstrip("/")
    elif en_vercel and dominio:
        url_publica = f"https://{dominio}"
    else:
        url_publica = f"http://localhost:{puerto}"

    # Neon y Supabase (desde Vercel → Storage) definen DATABASE_URL o POSTGRES_URL.
    base = e.get("DATABASE_URL") or e.get("POSTGRES_URL") or e.get("BASE_DE_DATOS")
    if not base and not en_vercel:
        base = str(RAIZ / "datos" / "emociones.db")

    return Configuracion(
        token=e.get("TELEGRAM_TOKEN", "").strip(),
        permitidos=permitidos,
        base_de_datos=base or None,
        url_publica=url_publica,
        solo_local=not en_vercel and host in LOCALES,
        en_vercel=en_vercel,
        produccion=en_vercel and e.get("VERCEL_ENV") == "production",
        zona=_zona(e.get("ZONA_HORARIA", "").strip()),
    )
