import tempfile
import time
import unittest

from emociones import sesion
from emociones.bot import Bot
from emociones.config import Configuracion
from tests.utiles import nueva_bd

CON_GOOGLE = dict(url_publica="https://emociones.example", token="123:token", google_id="cliente",
                  google_secreto="secreto", google_correos={"yo@gmail.com"})


class APIFalsa:
    """Registra lo que el bot le enviaría a Telegram."""

    def __init__(self):
        self.enviados, self.ediciones, self.teclados, self.avisos, self.llamadas = [], [], [], [], []

    def llamar(self, metodo, espera=30, **parametros):
        self.llamadas.append((metodo, parametros))
        return {"username": "emociones_bot"} if metodo == "getMe" else True

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


class Ayudantes:
    """Arma el bot y simula mensajes y botones de Telegram."""

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.bd = nueva_bd(self.carpeta.name)
        self.api = APIFalsa()
        self.bot = Bot(self.api, self.bd, Configuracion(url_publica="https://emociones.example", token="123:token"))

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

    def registros(self, telegram_id=7):
        usuario = self.bd.usuario_por_telegram(telegram_id)
        return self.bd.listar_registros(usuario["id"]) if usuario else []


class TestBot(Ayudantes, unittest.TestCase):

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

    def test_usa_los_nombres_de_tu_rueda(self):
        self.escribir("hola")  # queda como dueño
        yo = self.bd.usuario_por_telegram(7)
        self.bd.renombrar(yo["id"], "enojo", "Bronca")
        self.bd.renombrar(yo["id"], "enojo/frustrado", "Bloqueado")
        self.bd.aprender(yo["id"], "bloqueado", "enojo/frustrado")  # la app se la enseña al renombrarla
        self.escribir("bloqueada: el tráfico")
        [registro] = self.registros()
        self.assertEqual(registro["emociones"][0]["emocion"], "enojo/frustrado")
        texto, _ = self.api.enviados[-1]
        self.assertIn("<b>Bronca</b> › Molesto › Bloqueado", texto)
        self.assertNotIn("(bloqueada)", texto)  # es su nombre, en femenino
        self.escribir("/rueda")
        self.assertIn("<b>Bronca</b>", self.api.enviados[-1][0])
        self.assertIn("Bloqueado", self.api.enviados[-1][0])
        self.tocar(f'r:{registro["id"]}:c:enojo')
        textos = [boton["text"] for fila in self.api.teclados[-1] for boton in fila]
        self.assertIn("Bloqueado", textos)
        self.assertIn("Solo bronca", textos)

    def test_panel_manda_un_enlace_firmado(self):
        self.escribir("hola")  # queda como dueño
        self.escribir("/panel")
        _, teclado = self.api.enviados[-1]
        enlace = teclado[0][0]["url"]
        self.assertTrue(enlace.startswith("https://emociones.example/entrar?t="))
        firma = enlace.split("t=", 1)[1]
        self.assertEqual(sesion.verificar("123:token", "entrar", firma), "t:7")
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
        bot = Bot(self.api, self.bd, Configuracion(permitidos={99}))
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

    def test_ensenar_cambiar_y_olvidar_palabras(self):
        self.escribir("/palabras")
        self.assertIn("Todavía no me enseñaste palabras", self.api.enviados[-1][0])
        # «rabia» viene incluida como Furioso; la cambio a Molesto.
        self.escribir("/palabra Rabia")
        texto, teclado = self.api.enviados[-1]
        self.assertIn("Hoy la entiendo como", texto)
        self.assertIn("p:0:c:enojo", botones(teclado))
        self.tocar("p:0:c:enojo")
        self.assertIn("p:0:e:enojo/molesto", botones(self.api.teclados[-1]))
        self.tocar("p:0:e:enojo/molesto")
        self.assertIn("Desde ahora la entiendo así", self.api.ediciones[-1][0])
        self.escribir("rabia: el tráfico")
        self.assertEqual(self.registros()[0]["emociones"][0]["emocion"], "enojo/molesto")
        self.escribir("/palabras")
        self.assertIn("rabia →", self.api.enviados[-1][0])
        # Al olvidarla, vuelve a lo que trae el bot.
        self.escribir("/olvidar rabia")
        self.assertIn("olvidé «rabia»", self.api.enviados[-1][0])
        self.escribir("rabia: otra vez el tráfico")
        self.assertEqual(self.registros()[0]["emociones"][0]["emocion"], "enojo/furioso")

    def test_palabras_mal_escritas(self):
        self.escribir("/palabra")
        self.assertIn("/palabra agotado", self.api.enviados[-1][0])
        self.escribir("/olvidar agotado")
        self.assertIn("no estaba entre tus palabras", self.api.enviados[-1][0])
        self.tocar("p:0:e:tristeza")  # botón sin haber usado /palabra antes
        self.assertIn("/palabra", self.api.avisos[-1])

    def test_resumenes(self):
        self.escribir("frustrado: tráfico")
        self.escribir("frustrado, ansioso: examen")
        self.escribir("/semana")
        texto, _ = self.api.enviados[-1]
        self.assertIn("3 emociones en 2 registros", texto)
        self.assertIn("Frustrado (2)", texto)
        self.escribir("/rueda")
        self.assertIn("Sin valor", self.api.enviados[-1][0])



