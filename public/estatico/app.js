// Panel de «Mis emociones»: dibuja la rueda y acomoda los registros por categoría.

const SVG = 'http://www.w3.org/2000/svg';
const RADIOS = { centro: 118, medio: 222, exterior: 322 };
const REFRESCO_MS = 8000;

const estado = {
  ruedaBase: null, // la rueda original, como la manda /api/rueda
  rueda: null, // la del diario que estás viendo, con los nombres que su dueño les puso a sus emociones
  nombres: {}, // {emocion: nombre} de ese diario
  registros: [],
  firma: '',
  periodo: leer('periodo', '7'), // 'hoy', '7', '30', 'todo' o 'dia'
  dia: leer('dia', ''), // con 'dia': el que elegiste, como 2026-09-29 (se valida al iniciar)
  vista: leer('vista', 'categorias'),
  resaltar: leer('resaltar', '1') === '1',
  filtro: null, // { tipo: 'categoria' | 'emocion', id, nombre }
  refresco: null,
  rol: 'dueno', // 'dueno' en tu diario; 'lectura' en uno que te compartieron
  diario: null, // null = tu diario; {id, correo} = uno que te compartieron
  diarioListo: false, // ya se mostró algún diario (para no recargar sin necesidad)
  servidor: null, // la última respuesta de /api/estado
  vinculo: null, // {enlace, codigo, bot} mientras vinculas Telegram
  palabras: null, // las palabras que le enseñaste al bot (se cargan al necesitarlas)
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
// ¿La palabra escrita es el nombre de la emoción (el que le pusiste o el original), o su femenino/plural?
const esSuNombre = (palabra, datos) => [datos.nombre, datos.original]
  .some((nombre) => normalizar(palabra).startsWith(normalizar(nombre).slice(0, -1)));
const categoria = (id) => estado.rueda.categorias.find((c) => c.id === id);

// Un día como 2026-09-29, en tu zona horaria.
const fechaISO = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const hoyISO = () => fechaISO(new Date());
function diaComoFecha(iso, sumar = 0) {
  const [anio, mes, dia] = iso.split('-').map(Number);
  return new Date(anio, mes - 1, dia + sumar); // medianoche de ese día (o de `sumar` días después)
}

const formatoDia = new Intl.DateTimeFormat('es', { weekday: 'long', day: 'numeric', month: 'long' });
const formatoCorto = new Intl.DateTimeFormat('es', { weekday: 'short', day: 'numeric', month: 'short' });
const formatoHora = new Intl.DateTimeFormat('es', { hour: '2-digit', minute: '2-digit' });

// --- Rueda -----------------------------------------------------------------------

// La rueda con los nombres propios del diario que estás viendo (los demás quedan como en el original).
function aplicarNombres() {
  const base = estado.ruedaBase;
  const nombre = (id) => estado.nombres[id] || base.emociones[id].nombre;
  estado.rueda = {
    categorias: base.categorias.map((cat) => ({
      ...cat,
      nombre: nombre(cat.id),
      ramas: cat.ramas.map(({ medio, exterior }) => ({
        medio: { ...medio, nombre: nombre(medio.id) },
        exterior: { ...exterior, nombre: nombre(exterior.id) },
      })),
    })),
    emociones: Object.fromEntries(Object.entries(base.emociones).map(([id, emocion]) => [id, {
      ...emocion, nombre: nombre(id), original: emocion.nombre, camino: emocion.ruta.map(nombre),
    }])),
  };
}

function usarNombres(nombres) {
  estado.nombres = nombres;
  aplicarNombres();
  dibujarRueda();
  if (estado.filtro) estado.filtro.nombre = estado.rueda.emociones[estado.filtro.id].nombre;
}

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
  ajustarEtiquetas();
}

