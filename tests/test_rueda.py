import re
import unittest

from emociones import rueda
from emociones.rueda import interpretar


def ids(texto, **kwargs):
    return [c.ids for c in interpretar(texto, **kwargs).emociones]


class TestRueda(unittest.TestCase):
    def test_estructura_como_la_imagen(self):
        self.assertEqual([c["id"] for c in rueda.CATEGORIAS],
                         ["enojo", "miedo", "felicidad", "calma", "fuerza", "tristeza"])
        for categoria in rueda.CATEGORIAS:
            self.assertEqual(len(categoria["ramas"]), 6, categoria["id"])
            for color in categoria["colores"]:
                self.assertRegex(color, r"^#[0-9A-F]{6}$")
        # 6 centros + 72 palabras, menos las 3 repetidas dentro de su misma categoría.
        self.assertEqual(len(rueda.EMOCIONES), 75)

    def test_camino_y_color(self):
        self.assertEqual(rueda.camino("enojo/frustrado"), ["Enojo", "Molesto", "Frustrado"])
        self.assertEqual(rueda.camino("tristeza"), ["Tristeza"])
        self.assertEqual(rueda.color("enojo"), rueda.CATEGORIA["enojo"]["colores"][0])
        self.assertEqual(rueda.color("miedo/sin-valor"), rueda.CATEGORIA["miedo"]["colores"][2])

    def test_formato_emociones_y_causa(self):
        r = interpretar("Frustrado, ansioso: mi jefe cambió la fecha de entrega")
        self.assertEqual([c.ids for c in r.emociones], [("enojo/frustrado",), ("miedo/ansioso",)])
        self.assertEqual(r.causa, "Mi jefe cambió la fecha de entrega")
        self.assertTrue(r.explicito)

    def test_separadores(self):
        for texto in ("triste - perdí el bus", "triste porque perdí el bus", "triste\nperdí el bus"):
            r = interpretar(texto)
            self.assertEqual([c.ids for c in r.emociones], [("tristeza",)], texto)
            self.assertEqual(r.causa, "Perdí el bus", texto)

    def test_femenino_plural_tildes_y_sinonimos(self):
        self.assertEqual(ids("frustrada y ansiosas"), [("enojo/frustrado",), ("miedo/ansioso",)])
        self.assertEqual(ids("jugueton"), [("felicidad/jugueton",)])
        self.assertEqual(ids("me siento sin valor"), [("miedo/sin-valor",)])
        self.assertEqual(ids("rabia"), [("enojo/furioso",)])
        self.assertEqual(ids("contenta"), [("felicidad/contenido",)])
        self.assertEqual(ids("estrés"), [("enojo/estresado",)])

    def test_sin_causa_la_deja_vacia(self):
        r = interpretar("me siento muy frustrado")
        self.assertEqual([c.ids for c in r.emociones], [("enojo/frustrado",)])
        self.assertIsNone(r.causa)

    def test_texto_libre(self):
        r = interpretar("Hoy me sentí triste y sola en la fiesta")
        self.assertEqual([c.ids for c in r.emociones], [("tristeza",), ("tristeza/solitario",)])
        self.assertEqual(r.causa, "Hoy me sentí triste y sola en la fiesta")
        self.assertEqual(ids("Me dio miedo la entrevista"), [("miedo",)])

    def test_palabras_comunes_no_cuentan_sin_contexto(self):
        self.assertEqual(ids("Solo quiero dormir un rato largo"), [])
        self.assertEqual(ids("Seguro que mañana llueve todo el día"), [])

    def test_negaciones(self):
        self.assertEqual(ids("No estoy triste, estoy tranquila hoy con todo"), [("calma/tranquilo",)])

    def test_errores_de_tipeo(self):
        self.assertEqual(ids("frustardo"), [("enojo/frustrado",)])

    def test_palabra_desconocida(self):
        r = interpretar("Agotado: mucho trabajo")
        self.assertEqual(r.emociones, [])
        self.assertEqual(r.desconocidas, ["Agotado"])
        self.assertEqual(r.causa, "Mucho trabajo")

    def test_palabra_en_dos_categorias(self):
        self.assertEqual(ids("agradecido"), [("calma/agradecido", "fuerza/agradecido")])

    def test_palabras_aprendidas(self):
        aprendidas = {"agotado": "tristeza/deprimido", "agradecido": "fuerza/agradecido"}
        self.assertEqual(ids("agotada y agradecido", aprendidas=aprendidas),
                         [("tristeza/deprimido",), ("fuerza/agradecido",)])

    def test_sin_emociones(self):
        r = interpretar("Hoy: me peleé con mi hermano")
        self.assertEqual((r.emociones, r.desconocidas), ([], []))
        self.assertEqual(r.causa, "Hoy: me peleé con mi hermano")

    def test_palabras_incluidas_por_emocion(self):
        emociones = rueda.como_json()["emociones"]
        self.assertEqual(emociones["enojo/furioso"]["palabras"][0], "furioso")
        self.assertIn("rabia", emociones["enojo/furioso"]["palabras"])
        self.assertIn("gratitud", emociones["calma/agradecido"]["palabras"])
        self.assertIn("gratitud", emociones["fuerza/agradecido"]["palabras"])
        self.assertIn("triste", emociones["tristeza"]["palabras"])
        # Se muestran con tilde, empezando por el nombre de la emoción.
        self.assertEqual(emociones["felicidad/jugueton"]["palabras"][:2], ["juguetón", "divertido"])
        self.assertIn("frustración", emociones["enojo/frustrado"]["palabras"])
        for emocion_id, datos in emociones.items():
            self.assertEqual(len(datos["palabras"]), len(set(datos["palabras"])), emocion_id)

    def test_sinonimos_con_tilde_se_entienden_igual(self):
        self.assertEqual(ids("frustración y pánico"), [("enojo/frustrado",), ("miedo",)])
        self.assertEqual(ids("frustracion y panico"), [("enojo/frustrado",), ("miedo",)])
        self.assertEqual(ids("vergüenza"), [("tristeza/avergonzado",)])

    def test_palabra_valida(self):
        self.assertEqual(rueda.palabra_valida("  Agotada "), "agotada")
        self.assertEqual(rueda.palabra_valida("Sin Ganas"), "sin ganas")
        for mala in ("", "123", "!!!", "una dos tres cuatro", "x" * 41):
            self.assertIsNone(rueda.palabra_valida(mala), mala)

    def test_significado(self):
        self.assertEqual(rueda.significado("rabia"), ("enojo/furioso",))
        self.assertEqual(rueda.significado("rabia", {"rabia": "enojo/molesto"}), ("enojo/molesto",))
        self.assertEqual(rueda.significado("agradecido"), ("calma/agradecido", "fuerza/agradecido"))
        self.assertEqual(rueda.significado("zapato"), ())

    def test_saludos(self):
        self.assertTrue(rueda.es_saludo("Hola!"))
        self.assertFalse(rueda.es_saludo("hola, estoy triste"))

    def test_json_para_el_panel(self):
        datos = rueda.como_json()
        self.assertEqual(len(datos["categorias"]), 6)
        for categoria in datos["categorias"]:
            for rama in categoria["ramas"]:
                self.assertIn(rama["medio"]["id"], datos["emociones"])
                self.assertIn(rama["exterior"]["id"], datos["emociones"])
        # Los ids caben en el callback_data de Telegram (máx. 64 bytes) con el prefijo más largo.
        for emocion_id in rueda.EMOCIONES:
            self.assertLessEqual(len(f"f:9999999999:e:{emocion_id}".encode()), 64)
            self.assertIsNotNone(re.fullmatch(r"[a-z/-]+", emocion_id))


if __name__ == "__main__":
    unittest.main()
