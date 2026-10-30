// La campanita: abre el panel, marca todo como leído y revisa la cifra cada minuto (solo con la pestaña visible).
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

  async function revisar() {
    if (document.hidden) return;
    try {
      const r = await fetch(raiz.dataset.contador, { credentials: 'same-origin' });
      if (r.status === 401) { location.reload(); return; }  // la sesión se cerró por inactividad: mostrar el acceso
      if (r.ok) pintar((await r.json()).sin_leer);
    } catch (e) { /* sin conexión: se intenta en el siguiente minuto */ }
  }
  pintar(parseInt(cifra.hidden ? '0' : cifra.textContent, 10) || 0);
  setInterval(revisar, 60000);
  document.addEventListener('visibilitychange', revisar);
})();
