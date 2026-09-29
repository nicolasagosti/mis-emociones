"""La rueda de los sentimientos y el reconocimiento de emociones en un texto.

Transcripción de «La rueda de los sentimientos» (Gloria Willcox, 1982), traducida
por @anabelcornago y Dr. Megan Anna Neff. Se respetan las palabras de la imagen,
incluso las que aparecen repetidas (DEPRIMIDO, FURIOSO, IRRITADO y AGRADECIDO).
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

# Cada categoría tiene tres tonos (centro, anillo medio, anillo exterior): los mismos
# matices de la imagen, pero más saturados. Las ramas van en sentido horario y unen
# cada palabra del anillo medio con la del anillo exterior que queda justo afuera.
CATEGORIAS = [
    {
        "id": "enojo", "nombre": "Enojo", "emoji": "❤️",
        "colores": ("#EB5547", "#F2877D", "#F9B9B3"),
        "ramas": [("Hostil", "Egoísta"), ("Irritado", "Celoso"), ("Furioso", "Furioso"),
                  ("Estresado", "Irritado"), ("Crítico", "Escéptico"), ("Molesto", "Frustrado")],
    },
    {
        "id": "miedo", "nombre": "Miedo", "emoji": "💜",
        "colores": ("#A95BD0", "#C88DE2", "#E0BDF0"),
        "ramas": [("Débil", "Sin valor"), ("Inseguro", "Inferior"), ("Confundido", "Perplejo"),
                  ("Amenazado", "Nervioso"), ("Ansioso", "Preocupado"), ("Rechazado", "Excluido")],
    },
    {
        "id": "felicidad", "nombre": "Felicidad", "emoji": "🩷",
        "colores": ("#EB4783", "#F27DA8", "#F9B3CD"),
        "ramas": [("Optimista", "Esperanzado"), ("Entusiasmado", "Energético"), ("Juguetón", "Excitado"),
                  ("Contenido", "Alegre"), ("Aceptado", "Valorado"), ("Interesado", "Curioso")],
    },
    {
        "id": "calma", "nombre": "Calma", "emoji": "💛",
        "colores": ("#F8B928", "#FDD372", "#FFE7AD"),
        "ramas": [("Aliviado", "Seguro"), ("Considerado", "Relajado"), ("Tranquilo", "Sereno"),
                  ("Agradecido", "Cariñoso"), ("Confiado", "Sensible"), ("Conectado", "Pertenencia")],
    },
    {
        "id": "fuerza", "nombre": "Fuerza", "emoji": "💚",
        "colores": ("#4CC27A", "#90E0AD", "#BEEED0"),
        "ramas": [("Orgulloso", "Agradecido"), ("Fuerte", "Exitoso"), ("Valiente", "Creativo"),
                  ("Apreciado", "Respetado"), ("Fiel", "Leal"), ("Empoderado", "Enfocado")],
    },
    {
        "id": "tristeza", "nombre": "Tristeza", "emoji": "💙",
        "colores": ("#3D9BE0", "#81C1EE", "#B5DCF7"),
        "ramas": [("Deprimido", "Avergonzado"), ("Indiferente", "Aburrido"), ("Deprimido", "Miserable"),
                  ("Solitario", "Aislado"), ("Vulnerable", "Frágil"), ("Arrepentido", "Culpable")],
    },
]

# Palabras que no están en la rueda pero se refieren claramente a una de ellas.
# Clave: nombre de la rueda (o de la categoría), sin tildes. Valor: palabras separadas por coma,
# escritas con tilde porque el panel las muestra (el bot compara sin tildes).
SINONIMOS = {
    "enojo": "enojado, enfadado, enfado, cabreado, bronca, indignado, indignación, enojé, enfadé",
    "furioso": "furia, rabia, rabioso, ira, cólera, colérico",
    "hostil": "resentido, resentimiento, rencor, rencoroso",
    "irritado": "irritación, irritable, fastidio, fastidiado",
    "estresado": "estrés, agobiado, agobio, abrumado, presionado, estresé, estresa",
    "molesto": "molestia, harto, hastiado",
    "frustrado": "frustración, impotencia, impotente, frustré, frustra",
    "celoso": "celos, envidia, envidioso",
    "egoista": "egoísmo",
    "esceptico": "escepticismo, desconfiado, desconfianza",
    "miedo": "asustado, temor, temeroso, aterrado, aterrorizado, pánico, susto, miedoso, asusté, asusta",
    "ansioso": "ansiedad, angustia, angustiado, intranquilo, inquieto, angustié",
    "nervioso": "nervios",
    "preocupado": "preocupación, preocupé, preocupa",
    "inseguro": "inseguridad",
    "confundido": "confusión, desorientado, perdido",
    "rechazado": "rechazo",
    "amenazado": "amenaza",
    "excluido": "exclusión",
    "debil": "debilidad",
    "sin valor": "inútil, insignificante",
    "inferior": "inferioridad",
    "perplejo": "desconcertado, perplejidad",
    "felicidad": "feliz, felices, dichoso, radiante",
    "alegre": "alegría, alegra",
    "contenido": "contento, satisfecho, satisfacción",
    "entusiasmado": "entusiasmo, emocionado, emocioné, emociona",
    "esperanzado": "esperanza, ilusionado, ilusión, ilusiona",
    "optimista": "optimismo",
    "energetico": "energía, energizado",
    "jugueton": "divertido, diversión",
    "excitado": "eufórico, euforia",
    "aceptado": "aceptación, incluido",
    "valorado": "reconocido",
    "interesado": "interés",
    "curioso": "curiosidad",
    "calma": "calmado, paz, en paz, calmé",
    "tranquilo": "tranquilidad",
    "aliviado": "alivio",
    "agradecido": "gratitud, agradecimiento",
    "sereno": "serenidad",
    "relajado": "relajación, relax, relajé",
    "seguro": "protegido, a salvo",
    "carinoso": "cariño, amor, amado, querido, enamorado, ternura",
    "sensible": "sensibilidad",
    "confiado": "confianza",
    "conectado": "conexión",
    "considerado": "pensativo, reflexivo",
    "fuerza": "poderoso, capaz",
    "orgulloso": "orgullo",
    "valiente": "valentía, coraje",
    "respetado": "respeto",
    "apreciado": "aprecio",
    "leal": "lealtad",
    "fiel": "fidelidad",
    "empoderado": "empoderamiento, decidido, determinado",
    "exitoso": "éxito",
    "creativo": "creatividad, inspirado, inspiración",
    "enfocado": "concentrado, concentración, enfoque",
    "tristeza": ("triste, tristes, desanimado, desánimo, bajoneado, bajón, decaído, melancólico, "
                 "melancolía, nostálgico, nostalgia, dolido, decepcionado, decepción, desilusionado, "
                 "desilusión, entristecí"),
    "deprimido": "depresión, deprimí, deprime",
    "solitario": "soledad, solo",
    "aislado": "aislamiento",
    "avergonzado": "vergüenza, avergoncé",
    "culpable": "culpa",
    "arrepentido": "arrepentimiento",
    "aburrido": "aburrimiento, aburrí, aburre",
    "indiferente": "apático, apatía, indiferencia",
    "fragil": "fragilidad",
    "vulnerable": "vulnerabilidad",
}

# Palabras de relleno que acompañan a las emociones («me siento muy …»).
RELLENO = set("""me te se siento senti sentia sentimos sentir sentirme sentido estoy estaba estuve
    estar ando andaba quede muy re tan bastante algo medio un una poco mas super hoy ayer anoche
    mucho mucha muchisimo demasiado tambien bien totalmente completamente realmente lo la el de
    emocion emociones sentimiento sentimientos sensacion""".split())

# En texto libre, estas palabras suelen tener otro sentido («solo quiero dormir», «seguro que
# sí»); cuentan como emoción solo si las precede una palabra de CLAVES («me siento sola»).
AMBIGUAS = set("""solo seguro fuerte sensible interesado interes fiel leal contenido aceptado
    conectado considerado curioso critico calma paz fuerza perdido capaz querido amor amado exito
    respeto confianza energia relax aprecio reconocido incluido enfoque conexion amenaza rechazo
    culpa excitado debil inferior apreciado respetado valorado alegra emociona preocupa""".split())
CLAVES = RELLENO | set("""nos dio da daba dan dieron que soy era fui puro pura termine""".split())
NEGACIONES = {"no", "nunca", "jamas", "tampoco", "ni", "nada"}
SALUDOS = {"hola", "holi", "buenas", "buen", "buenos", "hey", "gracias", "ok", "okay", "dale",
           "listo", "chau", "adios", "hi", "hello"}


@dataclass(frozen=True)
class Emocion:
    id: str            # «enojo» (centro de la rueda) o «enojo/frustrado»
    nombre: str        # «Frustrado»
    categoria: str     # «enojo»
    anillo: str        # «centro», «medio» o «exterior»
    padre: str | None  # emoción del anillo de adentro


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples: «Juguetón » → «jugueton»."""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    sin_tildes = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_tildes).strip()


