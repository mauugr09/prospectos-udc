/*
 * Cerrar sesión con confirmación, y el aviso antes del cierre por inactividad.
 * - El botón «Cerrar sesión» del menú abre una ventana: Enter confirma, Esc cancela.
 * - Mover el mouse, escribir o desplazarse cuenta como uso aunque no se abra otra página (se avisa al servidor
 *   cada pocos minutos). Las pestañas del mismo navegador comparten la hora del último uso.
 * - Un minuto antes del límite: «¿Sigues ahí?». Al llegar al límite la página se va a «Sesión cerrada», para que
 *   una computadora desatendida no siga mostrando datos (el servidor también la cierra por su cuenta).
 */
(function () {
  const dlg = document.getElementById('sl-dialogo');
  if (!dlg) return;
  const forma = document.getElementById('sl-forma');
  const motivo = document.getElementById('sl-motivo');
  const normal = dlg.querySelector('.sl-normal'), inactivo = dlg.querySelector('.sl-inactivo');
  const cancelar = document.getElementById('sl-cancelar'), cuenta = document.getElementById('sl-cuenta');
  const minutos = parseInt(dlg.dataset.minutos || '0', 10);
  let modo = null;

  function abrir(m) {
    modo = m;
    normal.hidden = m !== 'normal'; inactivo.hidden = m !== 'inactivo';
    cancelar.textContent = m === 'inactivo' ? 'Seguir trabajando' : 'Cancelar';
    if (!dlg.open) dlg.showModal();
    (m === 'inactivo' ? cancelar : document.getElementById('sl-confirmar')).focus();
  }
  function cerrarDialogo() { if (dlg.open) dlg.close(); modo = null; }

  // El menú de la cuenta (y cualquier otro formulario de salida) abre la ventana en vez de salir directo.
  document.addEventListener('submit', (e) => {
    const f = e.target;
    if (f === forma || !(f instanceof HTMLFormElement)) return;
    if (f.id === 'logout-form' || /\/admin\/logout\/?$/.test(f.getAttribute('action') || '')) {
      e.preventDefault();
      abrir('normal');
    }
  }, true);
  dlg.addEventListener('click', (e) => {
    if (e.target.closest('[data-sl=cancelar]')) {
      if (modo === 'inactivo') usar(true);
      cerrarDialogo();
    } else if (e.target === dlg && modo === 'normal') cerrarDialogo();  // clic fuera de la tarjeta
  });
  dlg.addEventListener('cancel', () => { if (modo === 'inactivo') usar(true); modo = null; });

  if (!minutos) return;
  // ------------------------------------------------------------------ inactividad
  const LIMITE = minutos * 60 * 1000, AVISO = Math.min(60 * 1000, LIMITE / 2), PING = 4 * 60 * 1000;
  const CLAVE = 'prospectos.actividad';
  const leerLS = () => { try { return parseInt(localStorage.getItem(CLAVE) || '0', 10) || 0; } catch (_) { return 0; } };
  const guardarLS = (t) => { try { localStorage.setItem(CLAVE, String(t)); } catch (_) { /* sin almacenamiento: solo esta pestaña */ } };
  let ultima = Date.now(), ultimoPing = Date.now(), pendiente = false;
  guardarLS(ultima);

  function ultimaActividad() { return Math.max(ultima, leerLS()); }
  function usar(forzarPing) {
    ultima = Date.now(); guardarLS(ultima); pendiente = true;
    if (forzarPing || ultima - ultimoPing > PING) ping();
  }
  function ping() {
    ultimoPing = Date.now(); pendiente = false;
    fetch(dlg.dataset.sigo, { method: 'POST', headers: { 'X-CSRFToken': dlg.dataset.csrf, 'X-Requested-With': 'fetch' }, credentials: 'same-origin' })
      .then((r) => { if (r.status === 401) irACerrada(); })
      .catch(() => { /* sin red: el servidor decide en la siguiente página */ });
  }
  function irACerrada() { location.href = forma.action.replace(/salir\/?$/, 'sesion-cerrada/') + '?motivo=inactividad'; }

  let ultimoMov = 0;
  const alUsar = (e) => {
    if (modo === 'inactivo') return;  // durante el aviso solo cuenta «Seguir trabajando»
    if (e.type === 'pointermove') { const t = Date.now(); if (t - ultimoMov < 15000) return; ultimoMov = t; }
    usar(false);
  };
  ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll'].forEach((ev) =>
    window.addEventListener(ev, alUsar, { passive: true, capture: true }));

  setInterval(() => {
    const quieto = Date.now() - ultimaActividad();
    if (quieto >= LIMITE) {
      motivo.value = 'inactividad';
      forma.submit();
      return;
    }
    if (quieto >= LIMITE - AVISO) {
      if (modo !== 'inactivo') abrir('inactivo');
      cuenta.textContent = String(Math.max(0, Math.ceil((LIMITE - quieto) / 1000)));
    } else if (modo === 'inactivo') {
      cerrarDialogo();  // otra pestaña se usó: ya no hace falta el aviso
    }
    if (pendiente && Date.now() - ultimoPing > PING) ping();
  }, 1000);
})();
