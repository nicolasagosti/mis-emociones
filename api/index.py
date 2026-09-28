"""Función de Vercel: atiende /api/*, /entrar y /salir (vercel.json las redirige aquí).

Los archivos de public/ (la página, el CSS y el JS) los sirve Vercel directamente.
Vercel reconoce la función leyendo este archivo sin ejecutarlo: `handler` tiene que
estar definida con `class handler(...)` a nivel del módulo.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from emociones.config import desde_entorno  # noqa: E402
from emociones.web import Panel  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


class handler(Panel):
    config = desde_entorno()
