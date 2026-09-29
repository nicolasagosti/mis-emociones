// Panel de «Mis emociones»: dibuja la rueda y acomoda los registros por categoría.

const SVG = 'http://www.w3.org/2000/svg';
const RADIOS = { centro: 118, medio: 222, exterior: 322 };
const REFRESCO_MS = 8000;

const estado = {
  rueda: null,
  registros: [],
  firma: '',
  periodo: leer('periodo', '7'),
  vista: leer('vista', 'categorias'),
  resaltar: leer('resaltar', '1') === '1',
  filtro: null, // { tipo: 'categoria' | 'emocion', id, nombre }
  refresco: null,
  rol: 'dueno', // 'dueno' o 'lectura' (con quien compartiste el panel)
};

// --- Utilidades ------------------------------------------------------------------

function leer(clave, porDefecto) {
  try { return localStorage.getItem(`emociones.${clave}`) ?? porDefecto; } catch { return porDefecto; }
}

function guardar(clave, valor) {
  try { localStorage.setItem(`emociones.${clave}`, valor); } catch { /* sin almacenamiento */ }
}

const $ = (selector) => document.querySelector(selector);

function el(etiqueta, clase, ...hijos) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  nodo.append(...hijos.filter((h) => h !== null && h !== undefined));
  return nodo;
}

function svg(etiqueta, atributos = {}) {
  const nodo = document.createElementNS(SVG, etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) nodo.setAttribute(clave, valor);
  return nodo;
}

const normalizar = (texto) => texto.toLowerCase().normalize('NFD').replace(/\p{Mn}/gu, '').trim();
const info = (fila) => estado.rueda.emociones[fila.emocion];
const categoria = (id) => estado.rueda.categorias.find((c) => c.id === id);

const formatoDia = new Intl.DateTimeFormat('es', { weekday: 'long', day: 'numeric', month: 'long' });
const formatoCorto = new Intl.DateTimeFormat('es', { weekday: 'short', day: 'numeric', month: 'short' });
const formatoHora = new Intl.DateTimeFormat('es', { hour: '2-digit', minute: '2-digit' });

// --- Rueda -----------------------------------------------------------------------

const punto = (r, grados) => {
  const a = (grados * Math.PI) / 180;
  return [r * Math.cos(a), r * Math.sin(a)];
};

function sector(r0, r1, a0, a1) {
  const [x0, y0] = punto(r1, a0);
  const [x1, y1] = punto(r1, a1);
  if (r0 === 0) return `M0 0 L${x0} ${y0} A${r1} ${r1} 0 0 1 ${x1} ${y1} Z`;
  const [x2, y2] = punto(r0, a1);
  const [x3, y3] = punto(r0, a0);
  return `M${x0} ${y0} A${r1} ${r1} 0 0 1 ${x1} ${y1} L${x2} ${y2} A${r0} ${r0} 0 0 0 ${x3} ${y3} Z`;
}

function dibujarRueda() {
  const lienzo = $('#rueda');
  lienzo.replaceChildren();
  // Igual que en la imagen: Enojo arriba y el resto en sentido horario, 60° cada una.
  estado.rueda.categorias.forEach((cat, i) => {
    const inicio = -120 + i * 60;
    agregarSegmento(lienzo, {
      id: cat.id, nombre: cat.nombre, anillo: 'centro', color: cat.colores.centro,
      r0: 0, r1: RADIOS.centro, a0: inicio, a1: inicio + 60,
    });
    cat.ramas.forEach((rama, j) => {
      const a0 = inicio + j * 10;
      agregarSegmento(lienzo, { ...rama.medio, anillo: 'medio', color: cat.colores.medio,
        r0: RADIOS.centro, r1: RADIOS.medio, a0, a1: a0 + 10 });
      agregarSegmento(lienzo, { ...rama.exterior, anillo: 'exterior', color: cat.colores.exterior,
        r0: RADIOS.medio, r1: RADIOS.exterior, a0, a1: a0 + 10 });
    });
  });
  lienzo.append(svg('circle', { class: 'marco', r: RADIOS.exterior + 8 }));
}

