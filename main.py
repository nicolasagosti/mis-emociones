#!/usr/bin/env python3
"""Mis Emociones en tu computadora: bot de Telegram + panel web con la rueda de los sentimientos.

    python3 main.py          # bot + panel (lee la configuración de .env)
    python3 main.py --demo   # solo el panel, con datos de ejemplo (no toca tus datos)

En Vercel no se usa este archivo: allí atiende api/index.py.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import signal
import sys
import threading

from emociones import demo
from emociones.bd import BaseDeDatos
from emociones.bot import Bot
from emociones.config import RAIZ, desde_entorno
from emociones.web import crear_servidor

log = logging.getLogger("emociones")


def cargar_env(ruta) -> None:
    """Lee un archivo .env sencillo (CLAVE=valor). Las variables ya definidas tienen prioridad."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip("\"'"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Diario de emociones con bot de Telegram y panel web.")
    parser.add_argument("--demo", action="store_true", help="abrir solo el panel con datos de ejemplo")
    args = parser.parse_args()

    cargar_env(RAIZ / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")

    try:
        config = desde_entorno()
        host = os.environ.get("HOST", "127.0.0.1").strip()
        puerto = int(os.environ.get("PUERTO", "8000"))
    except ValueError:
        sys.exit("PUERTO y TELEGRAM_USUARIOS deben ser números (revisa el archivo .env).")

    if args.demo:
        ruta_demo = RAIZ / "datos" / "demo.db"
        ruta_demo.unlink(missing_ok=True)
        demo.sembrar(BaseDeDatos(ruta_demo))
        config = dataclasses.replace(config, base_de_datos=str(ruta_demo), token="")
    bd = BaseDeDatos(config.base_de_datos)

    try:
        servidor = crear_servidor(config, host, puerto)
    except OSError as error:
        sys.exit(f"No pude abrir el panel en {host}:{puerto} ({error}). Prueba otro PUERTO en .env.")

    detener = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: detener.set())
    hilos = [threading.Thread(target=servidor.serve_forever, name="panel", daemon=True)]

    if args.demo:
        log.info("Modo demo: datos de ejemplo, sin bot de Telegram.")
    elif config.token:
        bot = Bot(config.api(config.token), bd, config)
        hilos.append(threading.Thread(target=bot.ejecutar, args=(detener,), name="bot", daemon=True))
    else:
        log.warning("Falta TELEGRAM_TOKEN en .env: abro solo el panel. El README explica cómo crear el bot.")

    for hilo in hilos:
        hilo.start()
    log.info("Panel: %s   (Ctrl+C para salir)", config.url_publica)
    if config.requiere_sesion:
        log.info("El panel se ve desde otros dispositivos: para entrar, envía /panel a tu bot.")

    try:
        detener.wait()
    except KeyboardInterrupt:
        pass
    finally:
        detener.set()
        servidor.shutdown()
        log.info("Hasta luego 👋")


if __name__ == "__main__":
    main()