def _slug(nombre: str) -> str:
    return normalizar(nombre).replace(" ", "-")


CATEGORIA = {c["id"]: c for c in CATEGORIAS}
EMOCIONES: dict[str, Emocion] = {}
for _cat in CATEGORIAS:
    EMOCIONES[_cat["id"]] = Emocion(_cat["id"], _cat["nombre"], _cat["id"], "centro", None)
    for _medio, _exterior in _cat["ramas"]:
        _id_medio = f'{_cat["id"]}/{_slug(_medio)}'
        _id_exterior = f'{_cat["id"]}/{_slug(_exterior)}'
        # Una palabra repetida dentro de la misma categoría es la misma emoción:
        # se queda con el lugar donde aparece primero.
        EMOCIONES.setdefault(_id_medio, Emocion(_id_medio, _medio, _cat["id"], "medio", _cat["id"]))
        EMOCIONES.setdefault(_id_exterior, Emocion(_id_exterior, _exterior, _cat["id"], "exterior", _id_medio))


def _variantes(palabra: str) -> set[str]:
    """Femenino y plural de una palabra normalizada: «frustrado» → frustrada, frustrados…"""
    formas = {palabra}
    if " " in palabra:
        return formas
    if palabra.endswith("o"):
        formas |= {palabra[:-1] + "a", palabra + "s", palabra[:-1] + "as"}
    elif palabra.endswith("on"):
        formas |= {palabra + "a", palabra + "es", palabra + "as"}
    elif palabra.endswith(("e", "a")):
        formas.add(palabra + "s")
    elif palabra.endswith(("l", "r")):
        formas.add(palabra + "es")
    return formas


