/* Mi perfil: elegir una foto, encuadrarla (arrastrar y acercar) y guardarla como JPEG cuadrado de 256 px.
   La imagen se recorta en el navegador: al servidor solo llega el JPEG pequeño. */
(function () {
  const elegir = document.getElementById('pf-elegir');
  if (!elegir) return;
  // Fuera del documento: unfold le pone su propio manejador a todo input[type=file] de la página.
  const archivo = document.createElement('input');
  archivo.type = 'file'; archivo.accept = 'image/jpeg,image/png,image/webp';
  const caja = document.getElementById('pf-recorte');
  const lienzo = caja.querySelector('canvas');
  const ctx = lienzo.getContext('2d');
  const zoom = caja.querySelector('input[type=range]');
  const form = document.getElementById('pf-foto-form');
  const L = lienzo.width;
  let img = null, escala = 1, x = 0, y = 0;

  function base() { return Math.max(L / img.width, L / img.height); }
  function limitar() {
    const s = base() * escala, w = img.width * s, h = img.height * s;
    x = Math.min(0, Math.max(L - w, x));
    y = Math.min(0, Math.max(L - h, y));
  }
  function dibujar() {
    if (!img) return;
    limitar();
    const s = base() * escala;
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, L, L);
    ctx.drawImage(img, x, y, img.width * s, img.height * s);
  }

  elegir.addEventListener('click', () => archivo.click());
  archivo.addEventListener('change', () => {
    const f = archivo.files[0];
    if (!f) return;
    if (!/^image\/(jpeg|png|webp)$/.test(f.type)) { alertar('Elige una foto JPG, PNG o WebP.'); return; }
    if (f.size > 15 * 1024 * 1024) { alertar('Esa foto pesa más de 15 MB.'); return; }
    const url = URL.createObjectURL(f);
    const nueva = new Image();
    nueva.onload = () => {
      img = nueva; escala = 1; zoom.value = 1;
      const s = base();
      x = (L - img.width * s) / 2; y = (L - img.height * s) / 2;
      caja.hidden = false; dibujar();
      URL.revokeObjectURL(url);
    };
    nueva.onerror = () => alertar('No se pudo abrir esa imagen.');
    nueva.src = url;
  });

  zoom.addEventListener('input', () => {
    const antes = base() * escala;
    escala = parseFloat(zoom.value);
    const ahora = base() * escala, c = L / 2;
    x = c - (c - x) * ahora / antes; y = c - (c - y) * ahora / antes;  // acercar hacia el centro
    dibujar();
  });

  let arrastre = null;
  lienzo.addEventListener('pointerdown', (e) => { arrastre = { px: e.clientX, py: e.clientY, x, y }; lienzo.setPointerCapture(e.pointerId); });
  lienzo.addEventListener('pointermove', (e) => {
    if (!arrastre) return;
    const k = L / lienzo.getBoundingClientRect().width;
    x = arrastre.x + (e.clientX - arrastre.px) * k; y = arrastre.y + (e.clientY - arrastre.py) * k;
    dibujar();
  });
  ['pointerup', 'pointercancel'].forEach((t) => lienzo.addEventListener(t, () => { arrastre = null; }));

  document.getElementById('pf-cancelar').addEventListener('click', () => { caja.hidden = true; archivo.value = ''; img = null; });
  document.getElementById('pf-guardar-foto').addEventListener('click', () => {
    if (!img) return;
    form.querySelector('input[name=foto]').value = lienzo.toDataURL('image/jpeg', 0.85);
    form.submit();
  });

  function alertar(texto) {
    let p = form.parentNode.querySelector('.pd-error');
    if (!p) { p = document.createElement('p'); p.className = 'pd-error'; form.after(p); }
    p.textContent = texto;
  }
})();