// Un nombre largo (como los que les pones a las emociones) se achica hasta caber en su lugar de la rueda.
function ajustarEtiquetas() {
  for (const grupo of $('#rueda').querySelectorAll('.seg')) {
    const { anillo } = grupo.dataset;
    const texto = grupo.querySelector('text');
    texto.style.fontSize = '';
    const medido = anillo === 'centro' ? texto.firstChild : texto;
    const largo = medido ? medido.getComputedTextLength() : 0; // 0 si está vacía u oculta
    const cabe = anillo === 'centro' ? 84 : RADIOS[anillo] - RADIOS[anillo === 'medio' ? 'centro' : 'medio'] - 2;
    if (largo > cabe) texto.style.fontSize = `${(parseFloat(getComputedStyle(texto).fontSize) * cabe) / largo}px`;
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
    // En el celular el panel de la emoción queda debajo de la rueda: se acerca para que se vea.
    const panel = $('#panel-emocion');
    const quieto = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!panel.hidden) panel.scrollIntoView({ block: 'nearest', behavior: quieto ? 'auto' : 'smooth' });
    // En tu diario, tocar una palabra de la rueda también te deja cambiarle el nombre.
    if (estado.filtro?.id === id && puedeEditar()) abrirEditorNombre(id);
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
  if (!esSuNombre(fila.palabra, datos)) nodo.append(el('span', 'original', `· ${fila.palabra}`));
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
  const editable = puedeEditar();
  let acciones = null; // quien solo tiene acceso de lectura no puede editar ni borrar
  if (estado.rol === 'dueno') {
    let editar = null;
    if (editable) {
      editar = el('button', 'editar', '✎');
      editar.type = 'button';
      editar.title = 'Editar registro';
      editar.setAttribute('aria-label', 'Editar registro');
    }
    const borrar = el('button', 'borrar', '×');
    borrar.type = 'button';
    borrar.title = 'Borrar registro';
    borrar.setAttribute('aria-label', 'Borrar registro');
    borrar.addEventListener('click', () => borrarRegistro(registro.id));
    acciones = el('div', 'acciones-registro', editar, borrar);
  }

  const chips = registro.emociones.length
    ? registro.emociones.map((fila) => {
      const nodo = chip(fila);
      if (editable) nodo.dataset.fila = fila.id; // para abrir el editor en la emoción que tocaste
      return nodo;
    })
    : [el('span', 'chip sin-clasificar', 'Sin emoción')];
  const causa = el('p', registro.causa ? 'causa' : 'causa falta', registro.causa || 'Sin causa');
  if (registro.mensaje && registro.mensaje !== registro.causa) causa.title = `Mensaje: ${registro.mensaje}`;

  let nodo;
  if (enDiario) {
    nodo = el('article', 'registro',
      el('time', 'hora', formatoHora.format(fecha)),
      el('div', 'cuerpo', el('div', 'chips', ...chips), causa),
      acciones);
    const primera = registro.emociones.map(info).find(Boolean);
    nodo.style.setProperty('--color', primera ? categoria(primera.categoria).colores.centro : 'var(--borde)');
  } else {
    const cuando = `${formatoCorto.format(fecha)} · ${formatoHora.format(fecha)}`;
    nodo = el('article', 'registro',
      el('div', 'meta', el('time', null, cuando), acciones),
      el('div', 'chips', ...chips),
      causa);
  }
  if (editable) {
    nodo.classList.add('editable');
    nodo.addEventListener('click', (e) => {
      if (!e.target.closest('.borrar')) abrirEditorRegistro(registro, e.target.closest('[data-fila]')?.dataset.fila);
    });
  }
  return nodo;
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
  if (!window.confirm('¿Borrar este registro? No se puede deshacer.')) return false;
  const respuesta = await fetch(`/api/registros/${id}`, { method: 'DELETE' });
  if (respuesta.ok) {
    estado.firma = '';
    await cargarRegistros();
  }
  return respuesta.ok;
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
  dibujarPanelEmocion();

  const { filtro } = estado;
  $('#filtro').hidden = !filtro;
  if (filtro) $('#filtro-texto').textContent = `Filtrando: ${filtro.nombre}`;

  const registros = visibles();
  const vacio = registros.length === 0;
  $('#vacio').hidden = !vacio || Boolean(filtro);
  $('#nota-editar').hidden = vacio || !puedeEditar();
  for (const p of document.querySelectorAll('#vacio .solo-propio')) p.hidden = Boolean(estado.diario);
  $('#tablero').hidden = estado.vista !== 'categorias' || (vacio && !filtro);
  $('#diario').hidden = estado.vista !== 'diario' || vacio;
  if (estado.vista === 'categorias') dibujarTablero(registros);
  else dibujarDiario(registros);

  dibujarPeriodo();
  for (const boton of document.querySelectorAll('#vistas button')) {
    boton.setAttribute('aria-pressed', String(boton.dataset.vista === estado.vista));
  }
}

function dibujarPeriodo() {
  for (const boton of document.querySelectorAll('#periodos button')) {
    boton.setAttribute('aria-pressed', String(boton.dataset.periodo === estado.periodo));
  }
  const unDia = estado.periodo === 'dia';
  $('#elegir-dia').hidden = !unDia;
  $('#dia-elegido').max = hoyISO();
  $('#dia-elegido').value = estado.dia;
  $('#dia-siguiente').disabled = estado.dia >= hoyISO();
  $('#texto-vacio').textContent = unDia ? 'No hay registros ese día.' : 'Todavía no hay registros en este período.';
}

function elegirPeriodo(periodo) {
  estado.periodo = periodo;
  guardar('periodo', periodo);
  estado.firma = '';
  dibujarPeriodo();
  cargarRegistros();
}

function elegirDia(iso) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso) || Number.isNaN(diaComoFecha(iso).getTime())) return;
  estado.dia = iso > hoyISO() ? hoyISO() : iso; // no hay registros en el futuro
  guardar('dia', estado.dia);
  elegirPeriodo('dia');
}

function desde() {
  if (estado.periodo === 'todo') return null;
  if (estado.periodo === 'dia') return Math.floor(diaComoFecha(estado.dia).getTime() / 1000);
  if (estado.periodo === 'hoy') {
    const hoy = new Date();
    hoy.setHours(0, 0, 0, 0);
    return Math.floor(hoy.getTime() / 1000);
  }
  return Math.floor(Date.now() / 1000) - Number(estado.periodo) * 86400;
}

