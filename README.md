# Mis emociones

Un diario de emociones: le escribes a un bot de Telegram cómo te sientes y qué lo causó, y la
aplicación acomoda cada emoción en su lugar de **la rueda de los sentimientos** (Gloria Willcox,
1982; versión en español de @anabelcornago / Dr. Megan Anna Neff). Un panel web muestra la rueda
con tus emociones resaltadas y tus registros ordenados por categoría.

Funciona en **Vercel** (siempre disponible, desde cualquier dispositivo) o **en tu computadora**.

## En línea: <https://mis-emociones-one.vercel.app>

El proyecto de Vercel está conectado a este repositorio: **cada `git push` a `main` publica los
cambios solo**, en menos de un minuto. Un push a otra rama crea una vista previa con su propia
dirección (el bot sigue conectado a la versión principal).

### Configurarlo (una sola vez)

1. **Crea la base de datos.** En [vercel.com](https://vercel.com), abre el proyecto →
   **Storage** → **Create Database** → **Neon** (plan gratis) → conéctala al proyecto.
2. **Vuelve a publicar** para que tome la configuración nueva: *Deployments → ⋯ → Redeploy*
   (o haz cualquier push). Hace falta cada vez que cambias la base de datos o las variables.
3. **Abre la dirección del proyecto.** Verás una lista con lo que está listo y lo que falta.
4. **Cuando tengas el token del bot** (en Telegram: [@BotFather](https://t.me/BotFather) → `/newbot`),
   agrégalo en *Settings → Environment Variables*:

   | Variable | Valor |
   | --- | --- |
   | `TELEGRAM_TOKEN` | el token que te dio BotFather |
   | `ZONA_HORARIA` | recomendado, p. ej. `America/Argentina/Buenos_Aires`, `America/Mexico_City`, `Europe/Madrid` |
   | `TELEGRAM_USUARIOS` | opcional: tu ID de Telegram (te lo dice [@userinfobot](https://t.me/userinfobot)) |

   Vuelve a publicar (paso 2) y **abre la página una vez**: eso conecta el bot con Telegram.
5. **Escríbele a tu bot** y envíale `/panel`: te responde con un enlace para entrar al panel.

### Seguridad
- El panel está en internet, así que para ver tus datos hay que entrar con el enlace de `/panel`
  (firmado, vence en 10 minutos; la sesión dura 30 días en ese navegador). Solo el dueño del bot
  puede pedirlo.
- El bot queda para la primera persona que le escribe. Escríbele apenas lo conectes, o fija tu ID
  en `TELEGRAM_USUARIOS`.
- Telegram firma cada aviso que manda al webhook y la aplicación rechaza los que no traen la firma.

## Usarla en tu computadora

Solo necesita Python 3.9 o más nuevo; no hay nada que instalar.

```bash
cp .env.example .env     # y pega el token en TELEGRAM_TOKEN=
python3 main.py
```

Escríbele a tu bot y abre el panel en <http://localhost:8000> (en tu computadora no pide entrar).
Para ver el panel sin configurar nada: `python3 main.py --demo` (datos de ejemplo, en una base aparte).

Un bot atiende en un solo lugar a la vez: si ya lo conectaste a Vercel, antes de usarlo en tu
computadora desconéctalo abriendo `https://api.telegram.org/bot<TOKEN>/deleteWebhook`.

## Cómo escribirle al bot

| Mensaje | Qué hace |
| --- | --- |
| `Frustrado, ansioso: mi jefe cambió la fecha de entrega` | Guarda las dos emociones con esa causa |
| `Me siento tranquila porque terminé el proyecto` | También sirve `porque`, un guion o un salto de línea |
| `triste` | Guarda la emoción y te pregunta qué la causó |
| `Hoy me sentí triste y sola en la fiesta` | Detecta las emociones dentro de la frase |
| `Hoy me peleé con mi hermano` | Si no reconoce emociones, te deja elegirlas en la rueda con botones |

- Entiende femenino, plural, sin tildes y errores de tipeo (`frustrada`, `jugueton`, `frustardo`).
- También reconoce sinónimos comunes: `rabia` → Furioso, `contento` → Contenido, `estrés` → Estresado…
- Si usas una palabra que no está en la rueda (`agotado`), te pregunta dónde va **y la aprende**.
- En cada registro puedes tocar **➕ Otra emoción** o **🗑 Borrar**.

Comandos: `/hoy`, `/semana`, `/panel`, `/rueda`, `/deshacer`, `/ayuda`.

## El panel

- **La rueda** tal como en la imagen, con colores más intensos. Lo que sentiste en el período
  elegido queda resaltado y con la cantidad de veces; el resto se atenúa (se puede apagar).
- **Resumen** por categoría y las emociones más frecuentes.
- **Tus registros** en columnas por categoría o como diario cronológico.
- Toca una emoción o una categoría (en la rueda o en las barras) para filtrar.
- Se actualiza solo cuando llegan mensajes nuevos.

## Tus datos

En Vercel quedan en tu base de datos de Neon; en tu computadora, en `datos/emociones.db` (SQLite).

## Personalizar

Las palabras, los colores y los sinónimos están en `emociones/rueda.py` (`CATEGORIAS` y
`SINONIMOS`). La rueda respeta la imagen original, incluidas sus repeticiones: DEPRIMIDO aparece
dos veces en Tristeza, FURIOSO e IRRITADO en dos anillos de Enojo, y AGRADECIDO está en Calma y
en Fuerza (por eso el bot pregunta cuál la primera vez).

## Pruebas

```bash
python3 -m unittest
# También contra Postgres (necesita psycopg): PRUEBAS_POSTGRES_URL=postgresql://… python3 -m unittest
```