def _construir_indice() -> dict[str, tuple[str, ...]]:
    por_nombre: dict[str, set[str]] = {}
    for emocion in EMOCIONES.values():
        por_nombre.setdefault(normalizar(emocion.nombre), set()).add(emocion.id)

    indice: dict[str, set[str]] = {}
    for nombre, ids in por_nombre.items():
        for forma in _variantes(nombre):
            indice.setdefault(forma, set()).update(ids)
    for destino, palabras in SINONIMOS.items():
        for palabra in palabras.split(","):
            for forma in _variantes(normalizar(palabra)):
                indice.setdefault(forma, set()).update(por_nombre[destino])
    return {forma: tuple(sorted(ids)) for forma, ids in indice.items()}


# Forma escrita (normalizada) → emociones posibles. Casi siempre es una sola;
# «agradecido» está en Calma y en Fuerza, así que devuelve las dos.
INDICE = _construir_indice()
AMBIGUAS = {forma for palabra in AMBIGUAS for forma in _variantes(palabra)}


def _palabras_incluidas() -> dict[str, list[str]]:
    """Para cada emoción, las palabras que el bot ya entiende así (su nombre y sus sinónimos), con tilde."""
    por_nombre: dict[str, set[str]] = {}
    for emocion in EMOCIONES.values():
        por_nombre.setdefault(normalizar(emocion.nombre), set()).add(emocion.id)
    incluidas = {emocion.id: [emocion.nombre.lower()] for emocion in EMOCIONES.values()}
    for destino, palabras in SINONIMOS.items():
        for emocion_id in por_nombre[destino]:
            incluidas[emocion_id] += [p.strip() for p in palabras.split(",") if p.strip()]
    return incluidas


PALABRAS_INCLUIDAS = _palabras_incluidas()


def camino(emocion_id: str) -> list[str]:
    """Nombres desde el centro de la rueda: ['Enojo', 'Molesto', 'Frustrado']."""
    nombres = []
    emocion = EMOCIONES.get(emocion_id)
    while emocion:
        nombres.append(emocion.nombre)
        emocion = EMOCIONES.get(emocion.padre) if emocion.padre else None
    return nombres[::-1]


def color(emocion_id: str) -> str:
    emocion = EMOCIONES[emocion_id]
    anillo = ("centro", "medio", "exterior").index(emocion.anillo)
    return CATEGORIA[emocion.categoria]["colores"][anillo]