// Hasta cuándo (sin incluirlo): solo al ver un día, la medianoche del siguiente.
function hasta() {
  return estado.periodo === 'dia' ? Math.floor(diaComoFecha(estado.dia, 1).getTime() / 1000) : null;
}

async function cargarRegistros() {
  const inicio = desde();
  try {
    const parametros = new URLSearchParams();
    if (inicio !== null) parametros.set('desde', inicio);
    if (hasta() !== null) parametros.set('hasta', hasta());
    if (estado.diario) parametros.set('diario', estado.diario.id);
    const respuesta = await fetch(`/api/registros?${parametros}`);
    if (respuesta.status === 401 || respuesta.status === 503) {
      // La sesión venció o falta configurar algo: se vuelve a la pantalla de acceso.
      clearInterval(estado.refresco);
      mostrarAcceso(await (await fetch('/api/estado')).json());
      return;
    }
    if (respuesta.status === 403) {
      await actualizarCuenta(); // te dejaron de compartir ese diario
      return;
    }
    if (!respuesta.ok) return;
    const { registros, nombres = {} } = await respuesta.json();
    const firma = JSON.stringify([registros, nombres]);
    if (firma === estado.firma) return;
    estado.firma = firma;
    estado.registros = registros;
    if (JSON.stringify(nombres) !== JSON.stringify(estado.nombres)) usarNombres(nombres);
    dibujar();
  } catch (error) {
    console.warn('No pude leer los registros:', error);
  }
}

function conectarControles() {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(estado.dia) || estado.dia > hoyISO()) estado.dia = hoyISO();
  $('#periodos').addEventListener('click', (e) => {
    const boton = e.target.closest('button');
    if (!boton) return;
    elegirPeriodo(boton.dataset.periodo);
    if (boton.dataset.periodo !== 'dia') return;
    try {
      $('#dia-elegido').showPicker(); // abre el calendario para elegir el día
    } catch { /* sin calendario emergente: queda el campo con la fecha */ }
  });
  $('#dia-elegido').addEventListener('change', (e) => elegirDia(e.target.value));
  $('#dia-anterior').addEventListener('click', () => elegirDia(fechaISO(diaComoFecha(estado.dia, -1))));
  $('#dia-siguiente').addEventListener('click', () => elegirDia(fechaISO(diaComoFecha(estado.dia, 1))));
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
  document.addEventListener('visibilitychange', async () => {
    // Al volver a la pestaña: quizás vinculaste Telegram o alguien te compartió su diario.
    if (document.hidden) return;
    if (estado.servidor?.requiere_sesion && !(await actualizarCuenta())) return;
    cargarRegistros();
  });
  estado.refresco = setInterval(() => { if (!document.hidden) cargarRegistros(); }, REFRESCO_MS);
}

// --- Acceso (fuera de tu computadora, el panel pide entrar) ------------------------------------

const AYUDA_BOT = {
  falta_token: 'Se conecta solo cuando agregues el token.',
  espera_base_de_datos: 'Se conecta solo cuando la base de datos esté lista.',
  solo_produccion: 'Esta es una vista previa: el bot se conecta desde la versión de producción.',
  token_invalido: 'Telegram rechazó el token: revisa TELEGRAM_TOKEN.',
  error: 'No pude hablar con Telegram. Recarga la página en un momento.',
};

function mostrarAcceso(servidor) {
  $('#app').hidden = true;
  $('#acceso').hidden = false;
  $('#entrar-google').hidden = !servidor.google;
  $('#acceso-telegram').hidden = servidor.google;
  $('#acceso-telegram-alternativa').hidden = !servidor.google;
  const pasos = [
    ['Base de datos', servidor.base_de_datos,
      'En Vercel: Storage → Create Database → Neon. Conéctala a este proyecto y vuelve a desplegar.'],
    ['Inicio con Google', servidor.google,
      'Agrega GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET en Settings → Environment Variables (los pasos están en el README) y vuelve a desplegar.'],
    ['Token del bot', servidor.token,
      'Crea el bot con @BotFather y guarda el token como TELEGRAM_TOKEN en Settings → Environment Variables. Luego vuelve a desplegar.'],
    ['Bot conectado', ['conectado', 'local'].includes(servidor.bot), AYUDA_BOT[servidor.bot] || ''],
  ];
  $('#pasos').replaceChildren(...pasos.map(([titulo, listo, ayuda]) => el('li', listo ? 'listo' : 'falta',
    el('span', 'marca', listo ? '✓' : '✗'),
    el('div', null, el('strong', null, titulo), listo ? null : el('span', null, ayuda)))));
}

// --- Compartir tu diario ------------------------------------------------------------------------

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
  if (!window.confirm(`¿Dejar de compartir tu diario con ${correo}? Dejará de verlo en el acto.`)) return;
  const respuesta = await fetch(`/api/accesos/${encodeURIComponent(correo)}`, { method: 'DELETE' });
  if (respuesta.ok) {
    avisarAcceso(`${correo} ya no puede ver tu diario.`);
    dibujarAccesos(await pedirAccesos());
  }
}

