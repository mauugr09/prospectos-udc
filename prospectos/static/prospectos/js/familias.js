// Familias por unir: filtrar al escribir, buscar alumnos en vivo y unir/descartar sin recargar.
(function () {
  const raiz = document.getElementById('fm');
  if (!raiz) return;
  const q = document.getElementById('fm-q');
  const lista = document.getElementById('fm-lista');
  const vacio = document.getElementById('fm-vacio');
  const vacioTexto = document.getElementById('fm-vacio-texto');
  const estado = document.getElementById('fm-estado');
  const aviso = document.getElementById('fm-aviso');
  const filtro = { vista: 'con', nivel: '', texto: '' };

  // Mismas reglas que el servidor: sin acentos, Ximena=Jimena, z=s, v=b, ll=y, h muda.
  const variante = (t) => t.replace(/^x(?=[ie])/, 'j').replace(/z/g, 's').replace(/ll/g, 'y').replace(/v/g, 'b')
    .replace(/(^|[^c])h(?=[aeiou])/g, '$1').replace(/^h/, '');
  const normalizar = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/ñ/g, 'n')
    .replace(/[^a-z0-9 ]+/g, ' ').split(/\s+/).filter(Boolean).map(variante).join(' ');

  const tarjetas = () => [...lista.querySelectorAll('.fm-tarjeta')];
  function indexar(t) { t.dataset.texto = normalizar(t.querySelector('.fm-cabeza').textContent + ' ' +
    [...t.querySelectorAll('.fm-cands:not(.fm-resultados) .fm-cand-texto')].map((x) => x.textContent).join(' ')); }
  tarjetas().forEach(indexar);

  function aplicar() {
    const palabras = filtro.texto ? filtro.texto.split(' ') : [];
    let visibles = 0;
    const cuenta = { con: 0, sin: 0 };
    for (const t of tarjetas()) {
      const coincide = palabras.every((p) => t.dataset.texto.includes(p));
      if (coincide) cuenta[t.dataset.tipo]++;
      const ver = coincide && t.dataset.tipo === filtro.vista && (!filtro.nivel || filtro.vista === 'sin' || t.dataset.nivel === filtro.nivel);
      t.hidden = !ver;
      if (ver) visibles++;
    }
    for (const k of ['con', 'sin']) raiz.querySelector(`[data-cuenta="${k}"]`).textContent = cuenta[k];
    raiz.querySelector('#fm-nivel').hidden = filtro.vista === 'sin';
    vacio.hidden = visibles > 0;
    vacioTexto.textContent = filtro.texto ? `Nada coincide con «${q.value.trim()}».`
      : filtro.vista === 'con' ? 'No hay propuestas por revisar. Las seguras se unen solas al importar.'
      : 'Todas las encuestas de familias tienen a su alumno o una propuesta.';
    estado.textContent = filtro.texto ? `${visibles} resultado${visibles === 1 ? '' : 's'}` : '';
  }

  let espera;
  q.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(() => { filtro.texto = normalizar(q.value); aplicar(); }, 120); });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) { e.preventDefault(); q.focus(); }
    if (e.key === 'Escape' && document.activeElement === q && q.value) { q.value = ''; filtro.texto = ''; aplicar(); }
  });
  function segmento(id, clave) {
    raiz.querySelector(id).addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      b.parentElement.querySelectorAll('button').forEach((x) => x.classList.toggle('activo', x === b));
      filtro[clave] = b.dataset[clave === 'vista' ? 'vista' : 'nivel'];
      aplicar();
    });
  }
  segmento('#fm-vista', 'vista'); segmento('#fm-nivel', 'nivel');

  let avisoT;
  function avisar(texto, error) {
    aviso.textContent = texto; aviso.classList.toggle('error', !!error); aviso.hidden = false;
    clearTimeout(avisoT); avisoT = setTimeout(() => { aviso.hidden = true; }, 4000);
  }

  function quitar(el) {
    el.classList.add('fm-saliendo');
    setTimeout(() => { el.remove(); aplicar(); }, 260);
  }
  function quitarCandidato(li) {
    const t = li.closest('.fm-tarjeta');
    li.remove();
    if (!t.querySelector('.fm-cands:not(.fm-resultados) .fm-cand')) {  // ya no le quedan propuestas: pasa a «Sin pareja»
      t.dataset.tipo = 'sin'; t.dataset.nivel = 'sin';
      t.querySelector('.fm-mejor')?.remove(); t.querySelector('.fm-pie')?.remove();
      t.querySelector('.fm-cands:not(.fm-resultados)')?.remove();
    }
    indexar(t);
  }

  async function enviar(datos) {
    const r = await fetch(location.pathname, { method: 'POST', credentials: 'same-origin', body: datos,
      headers: { 'X-CSRFToken': raiz.dataset.csrf, 'X-Requested-With': 'fetch' } });
    let j = {}; try { j = await r.json(); } catch (e) { /* respuesta no JSON */ }
    if (!r.ok || !j.ok) throw new Error(j.mensaje || 'No se pudo. Recarga la página e intenta otra vez.');
    return j;
  }

  lista.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-accion]'); if (!b) return;
    // Unir sin ningún indicio en común pide un segundo clic: unir mal no se deshace con un botón.
    if (b.dataset.confirmar && !b.classList.contains('fm-confirmando')) {
      b.dataset.texto = b.textContent; b.textContent = b.dataset.confirmar; b.classList.add('fm-confirmando');
      setTimeout(() => { if (b.isConnected) { b.textContent = b.dataset.texto; b.classList.remove('fm-confirmando'); } }, 4000);
      return;
    }
    const t = b.closest('.fm-tarjeta');
    const li = b.closest('.fm-cand');
    const datos = new FormData();
    datos.append('accion', b.dataset.accion);
    datos.append('familia', t.dataset.familia);
    (b.dataset.propuestas || '').split(',').filter(Boolean).forEach((p) => datos.append('propuesta', p));
    if (b.dataset.alumno) datos.append('alumno', b.dataset.alumno);
    b.disabled = true;
    try {
      const j = await enviar(datos);
      if (b.dataset.accion === 'no') { quitarCandidato(li); aplicar(); avisar('Descartado.'); return; }
      if (j.alumno) {  // ese alumno ya tiene familia: sale de las demás tarjetas
        lista.querySelectorAll(`.fm-cand[data-alumno="${j.alumno}"]`).forEach((x) => { if (!t.contains(x)) quitarCandidato(x); });
      }
      if (b.dataset.accion === 'ninguno') {
        t.querySelectorAll('.fm-cands:not(.fm-resultados) .fm-cand').forEach(quitarCandidato); aplicar();
      } else quitar(t);
      avisar(j.mensaje);
    } catch (err) { b.disabled = false; avisar(err.message, true); }
  });

  // Búsqueda en vivo de otro alumno, por tarjeta.
  lista.addEventListener('input', (e) => {
    const campo = e.target.closest('.fm-otro-q'); if (!campo) return;
    const t = campo.closest('.fm-tarjeta');
    const res = t.querySelector('.fm-resultados');
    clearTimeout(campo._t);
    const texto = campo.value.trim();
    if (texto.length < 2) { res.innerHTML = ''; return; }
    campo._t = setTimeout(async () => {
      const yo = (campo._n = (campo._n || 0) + 1);
      try {
        const r = await fetch(`${raiz.dataset.buscar}?familia=${t.dataset.familia}&q=${encodeURIComponent(texto)}`, { credentials: 'same-origin' });
        if (yo === campo._n && r.ok) res.innerHTML = await r.text();  // descarta respuestas viejas
      } catch (err) { res.innerHTML = '<li class="fm-sin-resultados">Sin conexión con la PC del sistema.</li>'; }
    }, 220);
  });

  aplicar();
})();
