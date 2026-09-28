import os
from pathlib import Path

from emociones.bd import BaseDeDatos

# Con PRUEBAS_POSTGRES_URL=postgresql://… las pruebas usan ese Postgres (lo vacían antes de cada una).
URL_POSTGRES = os.environ.get("PRUEBAS_POSTGRES_URL")


def nueva_bd(carpeta: str) -> BaseDeDatos:
    if not URL_POSTGRES:
        return BaseDeDatos(Path(carpeta) / "prueba.db")
    import psycopg

    with psycopg.connect(URL_POSTGRES, autocommit=True) as con:
        con.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    BaseDeDatos._preparadas.discard(URL_POSTGRES)
    return BaseDeDatos(URL_POSTGRES)