function iniciarCompartir(url) {
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
      avisarAcceso(`Listo: ${correo} ya puede ver tu diario. Envíale el enlace de la app.`);
      campo.value = '';
    } catch {
      avisarAcceso('No pude darle acceso: revisa que el correo esté bien escrito.');
    }
  });
  pedirAccesos().then(dibujarAccesos).catch(() => avisarAcceso('No pude cargar con quién compartiste tu diario.'));
}

// --- Telegram -----------------------------------------------------------------------------------

function avisarTelegram(texto) {
  $('#aviso-telegram').textContent = texto;
  $('#aviso-telegram').hidden = !texto;
}

function boton(texto, clase, alTocar) {
  const nodo = el('button', `boton ${clase}`, texto);
  nodo.type = 'button';
  nodo.addEventListener('click', alTocar);
  return nodo;
}

async function pedirVinculo() {
  const respuesta = await fetch('/api/telegram/vincular', { method: 'POST' });
  if (!respuesta.ok) {
    avisarTelegram('No pude crear el enlace. Intenta de nuevo en un momento.');
    return;
  }
  estado.vinculo = await respuesta.json();
  avisarTelegram('');
  dibujarTelegram();
}

async function yaLoVincule() {
  if (await actualizarCuenta() && !estado.servidor.cuenta.telegram) {
    avisarTelegram('Todavía no aparece vinculado: ¿tocaste «Iniciar» en el chat del bot?');
  }
}

async function desvincularTelegram() {
  if (!window.confirm('¿Desvincular tu Telegram? El bot dejará de guardar en tu diario lo que le escribas.')) return;
  await fetch('/api/telegram/desvincular', { method: 'POST' });
  estado.vinculo = null;
  avisarTelegram('');
  await actualizarCuenta();
}

function dibujarTelegram() {
  const { servidor, vinculo } = estado;
  const acciones = $('#acciones-telegram');
  if (!servidor.token) {
    $('#titulo-vincular').textContent = 'El bot de Telegram no está configurado';
    $('#texto-vincular').textContent = 'Falta la variable TELEGRAM_TOKEN (los pasos están en el README).';
    acciones.replaceChildren();
    return;
  }
  if (servidor.cuenta.telegram) {
    estado.vinculo = null;
    avisarTelegram('');
    $('#titulo-vincular').textContent = 'Tu Telegram está vinculado';
    $('#texto-vincular').textContent = '✓ Todo lo que le escribas al bot se guarda en tu diario.';
    acciones.replaceChildren(boton('Desvincular', 'secundario', desvincularTelegram));
    return;
  }
  $('#titulo-vincular').textContent = 'Vincula tu Telegram';
  $('#texto-vincular').textContent =
    'Se hace una sola vez. Después, cada mensaje que le mandes al bot se guarda en tu diario.';
  if (!vinculo) {
    acciones.replaceChildren(boton('Vincular mi Telegram', 'telegram', pedirVinculo));
    return;
  }
  const abrir = el('a', 'boton telegram', 'Abrir Telegram');
  abrir.href = vinculo.enlace;
  abrir.target = '_blank';
  abrir.rel = 'noopener';
  acciones.replaceChildren(
    el('ol', 'pasos-lista',
      el('li', null, 'Toca ', el('strong', null, 'Abrir Telegram'), `: se abre el chat con @${vinculo.bot}.`),
      el('li', null, 'Toca ', el('strong', null, 'Iniciar'), ' (o «Start») en Telegram.'),
      el('li', null, 'Vuelve aquí y toca ', el('strong', null, 'Ya lo vinculé'), '.')),
    el('div', 'botones', abrir, boton('Ya lo vinculé', 'secundario', yaLoVincule)),
    el('p', 'nota-telegram', '¿Telegram está en otro dispositivo? Mándale al bot ',
      el('code', null, `/start ${vinculo.codigo}`), '. El código vence en 10 minutos.'));
}

// --- Mis palabras: cómo entiende el bot tus palabras ------------------------------------------------

function llenarSelectorEmociones(selector) {
  selector.replaceChildren(); // se arma cada vez: los nombres de tu rueda pueden haber cambiado
  const vacia = el('option', null, 'Elige dónde va en la rueda…');
  vacia.value = '';
  selector.append(vacia);
  for (const cat of estado.rueda.categorias) {
    const grupo = document.createElement('optgroup');
    grupo.label = `${cat.emoji} ${cat.nombre}`;
    const general = el('option', null, `${cat.nombre} (en general)`);
    general.value = cat.id;
    grupo.append(general);
    // Primero el anillo medio y después el exterior, como en el bot.
    const emociones = Object.entries(estado.rueda.emociones)
      .filter(([, e]) => e.categoria === cat.id && e.anillo !== 'centro')
      .sort(([, a], [, b]) => (a.anillo === 'medio' ? 0 : 1) - (b.anillo === 'medio' ? 0 : 1));
    for (const [id, emocion] of emociones) {
      const opcion = el('option', null, emocion.camino.slice(1).join(' › '));
      opcion.value = id;
      grupo.append(opcion);
    }
    selector.append(grupo);
  }
}

async function pedirPalabras(opciones) {
  const respuesta = await fetch('/api/palabras', opciones);
  if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
  estado.palabras = (await respuesta.json()).palabras;
  return estado.palabras;
}