function agregarSegmento(lienzo, s) {
  const grupo = svg('g', { class: `seg ${s.anillo}`, tabindex: 0, role: 'button', 'aria-label': s.nombre });
  grupo.dataset.id = s.id;
  grupo.dataset.nombre = s.nombre;
  grupo.dataset.anillo = s.anillo;
  grupo.append(svg('path', { d: sector(s.r0, s.r1, s.a0, s.a1), fill: s.color }));

  const medio = (s.a0 + s.a1) / 2;
  const texto = svg('text', { 'text-anchor': 'middle' });
  if (s.anillo === 'centro') {
    const [x, y] = punto(RADIOS.centro * 0.6, medio);
    texto.setAttribute('x', x.toFixed(1));
    texto.setAttribute('y', y.toFixed(1));
  } else {
    // Texto radial; se da vuelta donde quedaría cabeza abajo (como en la imagen).
    const angulo = ((medio % 360) + 360) % 360;
    const girar = angulo >= 60 && angulo < 300 ? ' rotate(180)' : '';
    texto.setAttribute('transform', `rotate(${medio}) translate(${(s.r0 + s.r1) / 2} 0)${girar}`);
  }
  grupo.append(texto);
  lienzo.append(grupo);
}

function actualizarRueda(conteo) {
  const lienzo = $('#rueda');
  lienzo.classList.toggle('resaltar', estado.resaltar);
  for (const grupo of lienzo.querySelectorAll('.seg')) {
    const { id, nombre, anillo } = grupo.dataset;
    const cantidad = anillo === 'centro' ? conteo.porCategoria.get(id) || 0 : conteo.porEmocion.get(id) || 0;
    grupo.classList.toggle('con-datos', cantidad > 0);
    grupo.classList.toggle('sin-datos', cantidad === 0);
    grupo.classList.toggle('seleccionado', estado.filtro?.id === id);
    grupo.dataset.cantidad = cantidad;

    const texto = grupo.querySelector('text');
    texto.replaceChildren();
    if (anillo === 'centro') {
      const x = texto.getAttribute('x');
      const titulo = svg('tspan', { x, dy: cantidad ? '-0.45em' : '0' });
      titulo.textContent = nombre;
      texto.append(titulo);
      if (cantidad) {
        const numero = svg('tspan', { x, dy: '1.25em', class: 'cuenta' });
        numero.textContent = cantidad;
        texto.append(numero);
      }
    } else {
      texto.append(nombre);
      if (cantidad) {
        const numero = svg('tspan', { class: 'cuenta', dx: '4' });
        numero.textContent = cantidad;
        texto.append(numero);
      }
    }
  }
}

// --- Globo de ayuda sobre la rueda ---------------------------------------------------

function mostrarGlobo(grupo, x, y) {
  const globo = $('#globo');
  const { id, anillo, cantidad } = grupo.dataset;
  const datos = anillo === 'centro' ? { nombre: categoria(id).nombre, camino: [] } : estado.rueda.emociones[id];
  const veces = Number(cantidad);
  globo.replaceChildren(
    el('strong', null, datos.nombre),
    datos.camino.length > 1 ? el('div', 'ruta', datos.camino.slice(0, -1).join(' › ')) : null,
    el('div', null, veces ? `${veces} ${veces === 1 ? 'vez' : 'veces'} en este período` : 'Sin registros en este período'),
  );
  globo.hidden = false;
  const ancho = globo.offsetWidth;
  globo.style.left = `${Math.min(x + 14, window.innerWidth - ancho - 8)}px`;
  globo.style.top = `${y + 14}px`;
}

