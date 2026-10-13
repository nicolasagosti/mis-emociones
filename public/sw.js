// Lo mínimo para instalar la aplicación (y para la app de Android): sin conexión muestra un aviso
// en vez del error del navegador. No guarda registros ni sesiones: todo lo demás va a la red.
const CACHE = 'mis-emociones-v1';
const ESTILOS = '/estatico/estilos.css';
const SIN_CONEXION = `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Mis emociones</title>
<link rel="stylesheet" href="${ESTILOS}"></head><body><main class="acceso"><section class="tarjeta">
<h1>Sin conexión</h1><p>Mis emociones necesita internet para mostrar tu diario. Revisa tu conexión y vuelve a intentarlo.</p>
<p><a href="/">Volver a intentar</a></p></section></main></body></html>`;

self.addEventListener('install', (evento) => {
  evento.waitUntil(caches.open(CACHE).then((cache) => cache.add(ESTILOS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(caches.keys()
    .then((claves) => Promise.all(claves.filter((clave) => clave !== CACHE).map((clave) => caches.delete(clave))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (evento) => {
  const { request } = evento;
  if (request.mode === 'navigate') {
    evento.respondWith(fetch(request).catch(() =>
      new Response(SIN_CONEXION, { headers: { 'Content-Type': 'text/html; charset=utf-8' } })));
  } else if (new URL(request.url).pathname === ESTILOS) {
    evento.respondWith(fetch(request).catch(() => caches.match(ESTILOS)));
  }
});
