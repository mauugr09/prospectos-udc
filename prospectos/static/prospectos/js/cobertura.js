/*
 * Mapa de cobertura: burbujas por preparatoria, panel con lista y ficha, tres formas de colorear y distancias
 * a los planteles. Todo el texto que viene de la base de datos se pone con textContent (nunca como HTML).
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const leer = (id) => JSON.parse($(id).textContent);
  const caja = $('mapa');
  if (!caja) return;

  const puntos = leer('puntos'), sedes = leer('sedes'), acciones = leer('acciones');
  const [hy, hm, hd] = leer('hoy').split('-').map(Number);
  const HOY = new Date(hy, hm - 1, hd);

  // ------------------------------------------------------------------ colores por modo
  const C = { coral: '#F25C54', ambar: '#F2A33A', verde: '#22A06B', azul: '#2F6FED', gris: '#8E8E93',
              cuau: '#2447B8', tult: '#C2185B' };
  const MODOS = {
    respuesta: {
      leyenda: [[C.verde, 'Alta, 15 % o más'], [C.ambar, 'Media, 5 a 15 %'], [C.coral, 'Baja, menos de 5 %'], [C.gris, 'Sin alumnos estimados']],
      color(p) { const t = tasa(p); return t === null ? C.gris : t >= 15 ? C.verde : t >= 5 ? C.ambar : C.coral; },
    },
    visita: {
      leyenda: [[C.azul, 'Visita programada'], [C.verde, 'Visitada hace menos de 3 meses'], [C.ambar, 'Hace 3 a 12 meses'], [C.coral, 'Hace más de un año o nunca']],
      color(p) {
        if (p.proxima_visita) return C.azul;
        const d = p.dias_sin_visita;
        return d === null ? C.coral : d <= 90 ? C.verde : d <= 365 ? C.ambar : C.coral;
      },
    },
    plantel: {
      leyenda: [[C.cuau, 'Eligen Cuautitlán'], [C.tult, 'Eligen Tultepec'], [C.gris, 'Sin aspirantes']],
      color(p) {
        if (!p.total) return C.gris;
        const pc = Math.round(100 * p.cuautitlan / p.total);
        return `conic-gradient(${C.cuau} 0 ${pc}%, ${C.tult} ${pc}% 100%)`;
      },
    },
  };
  let modo = 'respuesta', elegido = null;

  const tasa = (p) => (p.estimados ? Math.round(1000 * p.total / p.estimados) / 10 : null);
  const fecha = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d); };
  const fmt = (iso) => fecha(iso).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' });
  const hace = (dias) => (dias === 0 ? 'hoy' : dias === 1 ? 'ayer' : dias < 60 ? `hace ${dias} días`
    : dias < 730 ? `hace ${Math.round(dias / 30)} meses` : `hace ${Math.round(dias / 365)} años`);
  const km = (a, b) => {
    const r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLng = (b.lng - a.lng) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLng / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(h));
  };
  const el = (tag, clase, texto) => { const e = document.createElement(tag); if (clase) e.className = clase; if (texto !== undefined) e.textContent = texto; return e; };
  const icono = (nombre) => el('span', 'material-symbols-outlined', nombre);
  const diametro = (p) => (p.total ? Math.min(84, 30 + Math.sqrt(p.total) * 7) : 20);

  MapaMX.cuandoTengaTamano(caja, function () {
    const mapa = MapaMX.crear(caja, { tiles: leer('tiles'), rueda: true,
                                      sinInternet: () => { $('sin-internet').hidden = false; } });
    mapa.zoomControl.setPosition('bottomright');

    // ---------------------------------------------------------------- planteles UDC y distancias
    const radios = L.layerGroup();
    sedes.forEach((s, n) => {
      [5, 10, 15].forEach((k) => {
        L.circle([s.lat, s.lng], { radius: k * 1000, color: '#2447B8', weight: 1.2, opacity: 0.55, dashArray: '6 6',
                                   fill: k === 5, fillColor: '#2447B8', fillOpacity: 0.05, interactive: false }).addTo(radios);
        // Con dos planteles cercanos, las etiquetas de uno van arriba y las del otro abajo para no encimarse.
        const etiqueta = L.marker([s.lat + (n % 2 ? -1 : 1) * k / 111.32, s.lng], { interactive: false, keyboard: false,
          icon: L.divIcon({ className: 'mc-radio-etq', html: '', iconSize: [0, 0] }) });
        etiqueta.on('add', () => { const e = etiqueta.getElement(); if (e) e.replaceChildren(el('span', '', `${k} km`)); });
        radios.addLayer(etiqueta);
      });
      // Debajo de las burbujas: nunca tapa una prepa; el nombre sale al pasar el cursor.
      const m = L.marker([s.lat, s.lng], { zIndexOffset: -1000, title: `Plantel ${s.nombre}`,
        icon: L.divIcon({ className: 'mc-sede-icono', html: '', iconSize: [0, 0] }) }).addTo(mapa);
      m.on('add', pintarSede); pintarSede.call(m);
      function pintarSede() {
        const e = this.getElement?.(); if (!e) return;
        const caja = el('div', 'mc-sede'); caja.append(icono('school'));
        e.replaceChildren(caja);
      }
      m.bindTooltip(`Plantel ${s.nombre}`, { direction: 'top', offset: [0, -18], className: 'mc-tip', permanent: false });
    });
    const interruptor = $('mc-radios');
    const verRadios = () => (!interruptor || interruptor.checked ? radios.addTo(mapa) : radios.remove());
    if (sedes.length) verRadios();
    interruptor?.addEventListener('change', verRadios);

    // ---------------------------------------------------------------- burbujas
    const marcadores = new Map();
    puntos.forEach((p) => {
      const d = diametro(p);
      const m = L.marker([p.lat, p.lng], { title: p.nombre, riseOnHover: true, zIndexOffset: p.total,
        icon: L.divIcon({ className: 'mc-burbuja-icono', html: '', iconSize: [d, d] }) }).addTo(mapa);
      m.on('add', () => pintar(p));
      m.on('click', () => elegir(p, true));
      m.bindTooltip(() => `${p.nombre.replace(/[<>&]/g, '')} · ${p.total}`, { direction: 'top', offset: [0, -d / 2], className: 'mc-tip' });
      marcadores.set(p.id, m);
      pintar(p);
    });

    function pintar(p) {
      const e = marcadores.get(p.id)?.getElement(); if (!e) return;
      const b = el('div', 'mc-burbuja' + (elegido === p ? ' elegida' : '') + (p.total ? '' : ' vacia'));
      const d = diametro(p);
      b.style.width = b.style.height = `${d}px`;
      b.style.background = MODOS[modo].color(p);
      b.style.fontSize = `${Math.max(11, Math.min(20, d / 3.2))}px`;
      if (p.total) b.append(el('span', '', p.total));
      e.replaceChildren(b);
    }
    const pintarTodo = () => puntos.forEach(pintar);

    const conAspirantes = puntos.filter((p) => p.total);
    const encuadre = (conAspirantes.length ? conAspirantes : puntos).map((p) => [p.lat, p.lng]).concat(sedes.map((s) => [s.lat, s.lng]));
    if (encuadre.length) mapa.fitBounds(L.latLngBounds(encuadre).pad(0.2), { maxZoom: 13, paddingBottomRight: [innerWidth > 900 ? 380 : 0, 0] });

    // ---------------------------------------------------------------- leyenda y modos
    function leyenda() {
      const caja = $('mc-leyenda');
      const filas = MODOS[modo].leyenda.map(([c, t]) => { const s = el('span'); const i = el('i'); i.style.background = c; s.append(i, t); return s; });
      const tam = el('span', 'mc-ley-tam'); tam.append(el('i', 'chica'), el('i', 'grande'), 'más aspirantes');
      caja.replaceChildren(...filas, tam);
    }
    function cambiarModo(nuevo) {
      modo = nuevo;
      document.querySelectorAll('#mc-modos [data-modo]').forEach((b) => {
        const activo = b.dataset.modo === modo; b.classList.toggle('activo', activo); b.setAttribute('aria-selected', activo);
      });
      pintarTodo(); leyenda(); lista();
    }
    document.querySelectorAll('#mc-modos [data-modo]').forEach((b) => b.addEventListener('click', () => cambiarModo(b.dataset.modo)));
    document.querySelectorAll('[data-modo-ir]').forEach((b) => b.addEventListener('click', () => {
      cambiarModo(b.dataset.modoIr); caja.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }));

    // ---------------------------------------------------------------- lista
    const buscador = $('mc-buscar');
    const normal = (t) => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    function lista() {
      const q = normal(buscador.value.trim());
      const ol = $('mc-lista');
      let filas = puntos.filter((p) => !q || normal(p.nombre).includes(q) || normal(p.municipio).includes(q));
      if (modo === 'visita') filas = filas.slice().sort((a, b) => (b.dias_sin_visita ?? 1e6) - (a.dias_sin_visita ?? 1e6) || b.total - a.total);
      ol.replaceChildren(...filas.slice(0, 200).map((p) => {
        const li = el('li'), bt = el('button', 'mc-item'); bt.type = 'button';
        const punto = el('i', 'mc-punto'); punto.style.background = MODOS[modo].color(p);
        const txt = el('span', 'mc-item-txt'); txt.append(el('b', '', p.nombre));
        const sub = modo === 'visita'
          ? (p.proxima_visita ? `Próxima: ${fmt(p.proxima_visita)}` : p.ultima_visita ? `Última: ${hace(p.dias_sin_visita)}` : 'Sin visitas registradas')
          : modo === 'plantel' ? `Cuautitlán ${p.cuautitlan} · Tultepec ${p.tultepec}`
          : [p.municipio, tasa(p) !== null ? `${tasa(p)} % responde` : null].filter(Boolean).join(' · ');
        txt.append(el('small', '', sub));
        bt.append(punto, txt, el('span', 'mc-item-n', p.total));
        bt.addEventListener('click', () => elegir(p, true));
        bt.addEventListener('mouseenter', () => marcadores.get(p.id)?.getElement()?.firstChild?.classList.add('resaltada'));
        bt.addEventListener('mouseleave', () => marcadores.get(p.id)?.getElement()?.firstChild?.classList.remove('resaltada'));
        li.append(bt); return li;
      }));
      if (!filas.length) ol.replaceChildren(el('li', 'mc-vacio', q ? 'Ninguna preparatoria coincide.' : 'Aún no hay preparatorias ubicadas.'));
    }
    buscador.addEventListener('input', lista);
    buscador.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { const b = $('mc-lista').querySelector('button'); if (b) { e.preventDefault(); b.click(); } }
    });

    // ---------------------------------------------------------------- ficha de la prepa
    function enlace(href, icon, texto, principal) {
      const a = el('a', 'mc-accion' + (principal ? ' principal' : '')); a.href = href; a.append(icono(icon), texto);
      if (href.startsWith('http')) { a.target = '_blank'; a.rel = 'noopener'; }
      return a;
    }
    function elegir(p, volar) {
      const antes = elegido; elegido = p;
      if (antes) pintar(antes);
      pintar(p);
      if (volar) {
        // El panel tapa la derecha del mapa: se centra la prepa en la parte que sí se ve.
        const z = Math.max(mapa.getZoom(), 13), corrimiento = innerWidth > 900 ? 190 : 0;
        mapa.flyTo(mapa.unproject(mapa.project([p.lat, p.lng], z).add([corrimiento, 0]), z), z, { duration: 0.6 });
      }
      const v = $('mc-vista-detalle');
      const volver = el('button', 'mc-volver'); volver.type = 'button'; volver.append(icono('chevron_left'), 'Todas las preparatorias');
      volver.addEventListener('click', cerrar);
      const cab = el('div', 'mc-ficha-cab');
      cab.append(el('h3', '', p.nombre), el('small', '', p.municipio || 'Municipio sin capturar'));
      const grande = el('div', 'mc-grande'); grande.append(el('b', '', p.total), el('span', '', p.total === 1 ? 'aspirante con permiso' : 'aspirantes con permiso'));
      const reparto = el('div', 'mc-reparto');
      if (p.total) {
        const barra = el('div', 'mc-reparto-barra'), a = el('i'), b = el('i');
        a.style.flex = p.cuautitlan || 0.0001; b.style.flex = p.tultepec || 0.0001; a.style.background = C.cuau; b.style.background = C.tult;
        barra.append(a, b);
        const nombres = el('div', 'mc-reparto-txt'); nombres.append(el('span', '', `Cuautitlán ${p.cuautitlan}`), el('span', '', `Tultepec ${p.tultepec}`));
        reparto.append(barra, nombres);
      }
      const datos = el('dl', 'mc-datos');
      const fila = (icon, t, valor, nota) => { const dt = el('dt'); dt.append(icono(icon), t); const dd = el('dd', '', valor); if (nota) dd.append(el('small', '', nota)); datos.append(dt, dd); };
      const t = tasa(p);
      fila('percent', 'Responde', t === null ? 'Sin estimado' : `${t} %`, p.estimados ? `de ${p.estimados} alumnos estimados` : 'Captura cuántos alumnos tiene');
      fila('history', 'Última visita', p.ultima_visita ? hace(p.dias_sin_visita) : 'Nunca', p.ultima_visita ? fmt(p.ultima_visita) : '');
      fila('event_upcoming', 'Próxima visita', p.proxima_visita ? fmt(p.proxima_visita) : 'Sin programar');
      if (sedes.length) {
        const cerca = sedes.map((s) => ({ s, d: km(s, p) })).sort((x, y) => x.d - y.d)[0];
        fila('near_me', 'Distancia', `${cerca.d.toFixed(1)} km`, `del plantel ${cerca.s.nombre} (en línea recta)`);
      }
      const acc = el('div', 'mc-acciones');
      if (acciones.evento && !p.proxima_visita) acc.append(enlace(`${acciones.evento}?preparatoria=${p.id}`, 'event', 'Programar visita', true));
      if (acciones.aspirantes && p.total) acc.append(enlace(`${acciones.aspirantes}?preparatoria__id__exact=${p.id}`, 'groups', 'Ver aspirantes', !acciones.evento || !!p.proxima_visita));
      if (acciones.qr) acc.append(enlace(acciones.qr.replace('/0/', `/${p.id}/`), 'qr_code_2', 'QR permanente'));
      acc.append(enlace(`https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lng}`, 'map', 'Google Maps'));
      if (acciones.prepa) acc.append(enlace(acciones.prepa.replace('/0/', `/${p.id}/`), 'edit', 'Datos de la prepa'));
      v.replaceChildren(volver, cab, grande, reparto, datos, acc);
      v.hidden = false; $('mc-vista-lista').hidden = true;
      $('mc-panel').classList.add('con-ficha');
    }
    function cerrar() {
      const antes = elegido; elegido = null; if (antes) pintar(antes);
      $('mc-vista-detalle').hidden = true; $('mc-vista-lista').hidden = false;
      $('mc-panel').classList.remove('con-ficha');
    }
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && elegido) cerrar(); });
    mapa.on('click', () => { if (elegido) cerrar(); });

    leyenda(); lista();
  });
})();
