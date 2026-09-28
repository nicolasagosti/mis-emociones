"""Registros de ejemplo para ver el panel funcionando (`python3 main.py --demo`)."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import rueda
from .bd import BaseDeDatos

# (días atrás, hora, emociones, causa)
EJEMPLOS = [
    (0, "08:40", ["miedo/ansioso", "miedo/nervioso"], "Tengo la presentación con el cliente a las 11"),
    (0, "12:15", ["calma/aliviado", "fuerza/orgulloso"], "La presentación salió muy bien"),
    (0, "21:30", ["calma/agradecido"], "Mi hermana me llamó para felicitarme"),
    (1, "10:05", ["enojo/frustrado"], "El tren se atrasó 40 minutos otra vez"),
    (1, "19:20", ["felicidad/jugueton", "felicidad/alegre"], "Partido de fútbol con amigos"),
    (2, "09:00", ["enojo/estresado", "enojo/molesto"], "Me cambiaron la fecha de entrega sin avisar"),
    (2, "23:10", ["tristeza/solitario"], "Todos salieron y yo me quedé en casa"),
    (3, "14:45", ["felicidad/interesado", "felicidad/curioso"], "Empecé un curso de fotografía"),
    (4, "08:30", ["miedo/preocupado"], "Mi mamá tiene estudios médicos esta semana"),
    (4, "18:00", ["calma/tranquilo", "calma/conectado"], "Caminata por el parque con Sofi"),
    (5, "11:20", ["enojo/critico", "enojo/esceptico"], "Reunión eterna en la que no se decidió nada"),
    (6, "20:00", ["tristeza/vulnerable"], "Hablé con una amiga sobre la mudanza"),
    (6, "22:15", ["calma/relajado", "calma/sereno"], "Baño caliente y un buen libro"),
    (8, "16:40", ["fuerza/valiente", "fuerza/empoderado"], "Por fin pedí el aumento"),
    (9, "10:10", ["miedo/inseguro", "miedo/inferior"], "Comparé mi trabajo con el de un compañero"),
    (10, "13:30", ["felicidad/entusiasmado", "felicidad/esperanzado"], "Reservamos las vacaciones"),
    (12, "09:45", ["enojo/irritado"], "Los vecinos hicieron ruido toda la noche"),
    (13, "17:05", ["fuerza/respetado", "fuerza/apreciado"], "Mi jefa reconoció mi trabajo frente al equipo"),
    (15, "21:00", ["tristeza/arrepentido", "tristeza/culpable"], "Le hablé mal a mi pareja por cansancio"),
    (17, "12:00", ["felicidad/aceptado", "felicidad/valorado"], "Primer asado con el equipo nuevo"),
    (20, "08:15", ["tristeza/aburrido", "tristeza/indiferente"], "Domingo de lluvia sin planes"),
    (24, "19:40", ["fuerza/creativo", "fuerza/enfocado"], "Terminé el diseño del proyecto personal"),
    (27, "15:30", ["miedo/confundido", "miedo/perplejo"], "No entiendo qué espera el cliente del proyecto"),
]


def sembrar(bd: BaseDeDatos) -> None:
    hoy = datetime.now()
    for dias, hora, emociones, causa in EJEMPLOS:
        horas, minutos = map(int, hora.split(":"))
        fecha = (hoy - timedelta(days=dias)).replace(hour=horas, minute=minutos, second=0, microsecond=0)
        filas = [(rueda.EMOCIONES[e].nombre, e) for e in emociones]
        mensaje = f'{", ".join(n for n, _ in filas)}: {causa}'
        bd.crear_registro(int(fecha.timestamp()), causa, mensaje, None, filas)
    # Una palabra que el bot todavía no sabe dónde va.
    ayer = int((hoy - timedelta(days=1)).replace(hour=15, minute=0).timestamp())
    bd.crear_registro(ayer, "Dormí cuatro horas", "Agotado: dormí cuatro horas", None, [("Agotado", None)])
