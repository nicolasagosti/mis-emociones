# Mis emociones

Un diario de emociones: le escribes a un bot de Telegram cómo te sientes y qué lo causó, y la
aplicación acomoda cada emoción en su lugar de **la rueda de los sentimientos** (Gloria Willcox,
1982; versión en español de @anabelcornago / Dr. Megan Anna Neff). Un panel web muestra la rueda
con tus emociones resaltadas y tus registros ordenados por categoría.

Cada persona tiene **su propio diario** y puede compartirlo en solo lectura (por ejemplo, con su
psicóloga): quien lo recibe lo ve en la pestaña **Compartidos conmigo**, junto a su propio diario.

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
5. **Configura el inicio de sesión con Google** (ver abajo).
6. **Entra con Google y abre la sección Telegram** del menú de la izquierda → *Vincular mi Telegram*
   → *Abrir Telegram* → *Iniciar*. Desde ese momento lo que le escribas va a tu diario. Cada persona vincula su propio Telegram; el bot es
   uno solo para todas.

### Inicio de sesión con Google

1. En [Google Cloud Console](https://console.cloud.google.com/) crea un proyecto (por ejemplo
   `mis-emociones`) y selecciónalo.
2. Ve a **Google Auth Platform** (o *APIs y servicios → Pantalla de consentimiento de OAuth*) →
   **Comenzar**: nombre de la app `Mis emociones`, tu correo de asistencia, público **Externo**,
   tu correo de contacto, acepta la política y **Crear**.
3. En **Público** → **Usuarios de prueba** → agrega tu Gmail. La app queda "en prueba": solo
   pueden usarla las cuentas de esa lista.
4. En **Clientes** → **Crear cliente** → tipo **Aplicación web** → en *URIs de redireccionamiento
   autorizados* agrega exactamente:
   `https://mis-emociones-one.vercel.app/auth/google/callback` → **Crear**.
5. Copia el **ID de cliente** y el **secreto** (el secreto se muestra una sola vez) y agrégalos en
   Vercel, en *Settings → Environment Variables*, junto con los correos que pueden entrar:

   | Variable | Valor |
   | --- | --- |
   | `GOOGLE_CLIENT_ID` | el ID de cliente (termina en `.apps.googleusercontent.com`) |
   | `GOOGLE_CLIENT_SECRET` | el secreto (empieza con `GOCSPX-`) |
   | `GOOGLE_CORREOS` | opcional: tu Gmail (si usabas la versión con un solo dueño, tus datos pasan a esa cuenta) |

6. **Publica la app en Google**: *Google Auth Platform* → **Audience** → **Publish app**. Mientras
   esté "en prueba", solo pueden entrar las cuentas que agregues como *Test user*. Como la app solo
   pide el correo, Google no exige verificarla.
7. Vuelve a publicar en Vercel. En la página aparece **Entrar con Google**: cualquier persona con una
   cuenta de Google puede entrar, y la primera vez se le crea su propio diario.

### Compartir tu diario (por ejemplo, con tu psicóloga)

1. En el menú de la izquierda → **Compartir mi diario**, escribe su correo de Google y toca **Dar acceso**.
2. Envíale el enlace de la app. Entra con **Entrar con Google** y tiene **su propio diario** (y
   puede vincular su Telegram); el tuyo lo ve en **Compartidos conmigo**, en solo lectura.
3. Para dejar de compartir, toca **Quitar**: deja de ver tu diario en el acto (su cuenta sigue).

### Cuentas y seguridad
- Cualquier persona con una cuenta de Google (con el correo verificado) puede crear su cuenta.
- Cada persona ve y modifica solo su diario; los compartidos son de solo lectura. Los permisos se
  revisan en cada pedido, así que dejar de compartir tiene efecto inmediato.
- Para entrar: con Google, o con el enlace que manda el bot con `/panel` (firmado, vence en 10
  minutos). La sesión dura 30 días en ese navegador.
- El inicio con Google usa el flujo estándar con `state` y PKCE, y valida que la cuenta de Google
  sea para esta app, esté vigente y tenga el correo verificado.