async function guardarPalabra(palabra, emocion) {
  return pedirPalabras({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ palabra, emocion }),
  });
}

async function olvidarEnServidor(palabra) {
  const respuesta = await fetch(`/api/palabras/${encodeURIComponent(palabra)}`, { method: 'DELETE' });
  if (respuesta.ok) await pedirPalabras();
  return respuesta.ok;
}

function avisarPalabras(texto) {
  $('#aviso-palabras').textContent = texto;
  $('#aviso-palabras').hidden = !texto;
}

function dibujarPalabras(palabras) {
  const lista = $('#lista-palabras');
  if (!palabras.length) {
    lista.replaceChildren(el('li', 'sin-datos-texto', 'Todavía no le enseñaste palabras. Cuando uses una que '
      + 'no está en la rueda, el bot te pregunta dónde va y aparece aquí.'));
    return;
  }
  lista.replaceChildren(...palabras.map(({ palabra, emocion }) => {
    const datos = estado.rueda.emociones[emocion];
    const cambiar = el('button', 'enlace', 'Cambiar');
    cambiar.type = 'button';
    cambiar.addEventListener('click', () => {
      $('#palabra-nueva').value = palabra;
      $('#emocion-palabra').value = emocion;
      $('#emocion-palabra').focus();
    });
    const olvidar = el('button', 'quitar', 'Olvidar');
    olvidar.type = 'button';
    olvidar.addEventListener('click', () => olvidarPalabra(palabra));
    return el('li', null,
      el('div', 'palabra-info', el('strong', null, palabra), ' → ', chip({ emocion, palabra: datos.nombre }),
        el('span', 'ruta', datos.camino.slice(0, -1).join(' › '))),
      el('div', 'palabra-acciones', cambiar, olvidar));
  }));
}

async function olvidarPalabra(palabra) {
  if (!window.confirm(`¿Olvidar «${palabra}»? El bot volverá a entenderla como antes, o te preguntará dónde va.`)) return;
  if (await olvidarEnServidor(palabra)) {
    avisarPalabras(`Listo, olvidé «${palabra}».`);
    dibujarPalabras(estado.palabras);
  }
}

function iniciarPalabras() {
  $('#form-palabra').addEventListener('submit', async (e) => {
    e.preventDefault();
    const palabra = $('#palabra-nueva').value.trim().toLowerCase();
    const emocion = $('#emocion-palabra').value;
    if (!emocion) {
      avisarPalabras('Elige dónde va en la rueda.');
      return;
    }
    try {
      dibujarPalabras(await guardarPalabra(palabra, emocion));
      avisarPalabras(`Listo: «${palabra}» → ${estado.rueda.emociones[emocion].camino.join(' › ')}. `
        + 'Desde ahora el bot la entiende así.');
      $('#palabra-nueva').value = '';
    } catch {
      avisarPalabras('No pude guardarla: usa una palabra (o hasta tres) con letras.');
    }
  });
}

function mostrarPalabras() {
  llenarSelectorEmociones($('#emocion-palabra'));
  pedirPalabras().then(dibujarPalabras).catch(() => avisarPalabras('No pude cargar tus palabras.'));
}

// --- Panel de la emoción que tocaste en la rueda: sus palabras -------------------------------------

const puedeEditar = () => estado.rol === 'dueno' && Boolean(estado.servidor?.cuenta);

function avisarEmocion(texto) {
  $('#aviso-emocion').textContent = texto;
  $('#aviso-emocion').hidden = !texto;
}

function dibujarPanelEmocion() {
  const panel = $('#panel-emocion');
  const id = estado.filtro?.id;
  const datos = id && estado.rueda.emociones[id];
  if (!datos || !puedeEditar()) {
    panel.hidden = true;
    return;
  }
  if (estado.palabras === null) { // se cargan una vez; después se actualizan al cambiarlas
    estado.palabras = [];
    pedirPalabras().then(dibujarPanelEmocion).catch(() => avisarEmocion('No pude cargar tus palabras.'));
  }
  panel.hidden = false;
  $('#titulo-emocion').replaceChildren(chip({ emocion: id, palabra: datos.nombre }));
  $('#ruta-emocion').textContent = datos.camino.length > 1
    ? `${datos.camino.join(' › ')}. Lo que agregues aquí, el bot lo entenderá como ${datos.nombre}.`
    : `Toda la categoría ${datos.nombre}. Lo que agregues aquí, el bot lo entenderá como ${datos.nombre} en general.`;

  const propias = estado.palabras.filter((p) => p.emocion === id);
  $('#palabras-emocion').replaceChildren(...(propias.length
    ? propias.map(({ palabra }) => {
      const quitar = el('button', 'quitar', 'Quitar');
      quitar.type = 'button';
      quitar.setAttribute('aria-label', `Quitar «${palabra}»`);
      quitar.addEventListener('click', async () => {
        if (await olvidarEnServidor(palabra)) {
          avisarEmocion(`Listo, «${palabra}» ya no va aquí.`);
          dibujarPanelEmocion();
        }
      });
      return el('li', null, el('strong', null, palabra), quitar);
    })
    : [el('li', 'sin-datos-texto', 'Todavía ninguna.')]));

  // Las incluidas que redefiniste en otra emoción ya no van aquí.
  const redefinidas = new Set(estado.palabras.filter((p) => p.emocion !== id).map((p) => p.palabra));
  $('#incluidas-emocion').textContent = datos.palabras.filter((p) => !redefinidas.has(normalizar(p))).join(', ') || '—';
}

