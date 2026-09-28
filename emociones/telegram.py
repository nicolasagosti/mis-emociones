"""Cliente mínimo de la API de bots de Telegram, sin dependencias externas."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class ErrorTelegram(Exception):
    def __init__(self, codigo: int | None, descripcion: str):
        super().__init__(f"{codigo}: {descripcion}")
        self.codigo = codigo
        self.descripcion = descripcion


class Telegram:
    def __init__(self, token: str):
        # El token nunca se incluye en mensajes de error ni en los logs.
        self._base = f"https://api.telegram.org/bot{token}/"

    def llamar(self, metodo: str, espera: float = 30, **parametros):
        datos = json.dumps({k: v for k, v in parametros.items() if v is not None}).encode()
        pedido = urllib.request.Request(
            self._base + metodo, data=datos, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(pedido, timeout=espera) as respuesta:
                cuerpo = json.load(respuesta)
        except urllib.error.HTTPError as error:
            try:
                cuerpo = json.load(error)
            except ValueError:
                raise ErrorTelegram(error.code, error.reason) from None
        except urllib.error.URLError as error:
            raise ErrorTelegram(None, f"sin conexión ({error.reason})") from None
        if not cuerpo.get("ok"):
            raise ErrorTelegram(cuerpo.get("error_code"), cuerpo.get("description", "error desconocido"))
        return cuerpo["result"]

    def enviar(self, chat_id: int, texto: str, teclado: list[list[dict]] | None = None) -> dict:
        return self.llamar(
            "sendMessage", chat_id=chat_id, text=texto, parse_mode="HTML",
            reply_markup={"inline_keyboard": teclado} if teclado else None,
            link_preview_options={"is_disabled": True},
        )

    def editar(self, chat_id: int, mensaje_id: int, texto: str, teclado: list[list[dict]] | None = None) -> None:
        try:
            self.llamar(
                "editMessageText", chat_id=chat_id, message_id=mensaje_id, text=texto, parse_mode="HTML",
                reply_markup={"inline_keyboard": teclado or []},
                link_preview_options={"is_disabled": True},
            )
        except ErrorTelegram as error:
            # Tocar dos veces el mismo botón deja el mensaje igual: no es un error real.
            if "message is not modified" not in error.descripcion:
                raise

    def editar_teclado(self, chat_id: int, mensaje_id: int, teclado: list[list[dict]] | None) -> None:
        try:
            self.llamar(
                "editMessageReplyMarkup", chat_id=chat_id, message_id=mensaje_id,
                reply_markup={"inline_keyboard": teclado or []},
            )
        except ErrorTelegram as error:
            if "message is not modified" not in error.descripcion:
                raise

    def responder_boton(self, callback_id: str, texto: str | None = None) -> None:
        self.llamar("answerCallbackQuery", callback_query_id=callback_id, text=texto)
