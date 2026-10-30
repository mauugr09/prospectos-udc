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
  // Se guarda en «Mi perfil» (sigue a la persona en cualquier computadora).
  let oculta = !!(tarjetaKuali && tarjetaKuali.dataset.oculto === '1');
  function acomodar() {
    if (tarjetaKuali) tarjetaKuali.hidden = oculta;
    const visible = tarjetaKuali && !oculta && tarjetaKuali.offsetParent !== null && tarjetaKuali.getBoundingClientRect().width > 0;
    boton.classList.toggle('con-kuali-visible', !!visible);
  }
  addEventListener('resize', acomodar);
  new MutationObserver(acomodar).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  setTimeout(acomodar, 50); setTimeout(acomodar, 600);

  const IDEAS = ficha
    ? [['Preparar el contacto', ['Prepara la llamada con este aspirante', 'Escribe un WhatsApp para invitarlo al open house',
        '¿En qué no coincide con su familia y cómo lo abordo?']]]
    : [['Qué hago hoy', ['¿Qué es lo más urgente hoy?', '¿Cuántos listos para inscribirse nadie ha llamado?']],
       ['Entender cómo vamos', ['¿Cómo vamos este mes contra el anterior, por plantel?', '¿En qué etapa del embudo se nos quedan más?',
         '¿Qué carreras piden en cada plantel?']],
       ['Mejorar resultados', ['¿Qué canal convierte mejor: WhatsApp o correo?', '¿Qué visitas rindieron más registros por costo?',
         '¿Qué prepas mandan aspirantes que sí avanzan?']],
       ['Cómo se hace', ['¿Cómo uno a una familia con su alumno?', '¿Qué significa Esperando permiso?']]];

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
    <p class="as-pie">Funciona en esta computadora, sin internet. Revisa lo que entendió y confirma antes de que cambie algo.
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
    textoOcultar(); acomodar();
    if (tarjetaKuali && tarjetaKuali.dataset.perfil) {
      const datos = new FormData();
      datos.append('accion', 'kuali'); datos.append('oculto', oculta ? '1' : '0');
      fetch(tarjetaKuali.dataset.perfil, { method: 'POST', body: datos, credentials: 'same-origin',
        headers: { 'X-CSRFToken': boton.dataset.csrf, 'X-Requested-With': 'fetch' } }).catch(() => {});
    }
  };
  if (tarjetaKuali) tarjetaKuali.querySelector('button').addEventListener('click', () => (panel.hidden ? abrir() : cerrar()));
  const hilo = panel.querySelector('.as-hilo');
  const campo = panel.querySelector('textarea');
  const formulario = panel.querySelector('form');

  function bienvenida() {
    hilo.innerHTML = '';
    const b = el('div', 'as-bienvenida');
    b.appendChild(el('p', '', ficha ? `Hola, soy ${NOMBRE}. Puedo preparar la llamada, un WhatsApp o ver en qué no coincide con su familia.`
      : `Hola, soy ${NOMBRE}. Pregúntame cifras, cómo hacer algo en el programa, o pídeme que prepare una visita o asigne aspirantes. Tú confirmas antes de que cambie algo.`));
    if (avisosSinLeer) {
      const av = el('button', 'as-sugerencia as-sugerencia-aviso', `Ver mis ${avisosSinLeer} aviso${avisosSinLeer === 1 ? '' : 's'} sin leer`);
      av.type = 'button';
      av.onclick = () => { cerrar(); document.querySelector('.av-boton')?.click(); };
      b.appendChild(av);
    }
    const lista = el('div', 'as-sugerencias');
    IDEAS.forEach(([titulo, preguntas]) => {
      lista.appendChild(el('small', 'as-ideas-titulo', titulo));
      preguntas.forEach((s) => { const c = el('button', 'as-sugerencia', s); c.type = 'button'; c.onclick = () => enviar(s); lista.appendChild(c); });
    });
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
    txt.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\([^)\s]+\))/).forEach((parte) => {
      const enlace = parte.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
      if (/^\*\*[^*]+\*\*$/.test(parte)) nodo.appendChild(el('b', '', parte.slice(2, -2)));
      else if (enlace) {
        if (esInterno(enlace[2])) { const a = el('a', 'as-enlace', enlace[1]); a.href = enlace[2]; nodo.appendChild(a); }
        else nodo.appendChild(document.createTextNode(enlace[1]));  // la IA no puede mandar a sitios de fuera
      } else if (parte) nodo.appendChild(document.createTextNode(parte));
    });
    return nodo;
  }
  const esInterno = (u) => typeof u === 'string' && u.startsWith('/admin/') && !u.includes('//');

  // Gráfica con los números del sistema (no del texto de la IA).
  function grafica(v) {
    const caja = el('div', 'as-grafica');
    const cab = el('div', 'as-grafica-cabeza');
    cab.appendChild(el('b', '', v.titulo || ''));
    if (v.total != null) cab.appendChild(el('span', '', `Total ${v.total}` + (v.anterior != null ? ` · antes ${v.anterior}` : '')));
    caja.appendChild(cab);
    const max = Math.max(1, ...v.filas.map((f) => Math.max(f.valor || 0, f.antes || 0)));
    v.filas.forEach((f) => {
      const fila = el(f.enlace && esInterno(f.enlace) ? 'a' : 'div', 'as-barra');
      if (fila.tagName === 'A') fila.href = f.enlace;
      fila.appendChild(el('span', 'as-barra-etiqueta', f.etiqueta));
      const pista = el('span', 'as-barra-pista');
      if (v.tipo !== 'pendientes') {
        const ancho = v.tipo === 'porcentajes' ? (f.valor || 0) : ((f.valor || 0) / max * 100);
        const relleno = el('i', f.confiable === false ? 'poco' : ''); relleno.style.width = Math.max(ancho, f.valor ? 2 : 0) + '%';
        pista.appendChild(relleno);
        if (f.antes != null) { const fantasma = el('em'); fantasma.style.left = (f.antes / max * 100) + '%'; fantasma.title = `Antes: ${f.antes}`; pista.appendChild(fantasma); }
      }
      fila.appendChild(pista);
      const valor = f.valor == null ? 'menos de 3' : (v.tipo === 'porcentajes' ? `${f.valor} %` : String(f.valor));
      fila.appendChild(el('span', 'as-barra-valor', valor + (v.tipo === 'porcentajes' && f.n ? ` de ${f.n}` : '')));
      caja.appendChild(fila);
    });
    if (v.tipo === 'barras' && v.filas.some((f) => f.antes != null)) caja.appendChild(el('small', 'as-grafica-nota', 'La rayita marca el periodo anterior.'));
    if (v.tipo === 'porcentajes' && v.filas.some((f) => f.confiable === false)) caja.appendChild(el('small', 'as-grafica-nota', 'En gris: muy pocos casos para confiar en el porcentaje.'));
    if (v.enlace && esInterno(v.enlace)) { const a = el('a', 'as-enlace as-grafica-ver', 'Ver la lista'); a.href = v.enlace; caja.appendChild(a); }
    return caja;
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
    hilo.querySelectorAll('.as-siguientes').forEach((x) => x.remove());
    const pensando = burbuja('ia', el('div', 'as-pensando', 'Revisando los datos…'));
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
      if (j.entendi) b.insertBefore(el('small', 'as-entendi', 'Entendí: ' + j.entendi), b.firstChild);
      if (j.visual && j.visual.filas && j.visual.filas.length) b.appendChild(grafica(j.visual));
      if (j.calculos && j.calculos.length) {
        const det = el('details', 'as-calculo');
        det.appendChild(el('summary', '', 'Cómo lo calculé'));
        j.calculos.forEach((c) => {
          const p = el('p', '', c.que);
          if (c.enlace && esInterno(c.enlace)) { p.appendChild(document.createTextNode(' ')); const a = el('a', 'as-enlace', 'Ver esos aspirantes'); a.href = c.enlace; p.appendChild(a); }
          det.appendChild(p);
        });
        b.appendChild(det);
      }
      if (ficha && /whatsapp|mensaje|correo/i.test(texto)) botonCopiar(b, j.texto);
      (j.propuestas || []).forEach((p) => hilo.appendChild(tarjeta(p)));
      if (j.siguientes && j.siguientes.length) {
        const sig = el('div', 'as-siguientes');
        j.siguientes.forEach((q) => { const c = el('button', 'as-siguiente', q); c.type = 'button'; c.onclick = () => { sig.remove(); enviar(q); }; sig.appendChild(c); });
        hilo.appendChild(sig);
      }
      hilo.scrollTop = hilo.scrollHeight;
    } catch (e) {
      pensando.remove();
      estado(null); estado('preocupado', 3500);
      burbuja('aviso', 'Sin conexión con la PC del sistema.');
    } finally { ocupado = false; campo.focus(); }
  }
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
