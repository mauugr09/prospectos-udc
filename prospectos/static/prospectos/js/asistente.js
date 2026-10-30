// Asistente: panel lateral de conversación. Lo que responde la IA se muestra como texto (nunca como HTML).
(function () {
  const boton = document.getElementById('as-abrir');
  if (!boton || boton.dataset.listo) return;
  boton.dataset.listo = '1';
  const ficha = (location.pathname.match(/\/admin\/prospectos\/prospecto\/(\d+)\/change\//) || [])[1] || null;

  // ---------------------------------------------------------------- la mascota (Kuali): solo reacciona, nunca interrumpe
  const tarjetaKuali = document.getElementById('km');
  const NOMBRE = (tarjetaKuali && tarjetaKuali.dataset.nombre) || 'Kuali';
  const FRASES = { reposo: '¿En qué te ayudo?', pensando: 'Pensando…', contento: '¡Listo!', preocupado: 'Algo salió mal', dormido: 'Zzz…' };
  let avisosSinLeer = 0, estadoFijo = null, temporizador = null, ultimoMovimiento = Date.now();
  const mascotas = () => document.querySelectorAll('svg.kuali');
  function pintarMascota(estado) {
    mascotas().forEach((svg) => {
      ['pensando', 'contento', 'avisando', 'preocupado', 'dormido'].forEach((e) => svg.classList.toggle(`k-${e}-on`, e === estado));
    });
    if (tarjetaKuali) {
      const txt = tarjetaKuali.querySelector('small');
      tarjetaKuali.classList.toggle('avisando', estado === 'avisando');
      txt.textContent = estado === 'avisando' ? `Tienes ${avisosSinLeer} aviso${avisosSinLeer === 1 ? '' : 's'}` : (FRASES[estado] || FRASES.reposo);
    }
  }
  const base = () => (avisosSinLeer ? 'avisando' : 'reposo');
  // estado(e) fija un estado (p. ej. pensando) hasta que se llame con null; estado(e, ms) lo muestra un momento.
  function estado(e, ms) {
    clearTimeout(temporizador);
    if (ms) { pintarMascota(e); temporizador = setTimeout(() => pintarMascota(estadoFijo || base()), ms); return; }
    estadoFijo = e;
    pintarMascota(e || base());
  }
  document.addEventListener('avisos:cifra', (ev) => { avisosSinLeer = ev.detail || 0; if (!estadoFijo) pintarMascota(base()); });
  const cifraInicial = document.querySelector('.av-cifra');
  avisosSinLeer = cifraInicial && !cifraInicial.hidden ? parseInt(cifraInicial.textContent, 10) || 0 : 0;
  pintarMascota(base());
  // Parpadea de vez en cuando y se duerme tras 5 minutos sin que nadie mueva el mouse ni escriba.
  (function parpadear() {
    setTimeout(() => {
      if (!document.hidden) mascotas().forEach((svg) => { svg.classList.add('parpadea'); setTimeout(() => svg.classList.remove('parpadea'), 140); });
      parpadear();
    }, 2800 + Math.random() * 4200);
  })();
  ['mousemove', 'keydown', 'scroll', 'click'].forEach((t) => addEventListener(t, () => {
    ultimoMovimiento = Date.now();
    if (estadoFijo === 'dormido') estado(null);
  }, { passive: true }));
  setInterval(() => { if (!estadoFijo && Date.now() - ultimoMovimiento > 5 * 60000) estado('dormido'); }, 30000);
  // Si la tarjeta del menú no se ve (menú cerrado, celular u oculta), queda el botón de arriba.
  let oculta = false;
  try { oculta = localStorage.getItem('kuali-oculto') === '1'; } catch (e) { /* sin almacenamiento */ }
  function acomodar() {
    if (tarjetaKuali) tarjetaKuali.hidden = oculta;
    const visible = tarjetaKuali && !oculta && tarjetaKuali.offsetParent !== null && tarjetaKuali.getBoundingClientRect().width > 0;
    boton.classList.toggle('con-kuali-visible', !!visible);
  }
  addEventListener('resize', acomodar);
  new MutationObserver(acomodar).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  setTimeout(acomodar, 50); setTimeout(acomodar, 600);

  const SUGERENCIAS = ficha
    ? ['Prepara la llamada con este aspirante', 'Escribe un WhatsApp para invitarlo al open house', '¿En qué no coincide con su familia?']
    : ['¿Cuántos aspirantes llegaron este mes por plantel?', '¿Qué carreras piden más en Tultepec?', '¿Qué visitas hay las próximas 2 semanas?',
       '¿Cómo uno a una familia con su alumno?'];

  const panel = document.createElement('aside');
  panel.id = 'as-panel';
  panel.className = 'as-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', 'Asistente');
  panel.hidden = true;
  panel.innerHTML = `
    <header class="as-cabeza">
      <span class="as-logo-kuali" aria-hidden="true"></span>
      <div><h2></h2><small>${ficha ? 'Sobre la ficha abierta, sin su nombre' : 'Tu asistente: cifras, ayuda y propuestas'}</small></div>
      <button type="button" class="as-icono" data-nueva title="Nueva conversación" aria-label="Nueva conversación"><span class="material-symbols-outlined">edit_square</span></button>
      <button type="button" class="as-icono" data-cerrar title="Cerrar" aria-label="Cerrar"><span class="material-symbols-outlined">close</span></button>
    </header>
    <div class="as-hilo" aria-live="polite"></div>
    <form class="as-escribir">
      <textarea rows="1" placeholder="Pregunta algo…" aria-label="Tu pregunta" maxlength="1500"></textarea>
      <button type="submit" class="as-enviar" aria-label="Enviar"><span class="material-symbols-outlined">arrow_upward</span></button>
    </form>
    <p class="as-pie">No escribas nombres ni teléfonos: no los recibe. Puede equivocarse: revisa antes de confirmar.
      <button type="button" class="as-ocultar"></button></p>`;
  document.body.appendChild(panel);
  panel.querySelector('h2').textContent = NOMBRE;
  panel.setAttribute('aria-label', NOMBRE);
  const original = document.querySelector('#km svg.kuali') || boton.querySelector('svg.kuali');
  if (original) panel.querySelector('.as-logo-kuali').appendChild(original.cloneNode(true));
  const ocultar = panel.querySelector('.as-ocultar');
  const textoOcultar = () => { ocultar.textContent = oculta ? `Mostrar a ${NOMBRE} en el menú` : `Ocultar a ${NOMBRE} del menú`; };
  textoOcultar();
  ocultar.onclick = () => {
    oculta = !oculta;
    try { localStorage.setItem('kuali-oculto', oculta ? '1' : '0'); } catch (e) { /* sin almacenamiento */ }
    textoOcultar(); acomodar();
  };
  if (tarjetaKuali) tarjetaKuali.querySelector('button').addEventListener('click', () => (panel.hidden ? abrir() : cerrar()));
  const hilo = panel.querySelector('.as-hilo');
  const campo = panel.querySelector('textarea');
  const formulario = panel.querySelector('form');

  function bienvenida() {
    hilo.innerHTML = '';
    const b = el('div', 'as-bienvenida');
    b.appendChild(el('p', '', ficha ? `Hola, soy ${NOMBRE}. Puedo preparar la llamada o un mensaje para este aspirante. Su nombre lo pongo al final, en esta computadora.`
      : `Hola, soy ${NOMBRE}. Pregúntame cifras, cómo hacer algo en el programa, o pídeme que prepare una visita o asigne aspirantes. Tú confirmas antes de que cambie algo.`));
    if (avisosSinLeer) {
      const av = el('button', 'as-sugerencia as-sugerencia-aviso', `Ver mis ${avisosSinLeer} aviso${avisosSinLeer === 1 ? '' : 's'} sin leer`);
      av.type = 'button';
      av.onclick = () => { cerrar(); document.querySelector('.av-boton')?.click(); };
      b.appendChild(av);
    }
    const lista = el('div', 'as-sugerencias');
    SUGERENCIAS.forEach((s) => { const c = el('button', 'as-sugerencia', s); c.type = 'button'; c.onclick = () => enviar(s); lista.appendChild(c); });
    b.appendChild(lista);
    hilo.appendChild(b);
  }

  function el(tag, clase, txt) { const e = document.createElement(tag); if (clase) e.className = clase; if (txt != null) e.textContent = txt; return e; }

  // Formato mínimo y seguro: **negritas**, listas con «- » o «1. » y párrafos. Todo por textContent.
  function formatear(texto) {
    const cont = el('div', 'as-texto');
    let lista = null;
    for (const linea of texto.split('\n')) {
      const item = linea.match(/^\s*(?:[-•*]|\d+[.)])\s+(.*)/);
      if (item) {
        if (!lista) { lista = el(/^\s*\d/.test(linea) ? 'ol' : 'ul'); cont.appendChild(lista); }
        lista.appendChild(enLinea(el('li'), item[1]));
      } else if (linea.trim()) { lista = null; cont.appendChild(enLinea(el('p'), linea.replace(/^#+\s*/, ''))); }
      else lista = null;
    }
    return cont;
  }
  function enLinea(nodo, txt) {
    txt.split(/(\*\*[^*]+\*\*)/).forEach((parte) => {
      if (/^\*\*[^*]+\*\*$/.test(parte)) nodo.appendChild(el('b', '', parte.slice(2, -2)));
      else if (parte) nodo.appendChild(document.createTextNode(parte));
    });
    return nodo;
  }

  function burbuja(quien, contenido) {
    const b = el('div', 'as-msg ' + quien);
    if (typeof contenido === 'string') b.appendChild(quien === 'yo' ? el('p', '', contenido) : formatear(contenido));
    else b.appendChild(contenido);
    hilo.appendChild(b);
    hilo.scrollTop = hilo.scrollHeight;
    return b;
  }

  function botonCopiar(b, texto) {
    const c = el('button', 'as-copiar');
    c.type = 'button';
    c.innerHTML = '<span class="material-symbols-outlined">content_copy</span>';
    c.appendChild(document.createTextNode('Copiar'));
    c.onclick = async () => { try { await navigator.clipboard.writeText(texto); c.lastChild.textContent = 'Copiado'; } catch (e) { /* sin portapapeles */ } };
    b.appendChild(c);
  }

  function tarjeta(p) {
    const t = el('div', 'as-propuesta');
    const cab = el('div', 'as-propuesta-cabeza');
    cab.appendChild(el('span', 'material-symbols-outlined', p.icono));
    cab.appendChild(el('b', '', p.titulo));
    t.appendChild(cab);
    const ul = el('ul');
    p.lineas.slice(0, 50).forEach((l) => ul.appendChild(el('li', '', l)));
    t.appendChild(ul);
    const acciones = el('div', 'as-propuesta-acciones');
    const si = el('button', 'udc-btn chico', 'Confirmar'); si.type = 'button';
    const no = el('button', 'udc-btn chico secundario', 'Descartar'); no.type = 'button';
    acciones.append(si, no);
    t.appendChild(acciones);
    const decidir = async (decision) => {
      si.disabled = no.disabled = true;
      const datos = new FormData(); datos.append('decision', decision);
      const r = await fetch(boton.dataset.confirmar.replace('PID', p.id), { method: 'POST', body: datos, credentials: 'same-origin',
        headers: { 'X-CSRFToken': boton.dataset.csrf, 'X-Requested-With': 'fetch' } });
      const j = await r.json().catch(() => ({ mensaje: 'No se pudo.' }));
      acciones.replaceWith(el('p', 'as-propuesta-resultado ' + (j.ok && decision === 'si' ? 'hecho' : ''), j.mensaje));
      if (j.ok && decision === 'si') estado('contento', 2200); else if (!j.ok) estado('preocupado', 3000);
    };
    si.onclick = () => decidir('si');
    no.onclick = () => decidir('no');
    return t;
  }

  let ocupado = false;
  async function enviar(texto) {
    texto = (texto || '').trim();
    if (!texto || ocupado) return;
    ocupado = true;
    hilo.querySelector('.as-bienvenida')?.remove();
    burbuja('yo', texto);
    campo.value = ''; ajustar();
    const pensando = burbuja('ia', el('div', 'as-pensando', 'Consultando…'));
    estado('pensando');
    try {
      const r = await fetch(boton.dataset.url, { method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRFToken': boton.dataset.csrf, 'X-Requested-With': 'fetch', 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensaje: texto, ficha }) });
      if (r.status === 401) { location.reload(); return; }
      const j = await r.json().catch(() => ({ ok: false, mensaje: 'Respuesta inesperada del programa.' }));
      pensando.remove();
      estado(null);
      if (!j.ok) { estado('preocupado', 3500); burbuja('aviso ' + (j.tipo || ''), j.mensaje); return; }
      const b = burbuja('ia', j.texto || '(sin respuesta)');
      if (j.consulto && j.consulto.length) b.appendChild(el('small', 'as-fuente', 'Consultó: ' + j.consulto.map(nombreHerramienta).join(', ')));
      if (ficha && /whatsapp|mensaje|correo/i.test(texto)) botonCopiar(b, j.texto);
      (j.propuestas || []).forEach((p) => hilo.appendChild(tarjeta(p)));
      hilo.scrollTop = hilo.scrollHeight;
    } catch (e) {
      pensando.remove();
      estado(null); estado('preocupado', 3500);
      burbuja('aviso', 'Sin conexión con la PC del sistema.');
    } finally { ocupado = false; campo.focus(); }
  }
  const NOMBRES_H = { consultar_cifras: 'cifras', embudo: 'embudo', consultar_visitas: 'visitas', buscar_ayuda: 'manual', manual: 'manual',
    perfil_del_aspirante: 'perfil sin nombre', proponer_crear_visita: 'propuesta', proponer_crear_actividad: 'propuesta', proponer_asignar_asesor: 'propuesta' };
  const nombreHerramienta = (n) => NOMBRES_H[n] || n;

  function ajustar() { campo.style.height = 'auto'; campo.style.height = Math.min(campo.scrollHeight, 140) + 'px'; }
  campo.addEventListener('input', ajustar);
  campo.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(campo.value); } });
  formulario.addEventListener('submit', (e) => { e.preventDefault(); enviar(campo.value); });

  function abrir(pregunta) {
    panel.hidden = false; boton.setAttribute('aria-expanded', 'true');
    if (!hilo.childElementCount) bienvenida();
    if (pregunta) enviar(pregunta); else campo.focus();
  }
  function cerrar() { panel.hidden = true; boton.setAttribute('aria-expanded', 'false'); boton.focus(); }
  boton.addEventListener('click', () => (panel.hidden ? abrir() : cerrar()));
  panel.querySelector('[data-cerrar]').onclick = cerrar;
  panel.querySelector('[data-nueva]').onclick = async () => {
    await fetch(boton.dataset.nueva, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': boton.dataset.csrf } });
    bienvenida(); campo.focus();
  };
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !panel.hidden) cerrar(); });
  // Botones de otras pantallas (p. ej. «Preparar llamada» en la ficha): data-asistente="pregunta".
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-asistente]');
    if (b) { e.preventDefault(); abrir(b.dataset.asistente); }
  });
})();
