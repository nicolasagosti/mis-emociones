import tempfile
import threading
import unittest

from emociones.bd import VERSION_ESQUEMA
from tests.utiles import nueva_bd


class TestPreparacion(unittest.TestCase):
    def test_varias_instancias_preparan_la_base_a_la_vez(self):
        """Como al publicar en Vercel: varias instancias revisan el esquema al mismo tiempo."""
        with tempfile.TemporaryDirectory() as carpeta:
            bd = nueva_bd(carpeta)
            with bd._conexion() as con:  # que todas crean que hay que actualizar
                con.execute("DELETE FROM ajustes WHERE clave = 'esquema'")
            barrera = threading.Barrier(4)
            errores = []

            def preparar():
                barrera.wait()
                try:
                    bd._preparar()
                except Exception as error:  # noqa: BLE001 — se informa abajo
                    errores.append(error)

            hilos = [threading.Thread(target=preparar) for _ in range(4)]
            for hilo in hilos:
                hilo.start()
            for hilo in hilos:
                hilo.join()
            self.assertEqual(errores, [])
            with bd._conexion() as con:
                self.assertEqual(bd._version_esquema(con), str(VERSION_ESQUEMA))

    def test_si_esta_al_dia_no_toca_nada(self):
        with tempfile.TemporaryDirectory() as carpeta:
            bd = nueva_bd(carpeta)
            yo = bd.crear_usuario(correo="yo@gmail.com")
            bd._preparar()
            self.assertEqual(bd.usuario_por_correo("yo@gmail.com")["id"], yo["id"])


if __name__ == "__main__":
    unittest.main()