function iniciarPanelEmocion() {
  $('#cerrar-emocion').addEventListener('click', () => {
    estado.filtro = null;
    avisarEmocion('');
    dibujar();
  });
  $('#form-palabra-emocion').addEventListener('submit', async (e) => {
    e.preventDefault();
    const campo = $('#palabra-emocion');
    const palabra = campo.value.trim().toLowerCase();
    const id = estado.filtro?.id;
    if (!id) return;
    try {
      await guardarPalabra(palabra, id);
      avisarEmocion(`Listo: cuando escribas «${palabra}», el bot lo entenderá como ${estado.rueda.emociones[id].nombre}.`);
      campo.value = '';
      dibujarPanelEmocion();
    } catch {
      avisarEmocion('No pude guardarla: usa una palabra (o hasta tres) con letras.');
    }
  });
}

// --- Editar un registro (tocándolo en «Tus registros») ---------------------------------------------

let registroEditado = null;

function avisarRegistro(texto) {
  $('#aviso-registro').textContent = texto;
  $('#aviso-registro').hidden = !texto;
}

// Una emoción en el editor: dónde va en la rueda y, si la cambias, si el bot debe recordar esa palabra.
function emocionEditable({ id = null, palabra, emocion = null }) {
  const nueva = id === null;
  const selector = el('select');
  llenarSelectorEmociones(selector);
  selector.options[0].disabled = Boolean(emocion);
  selector.value = emocion || '';
  selector.setAttribute('aria-label', nueva ? 'Emoción nueva' : `Dónde va «${palabra}»`);
  const quitar = el('button', 'quitar', 'Quitar');
  quitar.type = 'button';
  quitar.setAttribute('aria-label', nueva ? 'Quitar esta emoción' : `Quitar «${palabra}» de este registro`);
  const aprender = el('input');
  aprender.type = 'checkbox';
  const casilla = el('label', 'casilla', aprender,
    el('span', null, `Recordar para la próxima: cuando escriba «${palabra.trim().toLowerCase()}», va aquí`));
  casilla.hidden = true;
  const nodo = el('li', 'fila-emocion', el('span', nueva ? 'palabra nueva' : 'palabra', nueva ? 'Nueva' : `«${palabra}»`),
    selector, quitar, casilla);
  if (!nueva) nodo.dataset.fila = id;

  const antes = estado.rueda.emociones[emocion];
  selector.addEventListener('change', () => {
    const estabaOculta = casilla.hidden;
    casilla.hidden = nueva || selector.value === (emocion || '');
    // Al aparecer: si escribiste el nombre de la emoción, por defecto no cambia lo que esa palabra significa.
    if (estabaOculta && !casilla.hidden) {
      aprender.checked = !(antes && esSuNombre(palabra, antes));
    }
  });
  quitar.addEventListener('click', () => {
    nodo.remove();
    mostrarSinEmociones();
  });
  return nodo;
}

function mostrarSinEmociones() {
  const lista = $('#emociones-registro');
  lista.querySelector('.sin-datos-texto')?.remove();
  if (!lista.querySelector('.fila-emocion')) lista.append(el('li', 'sin-datos-texto', 'Ninguna todavía: agrega una aquí abajo.'));
}

function abrirEditorRegistro(registro, filaTocada) {
  registroEditado = registro;
  const fecha = new Date(registro.creado_en * 1000);
  $('#fecha-registro').textContent = `${formatoDia.format(fecha)} · ${formatoHora.format(fecha)}`;
  const mensaje = registro.mensaje && registro.mensaje !== registro.causa ? registro.mensaje : '';
  $('#mensaje-registro').textContent = mensaje ? `Le escribiste al bot: «${mensaje}»` : '';
  $('#mensaje-registro').hidden = !mensaje;
  $('#causa-registro').value = registro.causa || '';
  $('#emociones-registro').replaceChildren(...registro.emociones.map(emocionEditable));
  mostrarSinEmociones();
  llenarSelectorEmociones($('#agregar-emocion'));
  $('#agregar-emocion').options[0].textContent = 'Elige una en la rueda…';
  $('#agregar-emocion').value = '';
  avisarRegistro('');
  $('#dialogo-registro').showModal();
  // Si tocaste una emoción, el foco va a ella; si no, al título (en el celular, el texto abriría el teclado).
  const tocada = filaTocada && $('#emociones-registro').querySelector(`[data-fila="${filaTocada}"] select`);
  (tocada || $('#titulo-registro')).focus();
}