def es_forma_de(palabra: str, emocion_id: str) -> bool:
    """¿La palabra escrita es el nombre de la emoción (o su femenino/plural)?"""
    return normalizar(palabra) in _variantes(normalizar(EMOCIONES[emocion_id].nombre))


def sugerencias(palabra: str, aprendidas: dict[str, str] | None = None, cantidad: int = 3) -> list[str]:
    """Emociones de la rueda que se escriben parecido a la palabra desconocida."""
    formas = {**{k: v for k, v in INDICE.items()}, **{k: (v,) for k, v in (aprendidas or {}).items()}}
    ids: list[str] = []
    for forma in difflib.get_close_matches(normalizar(palabra), list(formas), n=8, cutoff=0.6):
        for emocion_id in formas[forma]:
            if emocion_id not in ids:
                ids.append(emocion_id)
    return ids[:cantidad]


def como_json() -> dict:
    """La rueda completa para el panel web."""
    def nodo(nombre: str, categoria: str) -> dict:
        return {"id": f"{categoria}/{_slug(nombre)}", "nombre": nombre}

    return {
        "categorias": [
            {
                "id": c["id"],
                "nombre": c["nombre"],
                "emoji": c["emoji"],
                "colores": dict(zip(("centro", "medio", "exterior"), c["colores"])),
                "ramas": [{"medio": nodo(m, c["id"]), "exterior": nodo(e, c["id"])} for m, e in c["ramas"]],
            }
            for c in CATEGORIAS
        ],
        "emociones": {
            e.id: {"nombre": e.nombre, "categoria": e.categoria, "anillo": e.anillo,
                   "camino": camino(e.id), "color": color(e.id), "palabras": PALABRAS_INCLUIDAS[e.id]}
            for e in EMOCIONES.values()
        },
    }


# --- Interpretar mensajes ---------------------------------------------------------------

@dataclass
class Coincidencia:
    palabra: str             # como la escribió la persona, p. ej. «frustrada»
    ids: tuple[str, ...]     # emociones posibles (más de una si la palabra es ambigua)


@dataclass
class Interpretacion:
    emociones: list[Coincidencia] = field(default_factory=list)
    desconocidas: list[str] = field(default_factory=list)  # palabras que no están en la rueda
    causa: str | None = None
    explicito: bool = False  # vino con el formato «emociones: causa»


# «frustrado: …», «frustrado - …», un salto de línea, o «frustrado porque …».
_SEPARADOR = re.compile(
    r"\s*(?::|\n+|\s[-–—]+\s|[–—])\s*|\s+(?:porque|por que|pq|xq|ya que|debido a)\s+",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"\w+|[^\w\s]")
_CONECTORES = {"y", "e", "ni", "o"}

Token = tuple[str, str]  # (original, normalizado)


def _items(texto: str) -> list[list[Token]]:
    """Parte el texto en ítems separados por comas, puntos o «y»: «triste y sola» → 2 ítems."""
    items, actual = [], []
    for m in _TOKEN.finditer(texto):
        original, norm = m.group(), normalizar(m.group())
        if not norm[:1].isalnum() or norm in _CONECTORES:
            if actual:
                items.append(actual)
            actual = []
        else:
            actual.append((original, norm))
    if actual:
        items.append(actual)
    return items


def _buscar(item: list[Token], i: int, aprendidas: dict[str, str]) -> tuple[int, tuple[str, ...]] | None:
    """La coincidencia más larga que empieza en item[i]: (cantidad de palabras, ids)."""
    for n in (3, 2, 1):
        if i + n > len(item):
            continue
        clave = " ".join(norm for _, norm in item[i:i + n])
        if clave in aprendidas:
            return n, (aprendidas[clave],)
        if clave in INDICE:
            return n, INDICE[clave]
    return None


def _analizar(texto: str, aprendidas: dict[str, str]):
    """Por cada ítem: (ítem, coincidencias [(posición, largo, ids)], palabras que sobran)."""
    partes = []
    for item in _items(texto):
        encontradas, resto, i = [], [], 0
        while i < len(item):
            hallada = _buscar(item, i, aprendidas)
            if hallada:
                encontradas.append((i, *hallada))
                i += hallada[0]
            else:
                if item[i][1] not in RELLENO:
                    resto.append(item[i])
                i += 1
        partes.append((item, encontradas, resto))
    return partes