function conectarRueda() {
  const lienzo = $('#rueda');
  lienzo.addEventListener('pointermove', (e) => {
    const grupo = e.target.closest('.seg');
    if (grupo) mostrarGlobo(grupo, e.clientX, e.clientY);
    else $('#globo').hidden = true;
  });
  lienzo.addEventListener('pointerleave', () => { $('#globo').hidden = true; });
  lienzo.addEventListener('focusin', (e) => {
    const grupo = e.target.closest('.seg');
    if (!grupo) return;
    const caja = grupo.getBoundingClientRect();
    mostrarGlobo(grupo, caja.left + caja.width / 2, caja.top + caja.height / 2);
  });
  lienzo.addEventListener('focusout', () => { $('#globo').hidden = true; });
  const elegir = (grupo) => {
    const { id, nombre, anillo } = grupo.dataset;
    alternarFiltro({ tipo: anillo === 'centro' ? 'categoria' : 'emocion', id, nombre });
  };
  lienzo.addEventListener('click', (e) => {
    const grupo = e.target.closest('.seg');
    if (grupo) elegir(grupo);
  });
  lienzo.addEventListener('keydown', (e) => {
    const grupo = e.target.closest('.seg');
    if (grupo && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      elegir(grupo);
    }
  });
}

// --- Resumen -------------------------------------------------------------------------

function contar(registros) {
  const porEmocion = new Map();
  const porCategoria = new Map();
  let emociones = 0;
  for (const registro of registros) {
    for (const fila of registro.emociones) {
      const datos = info(fila);
      if (!datos) continue;
      emociones += 1;
      porEmocion.set(fila.emocion, (porEmocion.get(fila.emocion) || 0) + 1);
      porCategoria.set(datos.categoria, (porCategoria.get(datos.categoria) || 0) + 1);
    }
  }
  return { porEmocion, porCategoria, emociones };
}

function chip(fila) {
  const datos = info(fila);
  if (!datos) return el('span', 'chip sin-clasificar', `${fila.palabra} ?`);
  const nodo = el('span', 'chip', datos.nombre);
  nodo.style.setProperty('--color', datos.color);
  nodo.title = datos.camino.join(' › ');
  // Si escribió otra palabra («rabia» → Furioso), se muestra al lado.
  if (!normalizar(fila.palabra).startsWith(normalizar(datos.nombre).slice(0, -1))) {
    nodo.append(el('span', 'original', `· ${fila.palabra}`));
  }
  return nodo;
}

