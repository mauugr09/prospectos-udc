/* Prospectos: ventana para dar de baja (anonimizar) a un aspirante. */
(function () {
  const raiz = document.getElementById('pp');
  const dlg = document.getElementById('pp-baja');
  if (!raiz || !dlg) return;
  const form = document.getElementById('pp-baja-form');
  const plantilla = raiz.dataset.baja; // .../0/baja/
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-baja]');
    if (b && b.tagName === 'BUTTON') {
      form.reset();
      form.action = plantilla.replace('/0/', '/' + encodeURIComponent(b.dataset.baja) + '/');
      document.getElementById('pp-baja-nombre').textContent = b.dataset.nombre || 'este aspirante';
      dlg.showModal();
      return;
    }
    if (e.target.closest('[data-cerrar]')) dlg.close();
  });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
})();