def _es_lista(partes) -> bool:
    """¿Es una lista corta de emociones («frustrado, ansioso», «me siento agotada»)?"""
    hay_algo = any(encontradas or resto for _, encontradas, resto in partes)
    return hay_algo and all(
        (encontradas and not resto) or (not encontradas and len(resto) <= 2)
        for _, encontradas, resto in partes
    )


def _corregir(palabra: str) -> tuple[str, ...] | None:
    """Tolera errores de tipeo en palabras largas: «frustardo» → frustrado."""
    if len(palabra) < 5:
        return None
    parecidas = difflib.get_close_matches(palabra, list(INDICE), n=1, cutoff=0.84)
    return INDICE[parecidas[0]] if parecidas else None


def _extraer(partes, libre: bool) -> tuple[list[Coincidencia], list[str]]:
    emociones: list[Coincidencia] = []
    desconocidas: list[str] = []
    anterior_termino_en_emocion = False
    for item, encontradas, resto in partes:
        contadas = 0
        for pos, largo, ids in encontradas:
            previas = [norm for _, norm in item[max(0, pos - 3):pos]]
            if NEGACIONES & set(previas):
                continue
            if libre and largo == 1 and item[pos][1] in AMBIGUAS:
                tiene_clave = pos > 0 and item[pos - 1][1] in CLAVES
                encadenada = pos == 0 and anterior_termino_en_emocion  # «triste y sola»
                if not (tiene_clave or encadenada):
                    continue
            palabra = " ".join(original for original, _ in item[pos:pos + largo])
            if all(c.ids != ids for c in emociones):
                emociones.append(Coincidencia(palabra, ids))
            contadas += 1
        if not libre and not encontradas and resto:
            palabra = " ".join(original for original, _ in resto)
            corregida = _corregir(normalizar(palabra))
            if corregida:
                emociones.append(Coincidencia(palabra, corregida))
            else:
                desconocidas.append(palabra)
        ultima = encontradas[-1] if encontradas else None
        anterior_termino_en_emocion = bool(contadas) and ultima[0] + ultima[1] == len(item)
    return emociones, desconocidas


def _oracion(texto: str) -> str:
    texto = texto.strip()
    return texto[:1].upper() + texto[1:]


def interpretar(texto: str, aprendidas: dict[str, str] | None = None) -> Interpretacion:
    """Separa las emociones de la causa en un mensaje.

    - «Frustrado, ansioso: mi jefe cambió la fecha» → dos emociones y la causa.
    - «frustrado y ansioso» → dos emociones, sin causa (el bot la pregunta).
    - «Hoy me sentí triste y sola en la fiesta» → emociones del texto; la causa es todo el mensaje.
    """
    # Lo aprendido vale también en femenino y plural («agotado» → agotada, agotados…).
    formas = {forma: emocion for palabra, emocion in (aprendidas or {}).items() for forma in _variantes(palabra)}
    aprendidas = {**formas, **(aprendidas or {})}
    texto = texto.strip()

    separador = _SEPARADOR.search(texto)
    if separador:
        causa = texto[separador.end():].strip()
        partes = _analizar(texto[:separador.start()], aprendidas)
        if causa and _es_lista(partes):
            emociones, desconocidas = _extraer(partes, libre=False)
            return Interpretacion(emociones, desconocidas, _oracion(causa), explicito=True)

    partes = _analizar(texto, aprendidas)
    if _es_lista(partes):
        emociones, desconocidas = _extraer(partes, libre=False)
        return Interpretacion(emociones, desconocidas, None)

    emociones, _ = _extraer(partes, libre=True)
    return Interpretacion(emociones, [], _oracion(texto))


def palabra_valida(texto: str) -> str | None:
    """Una palabra (o expresión de hasta 3 palabras) para enseñarle al bot, normalizada;
    None si no sirve. «Sin Ganas» → «sin ganas»."""
    palabras = [normalizar(p) for p in re.findall(r"[^\W\d_]+", texto)]
    if not 1 <= len(palabras) <= 3:
        return None
    palabra = " ".join(palabras)
    return palabra if len(palabra) <= 40 else None


def significado(palabra: str, aprendidas: dict[str, str] | None = None) -> tuple[str, ...]:
    """Cómo entiende hoy el bot esta palabra: las emociones posibles (vacío si no la conoce)."""
    emociones = interpretar(palabra, aprendidas).emociones
    return emociones[0].ids if len(emociones) == 1 else ()


def es_saludo(texto: str) -> bool:
    items = _items(texto)
    return bool(items) and items[0][0][1] in SALUDOS and not interpretar(texto).emociones
