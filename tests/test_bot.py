import tempfile
import time
import unittest

from emociones import sesion
from emociones.bot import Bot
from tests.utiles import nueva_bd


class APIFalsa:
    """Registra lo que el bot le enviaría a Telegram."""

    def __init__(self):
        self.enviados, self.ediciones, self.teclados, self.avisos, self.llamadas = [], [], [], [], []

    def llamar(self, metodo, espera=30, **parametros):
        self.llamadas.append((metodo, parametros))
        return True

    def enviar(self, chat_id, texto, teclado=None):
        self.enviados.append((texto, teclado))
        return {"message_id": len(self.enviados)}

    def editar(self, chat_id, mensaje_id, texto, teclado=None):
        self.ediciones.append((texto, teclado))

    def editar_teclado(self, chat_id, mensaje_id, teclado):
        self.teclados.append(teclado)

    def responder_boton(self, callback_id, texto=None):
        self.avisos.append(texto)


def botones(teclado):
    return [boton["callback_data"] for fila in teclado or [] for boton in fila]


class TestBot(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.bd = nueva_bd(self.carpeta.name)
        self.api = APIFalsa()
        self.bot = Bot(self.api, self.bd, url_panel="https://emociones.example", clave="123:token")

    def tearDown(self):
        self.carpeta.cleanup()

    def escribir(self, texto, usuario=7):
        self.bot.procesar({"update_id": 1, "message": {
            "message_id": 1, "date": int(time.time()), "text": texto,
            "chat": {"id": usuario, "type": "private"}, "from": {"id": usuario},
        }})

    def tocar(self, datos, usuario=7):
        self.bot.procesar({"update_id": 2, "callback_query": {
            "id": "x", "data": datos, "from": {"id": usuario},
            "message": {"message_id": 1, "chat": {"id": usuario}},
        }})

    def registros(self):
        return self.bd.listar_registros()

    def test_registra_emociones_y_causa(self):
        self.escribir("Frustrado, ansioso: mi jefe cambió la fecha de entrega")
        [registro] = self.registros()
        self.assertEqual([e["emocion"] for e in registro["emociones"]], ["enojo/frustrado", "miedo/ansioso"])
        self.assertEqual(registro["causa"], "Mi jefe cambió la fecha de entrega")
        texto, _ = self.api.enviados[-1]
        self.assertIn("<b>Enojo</b> › Molesto › Frustrado", texto)
        self.assertIn("<b>Miedo</b> › Ansioso", texto)

    def test_pregunta_la_causa_y_la_guarda(self):
        self.escribir("triste")
        texto, teclado = self.api.enviados[-1]
        self.assertIn("¿Qué lo causó?", texto)
        self.assertTrue(any(d.endswith(":o") for d in botones(teclado)))
        self.escribir("discutí con mi hermana")
        [registro] = self.registros()
        self.assertEqual(registro["causa"], "Discutí con mi hermana")

    def test_un_saludo_no_se_toma_como_causa(self):
        self.escribir("triste")
        self.escribir("gracias")
        self.escribir("se murió mi planta")
        [registro] = self.registros()
        self.assertEqual(registro["causa"], "Se murió mi planta")

    def test_la_espera_de_la_causa_vence(self):
        self.escribir("triste")
        self.bd.esperar_causa(7, self.registros()[0]["id"], vence=0)
        self.escribir("se murió mi planta")
        self.assertEqual(len(self.registros()), 2)

    def test_omitir_la_causa(self):
        self.escribir("triste")
        self.tocar(f'r:{self.registros()[0]["id"]}:o')
        self.escribir("se murió mi planta")
        self.assertEqual(len(self.registros()), 2)

    def test_panel_manda_un_enlace_firmado(self):
        self.escribir("hola")  # queda como dueño
        self.escribir("/panel")
        _, teclado = self.api.enviados[-1]
        enlace = teclado[0][0]["url"]
        self.assertTrue(enlace.startswith("https://emociones.example/entrar?t="))
        firma = enlace.split("t=", 1)[1]
        self.assertEqual(sesion.verificar("123:token", "entrar", firma), 7)
        self.assertIsNone(sesion.verificar("123:token", "sesion", firma))

    def test_un_registro_completo_no_se_toma_como_causa(self):
        self.escribir("triste")
        self.escribir("ansioso: mañana tengo examen")
        self.assertEqual(len(self.registros()), 2)

    def test_palabra_desconocida_se_clasifica_y_se_aprende(self):
        self.escribir("agotado: mucho trabajo")
        [registro] = self.registros()
        [fila] = registro["emociones"]
        self.assertIsNone(fila["emocion"])
        texto, teclado = self.api.enviados[-1]
        self.assertIn("No encontré «agotado»", texto)
        self.assertIn(f'f:{fila["id"]}:c:tristeza', botones(teclado))

        self.tocar(f'f:{fila["id"]}:c:tristeza')
        self.assertIn(f'f:{fila["id"]}:e:tristeza/deprimido', botones(self.api.teclados[-1]))
        self.tocar(f'f:{fila["id"]}:e:tristeza/deprimido')
        self.assertEqual(self.bd.obtener_fila(fila["id"])["emocion"], "tristeza/deprimido")

        self.escribir("agotada: otra vez mucho trabajo")
        self.assertEqual(self.registros()[0]["emociones"][0]["emocion"], "tristeza/deprimido")

    def test_palabra_en_dos_categorias(self):
        self.escribir("agradecido: mi amiga me ayudó con la mudanza")
        [fila] = self.registros()[0]["emociones"]
        _, teclado = self.api.enviados[-1]
        self.assertIn(f'f:{fila["id"]}:e:fuerza/agradecido', botones(teclado))
        self.tocar(f'f:{fila["id"]}:e:fuerza/agradecido')
        self.escribir("agradecido: terminé el proyecto")
        self.assertEqual(self.registros()[0]["emociones"][0]["emocion"], "fuerza/agradecido")

    def test_sin_emociones_ofrece_elegir_en_la_rueda(self):
        self.escribir("Hoy me peleé con mi hermano por la herencia")
        [registro] = self.registros()
        self.assertEqual(registro["emociones"], [])
        texto, teclado = self.api.enviados[-1]
        self.assertIn("¿Qué sentiste?", texto)
        self.tocar(f'r:{registro["id"]}:c:enojo')
        self.tocar(f'r:{registro["id"]}:e:enojo/frustrado')
        [fila] = self.bd.obtener_registro(registro["id"])["emociones"]
        self.assertEqual(fila["emocion"], "enojo/frustrado")

    def test_cancelar_sin_emociones_borra_el_registro(self):
        self.escribir("Hoy me peleé con mi hermano por la herencia")
        self.tocar(f'r:{self.registros()[0]["id"]}:x')
        self.assertEqual(self.registros(), [])

    def test_descartar_la_unica_palabra_borra_el_registro(self):
        self.escribir("jaja")
        fila = self.registros()[0]["emociones"][0]
        self.tocar(f'f:{fila["id"]}:x')
        self.assertEqual(self.registros(), [])

    def test_saludo_no_crea_registros(self):
        self.escribir("hola")
        self.assertEqual(self.registros(), [])
        self.assertIn("Cuéntame", self.api.enviados[-1][0])

    def test_el_bot_es_de_quien_le_escribe_primero(self):
        self.escribir("triste: llueve")
        self.escribir("feliz: gané", usuario=99)
        self.assertEqual(len(self.registros()), 1)
        self.assertIn("privado", self.api.enviados[-1][0])

    def test_usuarios_permitidos(self):
        bot = Bot(self.api, self.bd, permitidos={99})
        bot.procesar({"update_id": 1, "message": {
            "message_id": 1, "date": int(time.time()), "text": "triste: llueve",
            "chat": {"id": 7, "type": "private"}, "from": {"id": 7},
        }})
        self.assertEqual(self.registros(), [])

    def test_deshacer(self):
        self.escribir("triste: llueve")
        self.escribir("/deshacer")
        _, teclado = self.api.enviados[-1]
        self.assertIn(f'r:{self.registros()[0]["id"]}:D', botones(teclado))
        self.tocar(botones(teclado)[0])
        self.assertEqual(self.registros(), [])

    def test_boton_de_registro_borrado(self):
        self.tocar("r:12345:m")
        self.assertEqual(self.api.avisos[-1], "Ese registro ya no existe.")

    def test_botones_invalidos_se_ignoran(self):
        self.escribir("triste: llueve")
        registro_id = self.registros()[0]["id"]
        for datos in ("", "r", "r:abc:m", f"r:{registro_id}:e:no/existe", f"z:{registro_id}:m"):
            self.tocar(datos)
        self.assertEqual(len(self.registros()[0]["emociones"]), 1)

    def test_resumenes(self):
        self.escribir("frustrado: tráfico")
        self.escribir("frustrado, ansioso: examen")
        self.escribir("/semana")
        texto, _ = self.api.enviados[-1]
        self.assertIn("3 emociones en 2 registros", texto)
        self.assertIn("Frustrado (2)", texto)
        self.escribir("/rueda")
        self.assertIn("Sin valor", self.api.enviados[-1][0])


if __name__ == "__main__":
    unittest.main()