class TestBotConCuentas(Ayudantes, unittest.TestCase):
    """Con inicio de sesión en la web: cada Telegram se vincula con una cuenta desde la app."""

    def setUp(self):
        super().setUp()
        self.bot = Bot(self.api, self.bd, Configuracion(**CON_GOOGLE))
        self.yo = self.bd.crear_usuario(correo="yo@gmail.com")

    def vincular(self, usuario, telegram_id=7):
        self.escribir(f"/start {sesion.firmar_vinculo('123:token', usuario['id'], 600)}", telegram_id)

    def test_sin_vincular_explica_como_hacerlo(self):
        self.escribir("triste: llueve")
        self.assertIn("Vincular mi Telegram", self.api.enviados[-1][0])
        self.assertEqual(self.registros(), [])

    def test_vincular_desde_la_app(self):
        self.vincular(self.yo)
        self.assertIn("vinculado a <b>yo@gmail.com</b>", self.api.enviados[-1][0])
        self.escribir("triste: llueve")
        [registro] = self.bd.listar_registros(self.yo["id"])
        self.assertEqual(registro["causa"], "Llueve")

    def test_codigo_vencido_o_falso(self):
        for codigo in (sesion.firmar_vinculo("123:token", self.yo["id"], -1), "1_2_falso", "basura"):
            self.escribir(f"/start {codigo}")
            self.assertIn("venció o no es válido", self.api.enviados[-1][0])
        self.assertIsNone(self.bd.usuario_por_telegram(7))

    def test_un_telegram_no_se_vincula_a_dos_cuentas(self):
        otra = self.bd.crear_usuario(correo="otra@gmail.com")
        self.vincular(self.yo)
        self.vincular(otra)
        self.assertIn("ya está vinculado a otra cuenta", self.api.enviados[-1][0])
        self.assertEqual(self.bd.usuario_por_telegram(7)["id"], self.yo["id"])

    def test_vincular_suma_los_registros_de_una_cuenta_sin_correo(self):
        vieja = self.bd.crear_usuario(telegram_id=7)
        self.bd.crear_registro(vieja["id"], 1000, "Llueve", None, 7, [("triste", "tristeza")])
        self.vincular(self.yo)
        self.assertIn("se sumaron", self.api.enviados[-1][0])
        self.assertEqual([r["causa"] for r in self.bd.listar_registros(self.yo["id"])], ["Llueve"])

    def test_cada_persona_tiene_su_diario(self):
        otra = self.bd.crear_usuario(correo="otra@gmail.com")
        self.vincular(self.yo, 7)
        self.vincular(otra, 8)
        self.escribir("triste: llueve", 7)
        self.escribir("feliz: gané el partido", 8)
        self.assertEqual([r["causa"] for r in self.bd.listar_registros(self.yo["id"])], ["Llueve"])
        self.assertEqual([r["causa"] for r in self.bd.listar_registros(otra["id"])], ["Gané el partido"])
        self.escribir("/hoy", 8)
        self.assertNotIn("Llueve", self.api.enviados[-1][0])
        # Los botones de un registro ajeno no hacen nada.
        registro_ajeno = self.bd.listar_registros(self.yo["id"])[0]["id"]
        self.tocar(f"r:{registro_ajeno}:D", 8)
        self.assertEqual(self.api.avisos[-1], "Ese registro ya no existe.")
        self.assertIsNotNone(self.bd.obtener_registro(registro_ajeno))

    def test_palabras_aprendidas_por_persona(self):
        otra = self.bd.crear_usuario(correo="otra@gmail.com")
        self.vincular(self.yo, 7)
        self.vincular(otra, 8)
        self.escribir("agotado: mucho trabajo", 7)
        fila = self.bd.listar_registros(self.yo["id"])[0]["emociones"][0]
        self.tocar(f'f:{fila["id"]}:e:tristeza/deprimido', 7)
        self.assertEqual(self.bd.vocabulario(self.yo["id"]), {"agotado": "tristeza/deprimido"})
        self.assertEqual(self.bd.vocabulario(otra["id"]), {})


if __name__ == "__main__":
    unittest.main()
