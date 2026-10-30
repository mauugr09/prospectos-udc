// La campanita: abre el panel, marca todo como leído y revisa cada 30 segundos (también con la pestaña en segundo plano).
// Cuando llega un aviso nuevo: ventanita flotante, un sonido corto (si la persona no lo apagó en Mi perfil),
// el título de la pestaña parpadea si no está a la vista y, si se dio permiso, un aviso del sistema operativo.
(function () {
  const raiz = document.getElementById('av-campana');
  if (!raiz || raiz.dataset.listo) return;
  raiz.dataset.listo = '1';
  const boton = raiz.querySelector('.av-boton');
  const panel = raiz.querySelector('.av-panel');
  const cifra = raiz.querySelector('.av-cifra');
  const tituloBase = document.title.replace(/^\(\d+\+?\) /, '');

  function pintar(n) {
    cifra.hidden = !n;
    cifra.textContent = n > 99 ? '99+' : n;
    boton.setAttribute('aria-label', n ? `Avisos: ${n} sin leer` : 'Avisos');
    document.title = n ? `(${n}) ${tituloBase}` : tituloBase;
    document.dispatchEvent(new CustomEvent('avisos:cifra', { detail: n }));  // la mascota reacciona
  }

  function cerrar() {
    panel.hidden = true;
    boton.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', fuera, true);
    document.removeEventListener('keydown', escape);
  }
  function fuera(e) { if (!raiz.contains(e.target)) cerrar(); }
  function escape(e) { if (e.key === 'Escape') { cerrar(); boton.focus(); } }

  async function abrir() {
    panel.hidden = false;
    boton.setAttribute('aria-expanded', 'true');
    document.addEventListener('click', fuera, true);
    document.addEventListener('keydown', escape);
    if (!panel.innerHTML.trim()) panel.innerHTML = '<p class="av-cargando">Cargando…</p>';
    try {
      const r = await fetch(raiz.dataset.panel, { credentials: 'same-origin' });
      if (r.ok) panel.innerHTML = await r.text();
    } catch (e) { panel.innerHTML = '<p class="av-cargando">No se pudo cargar. Revisa la conexión con la PC del sistema.</p>'; }
  }

  boton.addEventListener('click', () => (panel.hidden ? abrir() : cerrar()));

  panel.addEventListener('click', async (e) => {
    const b = e.target.closest('.av-leer-todo');
    if (!b) return;
    b.disabled = true;
    const r = await fetch(raiz.dataset.leer, { method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRFToken': raiz.dataset.csrf, 'X-Requested-With': 'fetch' } });
    if (r.ok) {
      pintar(0);
      panel.querySelectorAll('.av-nuevo').forEach((li) => li.classList.remove('av-nuevo'));
      panel.querySelectorAll('.av-punto').forEach((p) => p.remove());
      b.remove();
    } else b.disabled = false;
  });

  // ------------------------------------------------------------------ avisos nuevos: ventanita, sonido y título
  const CLAVE = 'avisos-visto:' + (raiz.dataset.usuario || '');
  let visto = null;
  try { visto = parseInt(localStorage.getItem(CLAVE) || '', 10) || null; } catch (e) { /* sin almacenamiento */ }
  const recordar = (m) => { visto = m; try { localStorage.setItem(CLAVE, String(m)); } catch (e) { /* nada */ } };

  let audio = null;
  const desbloquear = () => {  // los navegadores solo dejan sonar después de un clic o una tecla
    if (!audio) { try { audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { audio = null; } }
    if (audio && audio.state === 'suspended') audio.resume();
  };
  ['pointerdown', 'keydown'].forEach((t) => addEventListener(t, desbloquear, { capture: true, passive: true }));
  function sonar() {
    if (raiz.dataset.sonido !== '1' || !audio || audio.state !== 'running') return;
    const t = audio.currentTime;
    [[880, 0], [1318.5, 0.12]].forEach(([f, d]) => {  // dos notas suaves (La5 → Mi6)
      const o = audio.createOscillator(), g = audio.createGain();
      o.type = 'sine'; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t + d);
      g.gain.exponentialRampToValueAtTime(0.18, t + d + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.45);
      o.connect(g).connect(audio.destination); o.start(t + d); o.stop(t + d + 0.5);
    });
  }

  let pila = document.getElementById('av-flotantes');
  if (!pila) {
    pila = document.createElement('div');
    pila.id = 'av-flotantes'; pila.className = 'av-flotantes';
    pila.setAttribute('role', 'region'); pila.setAttribute('aria-label', 'Avisos nuevos'); pila.setAttribute('aria-live', 'polite');
    document.body.appendChild(pila);
  }
  function flotante(a) {
    const el = document.createElement('div');
    el.className = `av-flotante av-${a.tipo}`;
    el.innerHTML = '<span class="av-icono material-symbols-outlined" aria-hidden="true"></span>' +
      '<div class="av-flotante-texto"><b></b><small></small></div>' +
      '<a class="av-flotante-ver">Ver</a><button type="button" class="av-flotante-x" aria-label="Cerrar"><span class="material-symbols-outlined">close</span></button>';
    el.querySelector('.av-icono').textContent = a.icono;
    el.querySelector('b').textContent = a.titulo;
    el.querySelector('small').textContent = a.detalle || '';
    el.querySelector('.av-flotante-ver').href = a.url;
    const quitar = () => { el.classList.add('saliendo'); setTimeout(() => el.remove(), 300); };
    el.querySelector('.av-flotante-x').onclick = quitar;
    let reloj = setTimeout(quitar, 12000);
    el.addEventListener('mouseenter', () => clearTimeout(reloj));
    el.addEventListener('mouseleave', () => { reloj = setTimeout(quitar, 6000); });
    pila.prepend(el);
    while (pila.children.length > 3) pila.lastElementChild.remove();
  }

  let parpadeo = null;
  function llamarLaAtencion(n) {
    if (!document.hidden || parpadeo) return;
    let i = 0;
    parpadeo = setInterval(() => { document.title = (i++ % 2) ? `(${n}) ${tituloBase}` : `🔔 Aviso nuevo · ${tituloBase}`; }, 1200);
  }
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && parpadeo) { clearInterval(parpadeo); parpadeo = null; pintar(parseInt(cifra.textContent, 10) || 0); }
  });

  function nuevos(datos) {
    const recientes = datos.recientes || [];
    const mayor = recientes.reduce((m, a) => Math.max(m, a.marca), 0);
    if (visto === null) { recordar(mayor); return; }  // primera vez en este navegador: no se anuncia lo viejo
    const llegaron = recientes.filter((a) => a.marca > visto).reverse();
    if (!llegaron.length) return;
    recordar(mayor);
    llegaron.forEach(flotante);
    sonar();
    llamarLaAtencion(datos.sin_leer);
    if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
      const a = llegaron[llegaron.length - 1];
      const n = new Notification(a.titulo, { body: a.detalle || '', tag: 'prospectos-avisos', icon: raiz.dataset.icono || undefined });
      n.onclick = () => { window.focus(); location.href = a.url; };
    }
  }

  async function revisar() {
    try {
      const r = await fetch(raiz.dataset.contador, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (r.status === 401) { if (!document.hidden) location.reload(); return; }  // sesión cerrada por inactividad
      if (r.ok) { const d = await r.json(); pintar(d.sin_leer); nuevos(d); }
    } catch (e) { /* sin conexión: se intenta en la siguiente vuelta */ }
  }
  pintar(parseInt(cifra.hidden ? '0' : cifra.textContent, 10) || 0);
  revisar();
  setInterval(revisar, 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) revisar(); });
})();
