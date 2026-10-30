// Asistente: panel lateral de conversación. Lo que responde la IA se muestra como texto (nunca como HTML).
(function () {
  const boton = document.getElementById('as-abrir');
  if (!boton || boton.dataset.listo) return;
  boton.dataset.listo = '1';
  const ficha = (location.pathname.match(/\/admin\/prospectos\/prospecto\/(\d+)\/change\//) || [])[1] || null;

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
      <span class="as-logo material-symbols-outlined" aria-hidden="true">auto_awesome</span>
      <div><h2>Asistente</h2><small>${ficha ? 'Sobre la ficha abierta, sin su nombre' : 'Cifras, ayuda y propuestas'}</small></div>
      <button type="button" class="as-icono" data-nueva title="Nueva conversación" aria-label="Nueva conversación"><span class="material-symbols-outlined">edit_square</span></button>
      <button type="button" class="as-icono" data-cerrar title="Cerrar" aria-label="Cerrar"><span class="material-symbols-outlined">close</span></button>
    </header>
    <div class="as-hilo" aria-live="polite"></div>
    <form class="as-escribir">
      <textarea rows="1" placeholder="Pregunta algo…" aria-label="Tu pregunta" maxlength="1500"></textarea>
      <button type="submit" class="as-enviar" aria-label="Enviar"><span class="material-symbols-outlined">arrow_upward</span></button>
    </form>
    <p class="as-pie">No escribas nombres ni teléfonos: el asistente no los recibe. Puede equivocarse: revisa antes de confirmar.</p>`;
  document.body.appendChild(panel);
  const hilo = panel.querySelector('.as-hilo');
  const campo = panel.querySelector('textarea');
  const formulario = panel.querySelector('form');

  function bienvenida() {
    hilo.innerHTML = '';
    const b = el('div', 'as-bienvenida');
    b.appendChild(el('p', '', ficha ? 'Puedo preparar la llamada o un mensaje para este aspirante. Pongo su nombre al final, en esta computadora.'
      : 'Pregúntame cifras, cómo hacer algo en el programa, o pídeme que prepare una visita o asigne aspirantes. Tú confirmas antes de que cambie algo.'));
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
    try {
      const r = await fetch(boton.dataset.url, { method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRFToken': boton.dataset.csrf, 'X-Requested-With': 'fetch', 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensaje: texto, ficha }) });
      if (r.status === 401) { location.reload(); return; }
      const j = await r.json().catch(() => ({ ok: false, mensaje: 'Respuesta inesperada del programa.' }));
      pensando.remove();
      if (!j.ok) { burbuja('aviso ' + (j.tipo || ''), j.mensaje); return; }
      const b = burbuja('ia', j.texto || '(sin respuesta)');
      if (j.consulto && j.consulto.length) b.appendChild(el('small', 'as-fuente', 'Consultó: ' + j.consulto.map(nombreHerramienta).join(', ')));
      if (ficha && /whatsapp|mensaje|correo/i.test(texto)) botonCopiar(b, j.texto);
      (j.propuestas || []).forEach((p) => hilo.appendChild(tarjeta(p)));
      hilo.scrollTop = hilo.scrollHeight;
    } catch (e) {
      pensando.remove();
      burbuja('aviso', 'Sin conexión con la PC del sistema.');
    } finally { ocupado = false; campo.focus(); }
  }
  const NOMBRES = { consultar_cifras: 'cifras', embudo: 'embudo', consultar_visitas: 'visitas', buscar_ayuda: 'manual', manual: 'manual',
    perfil_del_aspirante: 'perfil sin nombre', proponer_crear_visita: 'propuesta', proponer_crear_actividad: 'propuesta', proponer_asignar_asesor: 'propuesta' };
  const nombreHerramienta = (n) => NOMBRES[n] || n;

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