- El enlace de «Vincular Telegram» está firmado y vence en 10 minutos. Un Telegram solo puede
  estar vinculado a una cuenta. Con `TELEGRAM_USUARIOS` limitas qué Telegrams pueden usar el bot.
- Telegram firma cada aviso que manda al webhook y la aplicación rechaza los que no traen la firma.
- Si usabas la versión anterior (con un solo dueño): tus registros, las palabras que le enseñaste
  al bot y con quién compartías pasan a tu cuenta la primera vez que entras con el correo de
  `GOOGLE_CORREOS`. Si ahí hay varios correos, pasan a la cuenta desde la que vincules tu Telegram.

## Usarla en tu computadora

Solo necesita Python 3.9 o más nuevo; no hay nada que instalar.

```bash
cp .env.example .env     # y pega el token en TELEGRAM_TOKEN=
python3 main.py
```

Escríbele a tu bot y abre el panel en <http://localhost:8000> (en tu computadora no pide entrar
y hay una sola cuenta: la de la primera persona que le escribe al bot).
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

Comandos: `/hoy`, `/semana`, `/panel`, `/rueda`, `/palabras`, `/deshacer`, `/ayuda`.

### Tus palabras

Cada persona puede enseñarle al bot sus propias palabras, cambiar dónde va una u olvidarla, desde
Telegram o desde la sección **Mis palabras** de la app (los cambios valen en los dos lados):

| En Telegram | Qué hace |
| --- | --- |
| `/palabras` | Lista las palabras que le enseñaste y dónde van |
| `/palabra agotado` | Te muestra cómo la entiende hoy y te deja elegir en la rueda dónde va |
| `/olvidar agotado` | La olvida: vuelve a entenderla como antes, o a preguntarte |

Lo que definas vale también en femenino y en plural, y reemplaza a los sinónimos que trae el bot
(por ejemplo, puedes hacer que para ti «rabia» sea Molesto en lugar de Furioso).

En la app también puedes tocar una emoción de la rueda para ver las palabras que la nombran y
agregarle o quitarle las tuyas, o tocar un registro en **Tus registros** para editarlo: cambiar lo
que pasó, mover una emoción a otro lugar de la rueda (y, si quieres, que el bot recuerde esa palabra
para la próxima), quitarla o agregar otras.

### Los nombres de tu rueda

Toca una palabra de la rueda para cambiarle el nombre en tu diario (por ejemplo, Frustrado →
«Bloqueado»). Se ve así en la rueda, tus registros, el resumen y las respuestas del bot, que además
la entiende cuando la escribes; quien vea tu diario compartido también ve tus nombres. Puedes volver
al nombre original cuando quieras (el lápiz ✎ del panel de la emoción la abre de nuevo).

## El panel

- **La rueda** tal como en la imagen, con colores más intensos. Lo que sentiste en el período
  elegido queda resaltado y con la cantidad de veces; el resto se atenúa (se puede apagar).
- **Resumen** por categoría y las emociones más frecuentes.
- **Tus registros** en columnas por categoría o como diario cronológico.
- Toca una emoción o una categoría (en la rueda o en las barras) para filtrar tus registros;
  en la rueda, además, puedes cambiarle el nombre y ver sus palabras.
- Toca un registro para editarlo: lo que pasó y sus emociones.
- Se actualiza solo cuando llegan mensajes nuevos.

## Tus datos

En Vercel quedan en tu base de datos de Neon; en tu computadora, en `datos/emociones.db` (SQLite).

## Personalizar

Cada persona puede ajustar sus palabras desde la app o Telegram (ver «Tus palabras»). Las
emociones de la rueda, los colores y los sinónimos que vienen incluidos están en
`emociones/rueda.py` (`CATEGORIAS` y `SINONIMOS`). La rueda respeta la imagen original, incluidas sus repeticiones: DEPRIMIDO aparece
dos veces en Tristeza, FURIOSO e IRRITADO en dos anillos de Enojo, y AGRADECIDO está en Calma y
en Fuerza (por eso el bot pregunta cuál la primera vez).

## Pruebas

```bash
python3 -m unittest
# También contra Postgres (necesita psycopg): PRUEBAS_POSTGRES_URL=postgresql://… python3 -m unittest
```