async function guardarRegistro() {
  const emociones = [...$('#emociones-registro').querySelectorAll('.fila-emocion')].map((nodo) => {
    const emocion = nodo.querySelector('select').value || null;
    if (!nodo.dataset.fila) return { emocion };
    const casilla = nodo.querySelector('.casilla');
    return { id: Number(nodo.dataset.fila), emocion, aprender: !casilla.hidden && casilla.querySelector('input').checked };
  });
  const respuesta = await fetch(`/api/registros/${registroEditado.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ causa: $('#causa-registro').value, emociones }),
  }).catch(() => null);
  if (!respuesta?.ok) {
    avisarRegistro('No pude guardarlo. Intenta de nuevo en un momento.');
    return;
  }
  $('#dialogo-registro').close();
  if (emociones.some((e) => e.aprender)) estado.palabras = null; // el bot aprendió una palabra
  estado.firma = '';
  await cargarRegistros();
}

function iniciarEditorRegistro() {
  $('#form-registro').addEventListener('submit', async (e) => {
    e.preventDefault();
    const boton = e.submitter || $('#form-registro [type=submit]');
    boton.disabled = true;
    try {
      await guardarRegistro();
    } finally {
      boton.disabled = false;
    }
  });
  $('#agregar-emocion').addEventListener('change', (e) => {
    const emocion = e.target.value;
    if (!emocion) return;
    e.target.value = '';
    const repetida = [...$('#emociones-registro').querySelectorAll('.fila-emocion select')].find((s) => s.value === emocion);
    if (repetida) { // ya está en el registro
      repetida.focus();
      return;
    }
    $('#emociones-registro').append(emocionEditable({ palabra: estado.rueda.emociones[emocion].nombre, emocion }));
    mostrarSinEmociones();
  });
  $('#borrar-registro').addEventListener('click', async () => {
    if (await borrarRegistro(registroEditado.id)) $('#dialogo-registro').close();
  });
  $('#cancelar-registro').addEventListener('click', () => $('#dialogo-registro').close());
}

// --- Cambiarle el nombre a una palabra de tu rueda (tocándola) ------------------------------------

let emocionRenombrada = null;

function avisarNombre(texto) {
  $('#aviso-nombre').textContent = texto;
  $('#aviso-nombre').hidden = !texto;
}

function abrirEditorNombre(id) {
  emocionRenombrada = id;
  const datos = estado.rueda.emociones[id];
  $('#ruta-nombre').textContent = datos.camino.join(' › ');
  $('#nombre-propio').value = datos.nombre;
  $('#texto-original').textContent = `Nombre original: ${datos.original}.`;
  $('#original-nombre').hidden = datos.nombre === datos.original;
  avisarNombre('');
  $('#dialogo-nombre').showModal();
  // En el celular, el foco en el campo abriría el teclado aunque solo quisieras ver sus registros.
  if (matchMedia('(pointer: coarse)').matches) $('#titulo-nombre').focus();
  else $('#nombre-propio').select();
}

async function guardarNombre(nombre) {
  const respuesta = await fetch('/api/nombres', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ emocion: emocionRenombrada, nombre }),
  }).catch(() => null);
  if (!respuesta?.ok) {
    avisarNombre({
      400: 'Usa de una a tres palabras, solo con letras (hasta 20 caracteres).',
      409: 'Otra emoción de tu rueda ya se llama así.',
    }[respuesta?.status] || 'No pude guardarlo. Intenta de nuevo en un momento.');
    return;
  }
  $('#dialogo-nombre').close();
  estado.palabras = null; // el bot pudo haber aprendido el nombre nuevo
  usarNombres((await respuesta.json()).nombres);
  dibujar();
}

function iniciarEditorNombre() {
  $('#form-nombre').addEventListener('submit', (e) => {
    e.preventDefault();
    guardarNombre($('#nombre-propio').value);
  });
  $('#restaurar-nombre').addEventListener('click', () => guardarNombre(''));
  $('#cancelar-nombre').addEventListener('click', () => $('#dialogo-nombre').close());
  $('#renombrar-emocion').addEventListener('click', () => {
    if (estado.filtro) abrirEditorNombre(estado.filtro.id);
  });
  // Tocar fuera de la ventana también la cierra.
  $('#dialogo-nombre').addEventListener('click', (e) => {
    const caja = e.currentTarget.getBoundingClientRect();
    const fuera = e.clientX < caja.left || e.clientX > caja.right || e.clientY < caja.top || e.clientY > caja.bottom;
    if (e.target === e.currentTarget && fuera) e.currentTarget.close();
  });
}

// --- Menú lateral y secciones (#/diario, #/compartido/<id>, #/palabras, #/compartir, #/telegram) ---

function abrirMenu() {
  $('#lateral').classList.add('abierto');
  $('#velo').hidden = false;
  $('#abrir-menu').setAttribute('aria-expanded', 'true');
  $('#lateral').focus(); // con el teclado, Tab recorre las secciones desde aquí
}

function cerrarMenu() {
  $('#lateral').classList.remove('abierto');
  $('#velo').hidden = true;
  $('#abrir-menu').setAttribute('aria-expanded', 'false');
}

function dibujarLateral() {
  const { servidor } = estado;
  const conCuenta = Boolean(servidor.requiere_sesion && servidor.cuenta);
  for (const id of ['#grupo-compartidos', '#nav-palabras', '#nav-compartir', '#nav-telegram', '#caja-usuario']) {
    $(id).hidden = !conCuenta;
  }
  if (!conCuenta) return;
  $('#insignia-telegram').hidden = !servidor.token || servidor.cuenta.telegram;
  const nombre = servidor.cuenta.correo || 'Telegram';
  $('#nombre-usuario').textContent = nombre;
  $('#detalle-usuario').textContent = servidor.cuenta.correo ? 'Cuenta de Google' : 'Entraste con Telegram';
  $('#avatar').textContent = nombre[0].toUpperCase();
  $('#nav-compartidos').replaceChildren(...(servidor.compartidos.length
    ? servidor.compartidos.map((diario) => {
      const enlace = el('a', null, diario.correo);
      enlace.href = `#/compartido/${diario.id}`;
      enlace.dataset.ruta = `compartido/${diario.id}`;
      enlace.title = diario.correo;
      return enlace;
    })
    : [el('p', 'nada', 'Nadie todavía')]));
}