function dibujarResumen(conteo) {
  const totales = $('#totales');
  const numero = (valor, texto) => el('div', null, el('strong', null, String(valor)), el('span', null, texto));
  totales.replaceChildren(
    numero(conteo.emociones, conteo.emociones === 1 ? 'emoción' : 'emociones'),
    numero(estado.registros.length, estado.registros.length === 1 ? 'registro' : 'registros'),
  );

  const maximo = Math.max(1, ...conteo.porCategoria.values());
  $('#barras').replaceChildren(...estado.rueda.categorias.map((cat) => {
    const cantidad = conteo.porCategoria.get(cat.id) || 0;
    const relleno = el('div', 'relleno');
    relleno.style.width = `${(100 * cantidad) / maximo}%`;
    relleno.style.setProperty('--color', cat.colores.centro);
    const fila = el('div', 'barra',
      el('span', 'nombre', `${cat.emoji} ${cat.nombre}`),
      el('div', 'pista-barra', relleno),
      el('span', 'numero', String(cantidad)));
    fila.title = `Ver registros de ${cat.nombre}`;
    fila.addEventListener('click', () => alternarFiltro({ tipo: 'categoria', id: cat.id, nombre: cat.nombre }));
    return fila;
  }));

  const frecuentes = [...conteo.porEmocion.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  const lista = $('#frecuentes');
  if (!frecuentes.length) {
    lista.replaceChildren(el('li', 'sin-datos-texto', 'Aún nada en este período.'));
    return;
  }
  lista.replaceChildren(...frecuentes.map(([id, veces]) => {
    const datos = estado.rueda.emociones[id];
    return el('li', null,
      el('span', null, chip({ emocion: id, palabra: datos.nombre }), ' ',
        el('span', 'ruta', datos.camino.slice(0, -1).join(' › '))),
      el('span', 'veces', `×${veces}`));
  }));
}

// --- Registros -----------------------------------------------------------------------

function visibles() {
  const { filtro } = estado;
  if (!filtro) return estado.registros;
  return estado.registros.filter((r) => r.emociones.some((fila) => (
    filtro.tipo === 'emocion' ? fila.emocion === filtro.id : info(fila)?.categoria === filtro.id
  )));
}

function tarjeta(registro, { enDiario = false } = {}) {
  const fecha = new Date(registro.creado_en * 1000);
  let borrar = null; // quien solo tiene acceso de lectura no puede borrar
  if (estado.rol === 'dueno') {
    borrar = el('button', 'borrar', '×');
    borrar.type = 'button';
    borrar.title = 'Borrar registro';
    borrar.setAttribute('aria-label', 'Borrar registro');
    borrar.addEventListener('click', () => borrarRegistro(registro.id));
  }

  const chips = registro.emociones.length
    ? registro.emociones.map(chip)
    : [el('span', 'chip sin-clasificar', 'Sin emoción')];
  const causa = el('p', registro.causa ? 'causa' : 'causa falta', registro.causa || 'Sin causa');
  if (registro.mensaje && registro.mensaje !== registro.causa) causa.title = `Mensaje: ${registro.mensaje}`;

  if (enDiario) {
    const nodo = el('article', 'registro',
      el('time', 'hora', formatoHora.format(fecha)),
      el('div', 'cuerpo', el('div', 'chips', ...chips), causa),
      borrar);
    const primera = registro.emociones.map(info).find(Boolean);
    nodo.style.setProperty('--color', primera ? categoria(primera.categoria).colores.centro : 'var(--borde)');
    return nodo;
  }
  const cuando = `${formatoCorto.format(fecha)} · ${formatoHora.format(fecha)}`;
  return el('article', 'registro',
    el('div', 'meta', el('time', null, cuando), borrar),
    el('div', 'chips', ...chips),
    causa);
}

function dibujarTablero(registros) {
  const columnas = estado.rueda.categorias.map((cat) => ({
    titulo: `${cat.emoji} ${cat.nombre}`,
    color: cat.colores.centro,
    registros: registros.filter((r) => r.emociones.some((f) => info(f)?.categoria === cat.id)),
    id: cat.id,
  }));
  const sinClasificar = registros.filter((r) => !r.emociones.length || r.emociones.some((f) => !info(f)));
  if (sinClasificar.length) {
    columnas.push({ titulo: '❔ Sin clasificar', color: 'var(--pista)', registros: sinClasificar, id: null });
  }

  const { filtro } = estado;
  const mostrar = columnas.filter((c) => (
    filtro?.tipo === 'categoria' ? c.id === filtro.id : !filtro || c.registros.length
  ));
  $('#tablero').replaceChildren(...mostrar.map((columna) => {
    const cabecera = el('header', null,
      el('span', null, columna.titulo),
      el('span', 'cantidad', String(columna.registros.length)));
    cabecera.style.setProperty('--color', columna.color);
    const lista = columna.registros.length
      ? el('div', 'lista', ...columna.registros.map((r) => tarjeta(r)))
      : el('p', 'vacia', 'Nada por aquí en este período.');
    const nodo = el('section', 'columna', cabecera, lista);
    nodo.style.setProperty('--color', columna.color);
    return nodo;
  }));
}

function dibujarDiario(registros) {
  const dias = new Map();
  for (const registro of registros) {
    const clave = formatoDia.format(new Date(registro.creado_en * 1000));
    if (!dias.has(clave)) dias.set(clave, []);
    dias.get(clave).push(registro);
  }
  $('#diario').replaceChildren(...[...dias].map(([dia, lista]) => el('section', 'dia',
    el('h3', null, dia),
    el('div', 'lista', ...lista.map((r) => tarjeta(r, { enDiario: true }))))));
}

async function borrarRegistro(id) {
  if (!window.confirm('¿Borrar este registro? No se puede deshacer.')) return;
  const respuesta = await fetch(`/api/registros/${id}`, { method: 'DELETE' });
  if (respuesta.ok) {
    estado.firma = '';
    await cargarRegistros();
  }
}

// --- Estado y eventos -------------------------------------------------------------------

function alternarFiltro(filtro) {
  estado.filtro = estado.filtro?.id === filtro.id ? null : filtro;
  dibujar();
}

function dibujar() {
  const conteo = contar(estado.registros);
  actualizarRueda(conteo);
  dibujarResumen(conteo);

  const { filtro } = estado;
  $('#filtro').hidden = !filtro;
  if (filtro) $('#filtro-texto').textContent = `Filtrando: ${filtro.nombre}`;

  const registros = visibles();
  const vacio = registros.length === 0;
  $('#vacio').hidden = !vacio || Boolean(filtro);
  $('#tablero').hidden = estado.vista !== 'categorias' || (vacio && !filtro);
  $('#diario').hidden = estado.vista !== 'diario' || vacio;
  if (estado.vista === 'categorias') dibujarTablero(registros);
  else dibujarDiario(registros);

  for (const boton of document.querySelectorAll('#periodos button')) {
    boton.setAttribute('aria-pressed', String(boton.dataset.periodo === estado.periodo));
  }
  for (const boton of document.querySelectorAll('#vistas button')) {
    boton.setAttribute('aria-pressed', String(boton.dataset.vista === estado.vista));
  }
}

function desde() {
  if (estado.periodo === 'todo') return null;
  if (estado.periodo === 'hoy') {
    const hoy = new Date();
    hoy.setHours(0, 0, 0, 0);
    return Math.floor(hoy.getTime() / 1000);
  }
  return Math.floor(Date.now() / 1000) - Number(estado.periodo) * 86400;
}

async function cargarRegistros() {
  const inicio = desde();
  try {
    const respuesta = await fetch(`/api/registros${inicio === null ? '' : `?desde=${inicio}`}`);
    if (respuesta.status === 401 || respuesta.status === 503) {
      // La sesión venció o falta configurar algo: se vuelve a la pantalla de acceso.
      clearInterval(estado.refresco);
      mostrarAcceso(await (await fetch('/api/estado')).json());
      return;
    }
    if (!respuesta.ok) return;
    const { registros } = await respuesta.json();
    const firma = JSON.stringify(registros);
    if (firma === estado.firma) return;
    estado.firma = firma;
    estado.registros = registros;
    dibujar();
  } catch (error) {
    console.warn('No pude leer los registros:', error);
  }
}

function conectarControles() {
  $('#periodos').addEventListener('click', (e) => {
    const boton = e.target.closest('button');
    if (!boton) return;
    estado.periodo = boton.dataset.periodo;
    guardar('periodo', estado.periodo);
    estado.firma = '';
    cargarRegistros();
  });
  $('#vistas').addEventListener('click', (e) => {
    const boton = e.target.closest('button');
    if (!boton) return;
    estado.vista = boton.dataset.vista;
    guardar('vista', estado.vista);
    dibujar();
  });
  const resaltar = $('#resaltar');
  resaltar.checked = estado.resaltar;
  resaltar.addEventListener('change', () => {
    estado.resaltar = resaltar.checked;
    guardar('resaltar', estado.resaltar ? '1' : '0');
    dibujar();
  });
  $('#quitar-filtro').addEventListener('click', () => { estado.filtro = null; dibujar(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) cargarRegistros(); });
  estado.refresco = setInterval(() => { if (!document.hidden) cargarRegistros(); }, REFRESCO_MS);
}

// --- Acceso (fuera de tu computadora, el panel pide entrar con el enlace de /panel) -------

const AYUDA_BOT = {
  falta_token: 'Se conecta solo cuando agregues el token.',
  espera_base_de_datos: 'Se conecta solo cuando la base de datos esté lista.',
  solo_produccion: 'Esta es una vista previa: el bot se conecta desde la versión de producción.',
  token_invalido: 'Telegram rechazó el token: revisa TELEGRAM_TOKEN.',
  error: 'No pude hablar con Telegram. Recarga la página en un momento.',
};

function mostrarAcceso(servidor) {
  $('#contenido').hidden = true;
  $('#periodos').hidden = true;
  $('#salir').hidden = true;
  $('#cuenta').hidden = true;
  $('#acceso').hidden = false;
  $('#entrar-google').hidden = !servidor.google;
  $('#acceso-telegram').hidden = servidor.google;
  $('#acceso-telegram-alternativa').hidden = !servidor.google;
  const pasos = [
    ['Base de datos', servidor.base_de_datos,
      'En Vercel: Storage → Create Database → Neon. Conéctala a este proyecto y vuelve a desplegar.'],
    ['Inicio con Google', servidor.google,
      'Agrega GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET y GOOGLE_CORREOS en Settings → Environment Variables (los pasos están en el README) y vuelve a desplegar.'],
    ['Token del bot', servidor.token,
      'Crea el bot con @BotFather y guarda el token como TELEGRAM_TOKEN en Settings → Environment Variables. Luego vuelve a desplegar.'],
    ['Bot conectado', ['conectado', 'local'].includes(servidor.bot), AYUDA_BOT[servidor.bot] || ''],
  ];
  $('#pasos').replaceChildren(...pasos.map(([titulo, listo, ayuda]) => el('li', listo ? 'listo' : 'falta',
    el('span', 'marca', listo ? '✓' : '✗'),
    el('div', null, el('strong', null, titulo), listo ? null : el('span', null, ayuda)))));
}

// --- Compartir el panel (solo el dueño) ----------------------------------------------------

async function pedirAccesos(opciones) {
  const respuesta = await fetch('/api/accesos', opciones);
  if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
  return (await respuesta.json()).accesos;
}

function dibujarAccesos(accesos) {
  const lista = $('#accesos');
  if (!accesos.length) {
    lista.replaceChildren(el('li', 'sin-datos-texto', 'Todavía no lo compartiste con nadie.'));
    return;
  }
  lista.replaceChildren(...accesos.map(({ correo }) => {
    const quitar = el('button', 'quitar', 'Quitar');
    quitar.type = 'button';
    quitar.setAttribute('aria-label', `Quitarle el acceso a ${correo}`);
    quitar.addEventListener('click', () => quitarAcceso(correo));
    return el('li', null, el('span', 'correo', correo), quitar);
  }));
}

function avisarAcceso(texto) {
  $('#aviso-acceso').textContent = texto;
  $('#aviso-acceso').hidden = !texto;
}

async function quitarAcceso(correo) {
  if (!window.confirm(`¿Quitarle el acceso a ${correo}? Dejará de ver tu panel en el acto.`)) return;
  const respuesta = await fetch(`/api/accesos/${encodeURIComponent(correo)}`, { method: 'DELETE' });
  if (respuesta.ok) {
    avisarAcceso(`${correo} ya no puede ver tu panel.`);
    dibujarAccesos(await pedirAccesos());
  }
}

function iniciarCompartir(url) {
  $('#compartir').hidden = false;
  $('#enlace-panel').textContent = url.replace(/^https?:\/\//, '');
  $('#form-acceso').addEventListener('submit', async (e) => {
    e.preventDefault();
    const campo = $('#correo-acceso');
    const correo = campo.value.trim().toLowerCase();
    try {
      dibujarAccesos(await pedirAccesos({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ correo }),
      }));
      avisarAcceso(`Listo: ${correo} ya puede entrar. Envíale el enlace del panel.`);
      campo.value = '';
    } catch {
      avisarAcceso('No pude darle acceso: revisa que el correo esté bien escrito.');
    }
  });
  pedirAccesos().then(dibujarAccesos).catch(() => avisarAcceso('No pude cargar con quién compartiste el panel.'));
}

async function iniciar() {
  const servidor = await (await fetch('/api/estado')).json();
  if (servidor.requiere_sesion && !servidor.sesion) {
    mostrarAcceso(servidor);
    return;
  }
  estado.rol = servidor.rol;
  $('#contenido').hidden = false;
  $('#periodos').hidden = false;
  $('#salir').hidden = !servidor.requiere_sesion;
  if (servidor.cuenta) {
    $('#cuenta').hidden = false;
    $('#cuenta').textContent = servidor.rol === 'lectura' ? `Solo lectura · ${servidor.cuenta}` : servidor.cuenta;
  }
  if (servidor.requiere_sesion && servidor.rol === 'dueno') iniciarCompartir(servidor.url);
  estado.rueda = await (await fetch('/api/rueda')).json();
  dibujarRueda();
  conectarRueda();
  conectarControles();
  dibujar();
  await cargarRegistros();
}

iniciar();
