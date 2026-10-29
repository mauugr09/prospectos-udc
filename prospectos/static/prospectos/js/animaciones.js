/*
 * Detalles de movimiento de toda la interfaz. Todo responde a algo que hace la persona; nada se mueve solo.
 *  - Avisa el cambio de tema (evento «udc-tema») para que gráficas y mapas se repinten.
 *  - Barra superior: se vuelve vidrio cuando el contenido pasa por debajo.
 *  - Controles segmentados: la selección se desliza a la opción elegida antes de cambiar de página.
 * Respeta «reducir movimiento» del sistema.
 */
(function () {
  const raiz = document.documentElement;
  const quieto = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // 1) Tema: unfold cambia la clase .dark de <html>.
  let oscuro = raiz.classList.contains('dark');
  new MutationObserver(() => {
    const ahora = raiz.classList.contains('dark');
    if (ahora !== oscuro) {
      oscuro = ahora;
      document.dispatchEvent(new CustomEvent('udc-tema', { detail: { oscuro } }));
    }
  }).observe(raiz, { attributes: true, attributeFilter: ['class'] });

  // 2) Barra superior de vidrio solo al desplazar.
  let pendiente = false;
  const revisar = () => { pendiente = false; raiz.classList.toggle('desplazado', window.scrollY > 4); };
  window.addEventListener('scroll', () => { if (!pendiente) { pendiente = true; requestAnimationFrame(revisar); } }, { passive: true });
  revisar();

  // 2b) Título grande: cuando sale de la vista, aparece el título chico en la barra.
  const titulo = () => {
    const t = document.querySelector('.titulo-grande');
    if (!t || !window.IntersectionObserver) return;
    raiz.classList.add('con-titulo-grande');
    new IntersectionObserver(([e]) => raiz.classList.toggle('titulo-arriba', !e.isIntersecting && e.boundingClientRect.top < 80),
                             { rootMargin: '-64px 0px 0px 0px' }).observe(t);
  };

  // 3) Controles segmentados con «pulgar» que se desliza.
  function segmentado(nav) {
    const activo = nav.querySelector('a.activo');
    if (!activo) return;
    const pulgar = document.createElement('span');
    pulgar.className = 'seg-pulgar';
    pulgar.setAttribute('aria-hidden', 'true');
    nav.prepend(pulgar);
    const mover = (a, animar) => {
      pulgar.style.transition = animar ? '' : 'none';
      pulgar.style.width = a.offsetWidth + 'px';
      pulgar.style.transform = `translateX(${a.offsetLeft - 2}px)`;
      if (!animar) { void pulgar.offsetWidth; pulgar.style.transition = ''; }
    };
    mover(activo, false);
    nav.classList.add('con-pulgar');
    new ResizeObserver(() => mover(nav.querySelector('a.activo') || activo, false)).observe(nav);
    nav.addEventListener('click', (e) => {
      const a = e.target.closest('a');
      if (!a || a.classList.contains('activo') || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
      nav.querySelectorAll('a.activo').forEach((x) => x.classList.remove('activo'));
      a.classList.add('activo');
      if (quieto()) return;
      e.preventDefault();
      mover(a, true);
      // Al cambiar de periodo se queda en el mismo lugar de la página (no salta hasta arriba).
      try { sessionStorage.setItem('udc-desplazamiento', JSON.stringify({ ruta: location.pathname, y: window.scrollY })); } catch (err) { /* sin almacenamiento */ }
      setTimeout(() => { window.location.href = a.href; }, 220);
    });
  }
  // 4) Gráficas de unfold (reporte, listas): misma letra que la interfaz.
  const letraGraficas = () => {
    if (!window.Chart) return;
    const f = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.family = f;
    Object.values(Chart.instances || {}).forEach((g) => { try { g.update('none'); } catch (e) { /* gráfica ya destruida */ } });
  };
  window.addEventListener('load', letraGraficas);

  const recordarLugar = () => {
    try {
      const v = JSON.parse(sessionStorage.getItem('udc-desplazamiento') || 'null');
      sessionStorage.removeItem('udc-desplazamiento');
      if (v && v.ruta === location.pathname) requestAnimationFrame(() => window.scrollTo(0, v.y));
    } catch (err) { /* sin almacenamiento */ }
  };

  const iniciar = () => { recordarLugar(); titulo(); letraGraficas(); document.querySelectorAll('.seg, .tb-periodos').forEach(segmentado); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