function mostrarRuta() {
  const { servidor } = estado;
  const conCuenta = Boolean(servidor.requiere_sesion && servidor.cuenta);
  const [pedida, id] = location.hash.replace(/^#\/?/, '').split('/');
  const compartido = pedida === 'compartido'
    ? servidor.compartidos.find((d) => String(d.id) === id) || null
    : null;
  let seccion = pedida || 'diario';
  if (!conCuenta || !['compartido', 'palabras', 'compartir', 'telegram'].includes(seccion)
      || (seccion === 'compartido' && !compartido)) {
    seccion = 'diario'; // ruta desconocida, o un diario que ya no te comparten
  }
  const actual = compartido ? `compartido/${compartido.id}` : seccion;
  if (location.hash && location.hash !== `#/${actual}`) history.replaceState(null, '', `#/${actual}`);

  const vista = compartido ? 'diario' : seccion;
  for (const nombre of ['diario', 'palabras', 'compartir', 'telegram']) $(`#vista-${nombre}`).hidden = nombre !== vista;
  for (const enlace of document.querySelectorAll('#lateral a[data-ruta]')) {
    if (enlace.dataset.ruta === actual) enlace.setAttribute('aria-current', 'page');
    else enlace.removeAttribute('aria-current');
  }
  cerrarMenu();
  if (vista === 'telegram') dibujarTelegram();
  if (vista === 'palabras') mostrarPalabras();
  if (vista === 'diario') mostrarDiario(compartido);
}

function mostrarDiario(compartido) {
  const cambio = !estado.diarioListo || (estado.diario?.id ?? null) !== (compartido?.id ?? null);
  const propio = !compartido;
  estado.diario = compartido;
  estado.rol = propio ? 'dueno' : 'lectura';
  $('#titulo-vista').textContent = propio ? 'Mi diario' : `Diario de ${compartido.correo}`;
  $('#aviso-lectura').hidden = propio;
  if (!propio) $('#aviso-lectura').textContent = `Estás viendo el diario de ${compartido.correo} · solo lectura`;
  $('#titulo-rueda').textContent = propio ? 'Tu rueda' : 'Su rueda';
  $('#texto-resaltar').textContent = propio ? 'Resaltar lo que sentí' : 'Resaltar lo que sintió';
  $('#titulo-frecuentes').textContent = propio ? 'Lo que más sentiste' : 'Lo que más sintió';
  $('#titulo-registros').textContent = propio ? 'Tus registros' : 'Sus registros';
  ajustarEtiquetas(); // si la rueda se dibujó mientras estaba oculta, no se pudo medir
  if (!cambio) return;
  estado.diarioListo = true;
  estado.filtro = null;
  estado.firma = '';
  estado.registros = [];
  dibujar();
  cargarRegistros();
}

async function actualizarCuenta() {
  const servidor = await (await fetch('/api/estado')).json();
  if (servidor.requiere_sesion && !servidor.sesion) {
    clearInterval(estado.refresco);
    mostrarAcceso(servidor);
    return false;
  }
  estado.servidor = servidor;
  dibujarLateral();
  mostrarRuta();
  return true;
}

function conectarMenu() {
  $('#abrir-menu').addEventListener('click', abrirMenu);
  $('#velo').addEventListener('click', cerrarMenu);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') cerrarMenu(); });
  window.addEventListener('hashchange', mostrarRuta);
}

async function iniciar() {
  const servidor = await (await fetch('/api/estado')).json();
  if (servidor.requiere_sesion && !servidor.sesion) {
    mostrarAcceso(servidor);
    return;
  }
  estado.servidor = servidor;
  $('#app').hidden = false;
  dibujarLateral();
  if (servidor.requiere_sesion && servidor.cuenta) iniciarCompartir(servidor.url);
  if (servidor.cuenta) {
    iniciarPalabras();
    iniciarPanelEmocion();
    iniciarEditorRegistro();
    iniciarEditorNombre();
  }
  estado.ruedaBase = await (await fetch('/api/rueda')).json();
  aplicarNombres();
  dibujarRueda();
  conectarRueda();
  conectarControles();
  conectarMenu();
  mostrarRuta();
}

iniciar();
