"""El bot de Telegram: recibe emociones y sus causas, y las acomoda en la rueda."""

from __future__ import annotations

import html
import logging
import threading
import time
from collections import Counter
from datetime import datetime, tzinfo

from . import cuentas, rueda, sesion
from .bd import BaseDeDatos
from .config import Configuracion
from .telegram import ErrorTelegram, Telegram

log = logging.getLogger("emociones.bot")

ESPERA_CAUSA = 30 * 60  # segundos durante los que el próximo mensaje se toma como la causa
DURACION_VINCULO = 10 * 60  # el enlace para vincular Telegram desde la app

COMANDOS = [
    ("hoy", "Lo que registraste hoy"),
    ("semana", "Resumen de los últimos 7 días"),
    ("panel", "Abrir tu panel con la rueda"),
    ("rueda", "Todas las emociones de la rueda"),
    ("deshacer", "Borrar el último registro"),
    ("ayuda", "Cómo usar el bot"),
]


def conectar_webhook(api: Telegram, url: str, token: str) -> None:
    """Le pide a Telegram que avise cada mensaje nuevo a `url` (así funciona en Vercel)."""
    api.llamar("setWebhook", url=url, secret_token=sesion.secreto_webhook(token),
               allowed_updates=["message", "callback_query"])
    api.llamar("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMANDOS])

EJEMPLO = "<code>Frustrado, ansioso: mi jefe cambió la fecha de entrega</code>"


def _boton(texto: str, datos: str) -> dict:
    return {"text": texto, "callback_data": datos}


def _en_filas(botones: list[dict], por_fila: int) -> list[list[dict]]:
    return [botones[i:i + por_fila] for i in range(0, len(botones), por_fila)]


def _teclado_categorias(prefijo: str) -> list[list[dict]]:
    return _en_filas(
        [_boton(f'{c["emoji"]} {c["nombre"]}', f'{prefijo}:c:{c["id"]}') for c in rueda.CATEGORIAS], 3
    )


def _teclado_palabras(prefijo: str, categoria: str) -> list[list[dict]]:
    """Las emociones de una categoría: primero el anillo medio, después el exterior."""
    nombre = rueda.CATEGORIA[categoria]["nombre"]
    emociones = [e for e in rueda.EMOCIONES.values() if e.categoria == categoria and e.anillo != "centro"]
    emociones.sort(key=lambda e: e.anillo != "medio")
    botones = [_boton(e.nombre, f"{prefijo}:e:{e.id}") for e in emociones]
    botones.append(_boton(f"Solo {nombre.lower()}", f"{prefijo}:e:{categoria}"))
    return _en_filas(botones, 3) + [[_boton("⬅️ Volver", f"{prefijo}:v")]]


def _teclado_registro(registro_id: int, esperando_causa: bool = False) -> list[list[dict]]:
    teclado = [[_boton("➕ Otra emoción", f"r:{registro_id}:m"), _boton("🗑 Borrar", f"r:{registro_id}:d")]]
    if esperando_causa:
        teclado.insert(0, [_boton("⏭ Omitir la causa", f"r:{registro_id}:o")])
    return teclado


def _etiqueta(emocion_id: str) -> str:
    """«❤️ Enojo › Molesto › Frustrado»."""
    emocion = rueda.EMOCIONES[emocion_id]
    categoria = rueda.CATEGORIA[emocion.categoria]
    return " › ".join([f'{categoria["emoji"]} <b>{categoria["nombre"]}</b>', *rueda.camino(emocion_id)[1:]])


def _linea_emocion(fila: dict) -> str:
    palabra = html.escape(fila["palabra"])
    if fila["emocion"] not in rueda.EMOCIONES:
        return f"❔ {palabra} <i>(sin clasificar)</i>"
    linea = _etiqueta(fila["emocion"])
    if not rueda.es_forma_de(fila["palabra"], fila["emocion"]):
        linea += f" <i>({palabra})</i>"
    return linea


def _corta(fila: dict) -> str:
    """«❤️ Frustrado», para listados."""
    emocion = rueda.EMOCIONES.get(fila["emocion"] or "")
    if emocion is None:
        return f'❔ {html.escape(fila["palabra"])}'
    return f'{rueda.CATEGORIA[emocion.categoria]["emoji"]} {emocion.nombre}'


def _resumen(registro: dict, titulo: str) -> str:
    lineas = [titulo, ""]
    lineas += [_linea_emocion(f) for f in registro["emociones"]] or ["<i>Sin emociones todavía</i>"]
    if registro["causa"]:
        lineas += ["", f'📝 {html.escape(registro["causa"][:3000])}']
    return "\n".join(lineas)


def _texto_rueda() -> str:
    lineas = ["<b>La rueda de los sentimientos</b> (Gloria Willcox)"]
    for categoria in rueda.CATEGORIAS:
        medio = dict.fromkeys(m for m, _ in categoria["ramas"])
        exterior = dict.fromkeys(e for _, e in categoria["ramas"] if e not in medio)
        lineas += [
            "",
            f'{categoria["emoji"]} <b>{categoria["nombre"]}</b>',
            ", ".join(medio),
            f'<i>{", ".join(exterior)}</i>',
        ]
    return "\n".join(lineas)


class Bot:
    """Un solo bot para todas las cuentas: cada mensaje va al diario de quien lo escribe.

    No guarda estado en memoria entre mensajes: todo vive en la base de datos, así funciona
    igual leyendo mensajes en tu computadora que recibiéndolos por webhook en Vercel.
    """

    def __init__(self, api: Telegram, bd: BaseDeDatos, config: Configuracion):
        self.api = api
        self.bd = bd
        self.config = config
        self.zona: tzinfo | None = config.zona
        self.usuario_id: int | None = None  # la cuenta de quien escribió lo que se está atendiendo
        self.aprendidas: dict[str, str] = {}

    # --- Ciclo principal ---------------------------------------------------------------

    def ejecutar(self, detener: threading.Event) -> None:
        """Pide mensajes nuevos a Telegram (long polling) hasta que `detener` se active."""
        if not self._conectar(detener):
            return
        desplazamiento, pausa = None, 1
        while not detener.is_set():
            try:
                novedades = self.api.llamar(
                    "getUpdates", espera=65, offset=desplazamiento, timeout=50,
                    allowed_updates=["message", "callback_query"],
                )
                pausa = 1
            except (ErrorTelegram, OSError, ValueError) as error:
                if getattr(error, "codigo", None) == 409:
                    log.error("Otro programa está leyendo este bot (¿lo abriste dos veces o tiene un webhook?).")
                else:
                    log.warning("No pude leer mensajes de Telegram (%s). Reintento en %s s.", error, pausa)
                detener.wait(pausa)
                pausa = min(pausa * 2, 60)
                continue
            for novedad in novedades:
                desplazamiento = novedad["update_id"] + 1
                try:
                    self.procesar(novedad)
                except Exception:
                    log.exception("Error al procesar un mensaje")

    def _conectar(self, detener: threading.Event) -> bool:
        pausa = 1
        while not detener.is_set():
            try:
                yo = self.api.llamar("getMe")
                break
            except ErrorTelegram as error:
                if error.codigo in (401, 404):
                    log.error("Telegram rechazó el token: revisa TELEGRAM_TOKEN en el archivo .env.")
                    return False
                log.warning("No pude conectar con Telegram (%s). Reintento en %s s.", error, pausa)
            except (OSError, ValueError) as error:
                log.warning("No pude conectar con Telegram (%s). Reintento en %s s.", error, pausa)
            detener.wait(pausa)
            pausa = min(pausa * 2, 60)
        else:
            return False
        log.info("Bot @%s listo para recibir emociones.", yo.get("username"))
        try:
            self.api.llamar("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMANDOS])
        except ErrorTelegram as error:
            log.warning("No pude registrar el menú de comandos: %s", error)
        return True

    def procesar(self, novedad: dict) -> None:
        if "callback_query" in novedad:
            self._al_tocar_boton(novedad["callback_query"])
        elif "message" in novedad:
            self._al_recibir_mensaje(novedad["message"])

    def _identificar(self, telegram_id: int | None) -> bool:
        """Busca la cuenta vinculada a quien escribe. Sin cuenta no puede usar el bot."""
        usuario = cuentas.usuario_para_telegram(self.bd, self.config, telegram_id) if telegram_id else None
        self.usuario_id = usuario["id"] if usuario else None
        self.aprendidas = self.bd.vocabulario(self.usuario_id) if usuario else {}
        return usuario is not None

    def _es_mio(self, registro: dict | None) -> bool:
        return registro is not None and registro["usuario_id"] == self.usuario_id

    def _como_vincular(self) -> str:
        if not self.config.google_listo:
            return "🔒 Este bot es privado."
        return (
            "👋 Para usar este bot, vincúlalo con tu cuenta:\n"
            f"1. Entra a {html.escape(self.config.url_publica)} con tu cuenta de Google.\n"
            "2. En el menú, entra a <b>Telegram</b> y toca <b>Vincular mi Telegram</b>.\n\n"
            "Si todavía no tienes cuenta, se crea sola la primera vez que entras."
        )

    def _vincular(self, chat_id: int, telegram_id: int, codigo: str) -> None:
        """/start <código>: el enlace «Vincular Telegram» de la app."""
        usuario_id = sesion.verificar_vinculo(self.config.clave_sesion, codigo)
        usuario = self.bd.usuario(usuario_id) if usuario_id else None
        if usuario is None:
            self.api.enviar(chat_id, "Ese enlace para vincular venció o no es válido. "
                                     "Pide uno nuevo en la app, con «Vincular Telegram».")
            return
        if self.config.permitidos and telegram_id not in self.config.permitidos:
            self.api.enviar(chat_id, "🔒 Este bot es privado.")
            return
        resultado = cuentas.vincular_telegram(self.bd, usuario, telegram_id)
        if resultado == "ocupado":
            otro = self.bd.usuario_por_telegram(telegram_id)
            self.api.enviar(chat_id, f'Este Telegram ya está vinculado a otra cuenta ({html.escape(otro["correo"])}). '
                                     "Desvincúlalo desde esa cuenta y vuelve a intentarlo.")
            return
        log.info("Telegram %s vinculado a la cuenta %s (%s).", telegram_id, usuario["id"], resultado)
        sumados = "\nTus registros anteriores se sumaron a esta cuenta." if resultado == "fusionado" else ""
        self.api.enviar(chat_id, f'✅ Listo: este Telegram quedó vinculado a '
                                 f'<b>{html.escape(usuario["correo"] or "tu cuenta")}</b>.{sumados}\n\n{self._ayuda()}')

    # --- Mensajes ----------------------------------------------------------------------

    def _al_recibir_mensaje(self, mensaje: dict) -> None:
        chat_id = mensaje["chat"]["id"]
        if mensaje["chat"].get("type") != "private":
            return
        telegram_id = mensaje.get("from", {}).get("id")
        texto = (mensaje.get("text") or "").strip()
        if texto.startswith("/start ") and telegram_id:
            self._vincular(chat_id, telegram_id, texto.split(maxsplit=1)[1])
            return
        if not self._identificar(telegram_id):
            self.api.enviar(chat_id, self._como_vincular())
            return
        if not texto:
            self.api.enviar(chat_id, "Por ahora solo entiendo mensajes de texto ✍️")
            return
        if texto.startswith("/"):
            self._comando(chat_id, mensaje["from"]["id"], texto)
            return

        registro_id = self.bd.espera(chat_id)
        if registro_id and not rueda.es_saludo(texto):
            self.bd.quitar_espera(chat_id)
            if self._guardar_causa(chat_id, registro_id, texto):
                return
        self._registrar(chat_id, texto, mensaje.get("date") or int(time.time()))

    def _guardar_causa(self, chat_id: int, registro_id: int, texto: str) -> bool:
        # Un mensaje con el formato «emoción: causa» es un registro nuevo, no la causa del anterior.
        interpretacion = rueda.interpretar(texto, self.aprendidas)
        if interpretacion.explicito and interpretacion.emociones:
            return False
        if not self._es_mio(self.bd.obtener_registro(registro_id)):
            return False
        self.bd.poner_causa(registro_id, texto[:1].upper() + texto[1:])
        registro = self.bd.obtener_registro(registro_id)
        self.api.enviar(chat_id, _resumen(registro, "📝 <b>Causa guardada</b>"), _teclado_registro(registro_id))
        return True

    def _registrar(self, chat_id: int, texto: str, fecha: int) -> None:
        if rueda.es_saludo(texto):
            self.api.enviar(chat_id, f"¡Hola! 👋 Cuéntame cómo te sientes y qué lo causó. Por ejemplo:\n{EJEMPLO}")
            return

        interpretacion = rueda.interpretar(texto, self.aprendidas)
        # Las palabras ambiguas o desconocidas se guardan sin clasificar y se preguntan aparte.
        filas = [(c.palabra, c.ids[0] if len(c.ids) == 1 else None) for c in interpretacion.emociones]
        filas += [(palabra, None) for palabra in interpretacion.desconocidas]
        registro_id, fila_ids = self.bd.crear_registro(self.usuario_id, fecha, interpretacion.causa, texto,
                                                       chat_id, filas)

        if not filas:
            self.api.enviar(
                chat_id,
                "No reconocí ninguna emoción de la rueda. <b>¿Qué sentiste?</b>\n\n"
                f"📝 {html.escape((interpretacion.causa or texto)[:3000])}",
                self._teclado_elegir(registro_id, vacio=True),
            )
            return

        respuesta = _resumen(self.bd.obtener_registro(registro_id), "✅ <b>Guardado</b>")
        falta_causa = interpretacion.causa is None
        if falta_causa:
            respuesta += "\n\n<b>¿Qué lo causó?</b> Cuéntamelo en tu próximo mensaje."
            self.bd.esperar_causa(chat_id, registro_id, int(time.time()) + ESPERA_CAUSA)
        self.api.enviar(chat_id, respuesta, _teclado_registro(registro_id, esperando_causa=falta_causa))

        for i, fila_id in enumerate(fila_ids):
            if filas[i][1] is None:
                opciones = interpretacion.emociones[i].ids if i < len(interpretacion.emociones) else ()
                self._preguntar_fila(chat_id, fila_id, filas[i][0], opciones)

    def _preguntar_fila(self, chat_id: int, fila_id: int, palabra: str, opciones: tuple[str, ...]) -> None:
        palabra_html = html.escape(palabra)
        if opciones:
            texto = f"«{palabra_html}» está en dos lugares de la rueda. ¿Cuál se acerca más a lo que sentiste?"
        else:
            texto = f"No encontré «{palabra_html}» en la rueda. ¿A qué emoción se parece?"
        self.api.enviar(chat_id, texto, self._teclado_fila(fila_id, palabra, opciones))

    def _teclado_fila(self, fila_id: int, palabra: str, opciones: tuple[str, ...] = ()) -> list[list[dict]]:
        prefijo = f"f:{fila_id}"
        ids = list(opciones) or rueda.sugerencias(palabra, self.aprendidas)
        sugeridas = [[_boton(self._boton_emocion(i), f"{prefijo}:e:{i}")] for i in ids]
        extra = [] if opciones else _teclado_categorias(prefijo)
        return sugeridas + extra + [[_boton("✖️ Descartar", f"{prefijo}:x")]]

    def _teclado_elegir(self, registro_id: int, vacio: bool) -> list[list[dict]]:
        salida = _boton("✖️ Cancelar", f"r:{registro_id}:x") if vacio else _boton("⬅️ Volver", f"r:{registro_id}:k")
        return _teclado_categorias(f"r:{registro_id}") + [[salida]]

    @staticmethod
    def _boton_emocion(emocion_id: str) -> str:
        emocion = rueda.EMOCIONES[emocion_id]
        return f'{rueda.CATEGORIA[emocion.categoria]["emoji"]} ' + " › ".join(rueda.camino(emocion_id))

    # --- Botones -----------------------------------------------------------------------

    def _al_tocar_boton(self, boton: dict) -> None:
        if "message" not in boton or not self._identificar(boton.get("from", {}).get("id")):
            self.api.responder_boton(boton["id"], "Vincula tu cuenta para usar el bot.")
            return
        partes = boton.get("data", "").split(":")
        chat_id = boton["message"]["chat"]["id"]
        mensaje_id = boton["message"]["message_id"]
        try:
            tipo, ident, accion = partes[0], int(partes[1]), partes[2]
        except (IndexError, ValueError):
            self.api.responder_boton(boton["id"])
            return
        valor = partes[3] if len(partes) > 3 else ""
        invalido = (
            tipo not in ("f", "r")
            or (accion == "c" and valor not in rueda.CATEGORIA)
            or (accion == "e" and valor not in rueda.EMOCIONES)
        )
        if invalido:
            self.api.responder_boton(boton["id"])
            return

        manejar = self._boton_fila if tipo == "f" else self._boton_registro
        aviso = manejar(chat_id, mensaje_id, ident, accion, valor)
        self.api.responder_boton(boton["id"], aviso)

    def _boton_fila(self, chat_id: int, mensaje_id: int, fila_id: int, accion: str, valor: str) -> str | None:
        """Botones para clasificar una palabra ambigua o que no está en la rueda."""
        fila = self.bd.obtener_fila(fila_id)
        if fila is None or not self._es_mio(self.bd.obtener_registro(fila["registro_id"])):
            self.api.editar_teclado(chat_id, mensaje_id, None)
            return "Ese registro ya no existe."
        prefijo = f"f:{fila_id}"
        palabra = html.escape(fila["palabra"])
        if accion == "c":
            self.api.editar_teclado(chat_id, mensaje_id, _teclado_palabras(prefijo, valor))
        elif accion == "v":
            self.api.editar_teclado(chat_id, mensaje_id, self._teclado_fila(fila_id, fila["palabra"]))
        elif accion == "e":
            self.bd.clasificar(fila_id, valor)
            clave = rueda.normalizar(fila["palabra"])
            self.bd.aprender(self.usuario_id, clave, valor)
            self.aprendidas[clave] = valor
            self.api.editar(chat_id, mensaje_id,
                            f"«{palabra}» → {_etiqueta(valor)}\n<i>La próxima vez la reconoceré sola.</i>")
            return "Guardado"
        elif accion == "x":
            self.bd.borrar_fila(fila_id)
            registro = self.bd.obtener_registro(fila["registro_id"])
            if registro and not registro["emociones"]:
                self._borrar(chat_id, registro["id"])
            self.api.editar(chat_id, mensaje_id, f"<s>{palabra}</s> — descartada.")
        return None

    def _boton_registro(self, chat_id: int, mensaje_id: int, registro_id: int, accion: str, valor: str) -> str | None:
        """Botones de un registro: agregar emociones, omitir la causa o borrarlo."""
        registro = self.bd.obtener_registro(registro_id)
        if not self._es_mio(registro):
            self.api.editar_teclado(chat_id, mensaje_id, None)
            return "Ese registro ya no existe."
        vacio = not registro["emociones"]
        esperando = self.bd.espera(chat_id) == registro_id
        if accion in ("m", "v"):
            self.api.editar_teclado(chat_id, mensaje_id, self._teclado_elegir(registro_id, vacio))
        elif accion == "c":
            self.api.editar_teclado(chat_id, mensaje_id, _teclado_palabras(f"r:{registro_id}", valor))
        elif accion == "e":
            self.bd.agregar_emocion(registro_id, rueda.EMOCIONES[valor].nombre, valor)
            self.api.editar(chat_id, mensaje_id,
                            _resumen(self.bd.obtener_registro(registro_id), "✅ <b>Guardado</b>"),
                            _teclado_registro(registro_id, esperando))
            return "Agregada"
        elif accion == "k":
            self.api.editar_teclado(chat_id, mensaje_id, _teclado_registro(registro_id, esperando))
        elif accion == "o":
            self.bd.quitar_espera(chat_id)
            self.api.editar_teclado(chat_id, mensaje_id, _teclado_registro(registro_id))
            return "Listo, queda sin causa."
        elif accion == "x" and vacio:
            self._borrar(chat_id, registro_id)
            self.api.editar(chat_id, mensaje_id, "✖️ Cancelado.")
        elif accion == "x":
            self.api.editar_teclado(chat_id, mensaje_id, _teclado_registro(registro_id, esperando))
        elif accion == "d":
            self.api.editar_teclado(chat_id, mensaje_id, [[
                _boton("Sí, borrar", f"r:{registro_id}:D"), _boton("No", f"r:{registro_id}:k"),
            ]])
        elif accion == "D":
            self._borrar(chat_id, registro_id)
            self.api.editar(chat_id, mensaje_id, "🗑 Registro borrado.")
            return "Borrado"
        return None

    def _borrar(self, chat_id: int, registro_id: int) -> None:
        self.bd.borrar_registro(registro_id)  # también borra su espera de causa, si la había

    # --- Comandos ----------------------------------------------------------------------

    def _comando(self, chat_id: int, usuario_id: int, texto: str) -> None:
        comando = texto.split()[0][1:].split("@")[0].lower()
        if comando in ("start", "ayuda", "help"):
            self.api.enviar(chat_id, self._ayuda())
        elif comando == "panel":
            self._enviar_enlace_panel(chat_id, usuario_id)
        elif comando == "rueda":
            self.api.enviar(chat_id, _texto_rueda())
        elif comando == "hoy":
            self.api.enviar(chat_id, self._texto_hoy())
        elif comando in ("semana", "resumen"):
            self.api.enviar(chat_id, self._texto_semana())
        elif comando == "deshacer":
            registro = self.bd.ultimo_registro(self.usuario_id)
            if registro is None:
                self.api.enviar(chat_id, "Todavía no hay registros.")
            else:
                self.api.enviar(chat_id, _resumen(registro, "¿Borro este registro?"), [[
                    _boton("Sí, borrar", f'r:{registro["id"]}:D'), _boton("No", f'r:{registro["id"]}:k'),
                ]])
        elif comando == "cancelar":
            self.bd.quitar_espera(chat_id)
            self.api.enviar(chat_id, "Listo.")
        else:
            self.api.enviar(chat_id, "No conozco ese comando. Prueba /ayuda")

    def _enviar_enlace_panel(self, chat_id: int, usuario_id: int) -> None:
        if not self.config.url_publica or not self.config.clave_sesion:
            self.api.enviar(chat_id, "El panel no está configurado.")
            return
        firma = sesion.firmar(self.config.clave_sesion, "entrar", f"t:{usuario_id}", sesion.DURACION_ENLACE)
        enlace = f"{self.config.url_publica}/entrar?t={firma}"
        texto = "🔐 Tu enlace para entrar al panel. Vence en 10 minutos y es solo para ti: no lo compartas."
        if enlace.startswith("https://"):
            self.api.enviar(chat_id, texto, [[{"text": "Abrir mi panel", "url": enlace}]])
        else:
            # Telegram no acepta botones con direcciones locales (http://localhost…).
            self.api.enviar(chat_id, f"{texto}\n\n{html.escape(enlace)}")

    def _ayuda(self) -> str:
        categorias = " · ".join(f'{c["emoji"]} {c["nombre"]}' for c in rueda.CATEGORIAS)
        texto = (
            "<b>Tu diario de emociones</b> 🎡\n\n"
            "Escríbeme cómo te sientes y qué lo causó, por ejemplo:\n"
            f"• {EJEMPLO}\n"
            "• <code>Me siento tranquila porque terminé el proyecto</code>\n"
            "• <code>triste</code> (y luego te pregunto qué lo causó)\n\n"
            f"Acomodo cada emoción en su lugar de la rueda de los sentimientos:\n{categorias}\n\n"
            "Si usas una palabra que no está en la rueda, te pregunto dónde va y la aprendo.\n\n"
            "/hoy — lo que registraste hoy\n"
            "/semana — resumen de los últimos 7 días\n"
            "/panel — ver tu rueda y tus registros\n"
            "/rueda — todas las emociones\n"
            "/deshacer — borrar el último registro"
        )
        return texto

    def _texto_hoy(self) -> str:
        inicio = datetime.now(self.zona).replace(hour=0, minute=0, second=0, microsecond=0)
        registros = self.bd.listar_registros(self.usuario_id, desde=int(inicio.timestamp()))
        if not registros:
            return f"Hoy todavía no registraste nada. ¿Cómo te sientes?\n{EJEMPLO}"
        lineas = [f"<b>Hoy</b> · {len(registros)} registro{'s' if len(registros) != 1 else ''}"]
        for registro in reversed(registros[:30]):
            hora = datetime.fromtimestamp(registro["creado_en"], self.zona).strftime("%H:%M")
            emociones = " · ".join(_corta(f) for f in registro["emociones"]) or "❔"
            lineas += ["", f"<b>{hora}</b> {emociones}"]
            if registro["causa"]:
                lineas.append(html.escape(registro["causa"][:200]))
        return "\n".join(lineas)

    def _texto_semana(self) -> str:
        registros = self.bd.listar_registros(self.usuario_id, desde=int(time.time()) - 7 * 86400)
        filas = [f for r in registros for f in r["emociones"] if f["emocion"] in rueda.EMOCIONES]
        if not filas:
            return "En los últimos 7 días no hay emociones registradas."
        por_categoria = Counter(rueda.EMOCIONES[f["emocion"]].categoria for f in filas)
        por_emocion = Counter(rueda.EMOCIONES[f["emocion"]].nombre for f in filas)
        maximo = max(por_categoria.values())
        lineas = [f"<b>Últimos 7 días</b> · {len(filas)} emociones en {len(registros)} registros", ""]
        for categoria in rueda.CATEGORIAS:
            cantidad = por_categoria.get(categoria["id"], 0)
            barra = "▰" * round(10 * cantidad / maximo) if cantidad else ""
            lineas.append(f'{categoria["emoji"]} {categoria["nombre"]}  {barra.ljust(10, "▱")}  {cantidad}')
        frecuentes = ", ".join(f"{nombre} ({n})" for nombre, n in por_emocion.most_common(5))
        lineas += ["", f"<b>Lo que más sentiste:</b> {frecuentes}"]
        return "\n".join(lineas)
