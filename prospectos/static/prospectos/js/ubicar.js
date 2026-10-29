/*
 * Ubicar preparatorias: elegir de la lista, buscar (Google Places si hay llave; si no, Nominatim),
 * pegar coordenadas o un enlace de Google Maps, o hacer clic; y guardar.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const lista = JSON.parse($('ub-lista').textContent);
  const ubicadas = JSON.parse($('ub-ubicadas').textContent);
  const fondo = JSON.parse($('tiles').textContent);
  let conGoogle = !!(fondo.google && fondo.google.llave);
  const CENTRO = { lat: 19.70, lng: -99.15 };  // zona de los planteles
  const csrf = document.querySelector('input[name=csrfmiddlewaretoken]')?.value || '';
  const NOMINATIM = 'https://nominatim.openstreetmap.org';
  const OPC = { referrerPolicy: 'origin' };  // Nominatim pide identificar la aplicación (Referer)
  let mapa, pin, actual = null, ultimaConsulta = 0;

  function texto(el, t) { el.textContent = t; }

  function elegir(id) {
    actual = lista.find((p) => p.id === id) || null;
    document.querySelectorAll('#ub-prepas button').forEach((b) => b.classList.toggle('activo', +b.dataset.id === id));
    texto($('ub-nombre'), actual ? actual.nombre : '—');
    $('ub-municipio').value = actual?.municipio || '';
    $('ub-q').value = actual ? actual.nombre : '';
    $('ub-resultados').hidden = true;
    if (pin) { pin.remove(); pin = null; }
    if (actual && actual.lat != null) poner([actual.lat, actual.lng], false);
    $('ub-guardar').disabled = !pin;
    texto($('ub-estado'), actual ? 'Busca la escuela o haz clic en el mapa donde está.' : 'Elige una preparatoria de la lista.');
  }

  function poner(latlng, centrar = true) {
    if (!actual) { texto($('ub-estado'), 'Primero elige una preparatoria de la lista.'); return; }
    if (!pin) {
      pin = L.marker(latlng, { draggable: true, autoPan: true }).addTo(mapa);
      pin.on('dragend', () => despues(pin.getLatLng()));
    } else pin.setLatLng(latlng);
    if (centrar) mapa.setView(latlng, Math.max(mapa.getZoom(), 15));
    $('ub-guardar').disabled = false;
    despues(L.latLng(latlng));
  }

  async function esperarTurno() {
    // Política de Nominatim: máximo 1 consulta por segundo y nada de autocompletar.
    const falta = 1100 - (Date.now() - ultimaConsulta);
    if (falta > 0) await new Promise((r) => setTimeout(r, falta));
    ultimaConsulta = Date.now();
  }

  function municipioDe(componentes) {
    // Google: el municipio en México es administrative_area_level_2 (a veces solo viene «locality»).
    const de = (tipo) => componentes.find((c) => (c.types || []).includes(tipo));
    const c = de('administrative_area_level_2') || de('locality');
    return c ? (c.longText || c.long_name || '') : '';
  }

  async function despues(ll) {
    const estado = $('ub-estado');
    estado.textContent = `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)} · arrastra el pin para afinar · `;
    estado.append(MapaMX.enlaceGoogle(ll.lat, ll.lng, 'comprobar en Google Maps'));
    if ($('ub-municipio').value) return;
    if (conGoogle) {
      try {
        const { Geocoder } = await google.maps.importLibrary('geocoding');
        const { results } = await new Geocoder().geocode({ location: { lat: ll.lat, lng: ll.lng } });
        const mun = results && results[0] ? municipioDe(results[0].address_components) : '';
        if (mun && !$('ub-municipio').value) $('ub-municipio').value = mun;
        return;
      } catch (e) { /* Geocoding API no habilitada: se intenta con OpenStreetMap */ }
    }
    try {
      await esperarTurno();
      const r = await fetch(`${NOMINATIM}/reverse?format=jsonv2&zoom=10&accept-language=es&lat=${ll.lat}&lon=${ll.lng}`, OPC);
      const a = (await r.json()).address || {};
      const mun = a.municipality || a.county || a.city || a.town || a.village || '';
      if (mun && !$('ub-municipio').value) $('ub-municipio').value = mun.replace(/^Municipio de /i, '');
    } catch (e) { /* sin internet: el municipio se escribe a mano */ }
  }

  function coordenadas(q) {
    // «19.6851, -99.1283», o un enlace de Google Maps (…!3d19.68!4d-99.12…, …@19.68,-99.12,17z, …?q=19.68,-99.12).
    const patrones = [/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/, /@(-?\d+\.\d+),\s*(-?\d+\.\d+)/,
                      /[?&](?:q|query|ll|center)=(-?\d+\.\d+),\s*(-?\d+\.\d+)/, /^\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$/];
    for (const p of patrones) {
      const m = q.match(p);
      if (m) return [parseFloat(m[1]), parseFloat(m[2])];
    }
    return null;
  }

  function mostrar(resultados, pie) {
    const caja = $('ub-resultados');
    caja.innerHTML = '';
    caja.hidden = false;
    if (!resultados.length && !pie) {
      const li = document.createElement('li');
      li.textContent = 'Sin resultados. Prueba con la colonia o calle, pega las coordenadas de Google Maps, o haz clic en el mapa.';
      caja.append(li);
    }
    resultados.forEach((x) => {
      const li = document.createElement('li');
      const b = document.createElement('button'); b.type = 'button';
      const t = document.createElement('b'); t.textContent = x.nombre || '';
      b.append(t, document.createTextNode((x.nombre ? ' · ' : '') + (x.direccion || '')));
      b.onclick = () => {
        caja.hidden = true;
        if (x.municipio) $('ub-municipio').value = x.municipio;
        poner([x.lat, x.lng]);
      };
      li.append(b); caja.append(li);
    });
    if (!resultados.length && pie && /Google Maps\.$|OpenStreetMap\./.test(pie)) {
      const li = document.createElement('li');
      li.textContent = 'Sin resultados. Prueba con la colonia o calle, pega las coordenadas de Google Maps, o haz clic en el mapa.';
      caja.append(li);
    }
    if (pie) { const li = document.createElement('li'); li.className = 'ub-pie'; li.textContent = pie; caja.append(li); }
  }

  async function buscarGoogle(q) {
    const { Place } = await google.maps.importLibrary('places');
    const { places } = await Place.searchByText({
      textQuery: q, fields: ['displayName', 'formattedAddress', 'location', 'addressComponents'],
      locationBias: CENTRO, region: 'mx', language: 'es', maxResultCount: 6,
    });
    return (places || []).map((p) => ({ nombre: p.displayName, direccion: p.formattedAddress, lat: p.location.lat(),
                                        lng: p.location.lng(), municipio: municipioDe(p.addressComponents || []) }));
  }

  async function buscar(q) {
    const coords = coordenadas(q);
    if (coords) { $('ub-resultados').hidden = true; poner(coords); return; }
    if (/goo\.gl|maps\.app/.test(q)) {
      mostrar([], 'Los enlaces cortos de Google Maps no se pueden leer. En Google Maps haz clic derecho sobre la escuela: ' +
                  'las coordenadas se copian al hacer clic en ellas; pégalas aquí.');
      return;
    }
    const caja = $('ub-resultados');
    caja.innerHTML = '';
    caja.hidden = false;
    const cargando = document.createElement('li'); cargando.textContent = 'Buscando…'; caja.append(cargando);
    if (conGoogle) {
      try { mostrar(await buscarGoogle(q), 'Resultados de Google Maps.'); return; } catch (e) {
        console.warn('Google Places no respondió; se usa OpenStreetMap.', e);  // p. ej. Places API (New) no habilitada
      }
    }
    try {
      await esperarTurno();
      const r = await fetch(`${NOMINATIM}/search?format=jsonv2&countrycodes=mx&limit=6&accept-language=es&` +
        `viewbox=-99.45,19.95,-98.85,19.45&q=${encodeURIComponent(q)}`, OPC);
      const res = await r.json();
      mostrar(res.map((x) => ({ direccion: x.display_name, lat: +x.lat, lng: +x.lon })),
              'Resultados de OpenStreetMap. Si no aparece la escuela, búscala en Google Maps y pega aquí sus coordenadas.');
    } catch (e) {
      caja.innerHTML = '';
      const li = document.createElement('li');
      li.textContent = 'No se pudo buscar (¿sin internet?). Haz clic en el mapa donde está la escuela.';
      caja.append(li);
    }
  }

  async function guardar() {
    if (!actual || !pin) return;
    const ll = pin.getLatLng();
    const datos = new FormData();
    datos.append('prepa', actual.id); datos.append('lat', ll.lat.toFixed(7)); datos.append('lng', ll.lng.toFixed(7));
    datos.append('municipio', $('ub-municipio').value);
    $('ub-guardar').disabled = true;
    const r = await fetch(location.pathname, { method: 'POST', body: datos, headers: { 'X-CSRFToken': csrf } });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) { texto($('ub-estado'), j.error || 'No se pudo guardar.'); $('ub-guardar').disabled = false; return; }
    L.circleMarker(ll, { radius: 6, color: '#fff', weight: 1, fillColor: '#4ade80', fillOpacity: 1 })
      .bindTooltip(actual.nombre).addTo(mapa);
    pin.remove(); pin = null;
    const i = lista.indexOf(actual);
    lista.splice(i, 1);
    document.querySelector(`#ub-prepas button[data-id="${actual.id}"]`)?.closest('li')?.remove();
    texto($('ub-cuenta'), lista.length);
    texto($('ub-estado'), `Guardada «${actual.nombre}».`);
    elegir(lista[Math.min(i, lista.length - 1)]?.id);
  }

  // ------------------------------------------------------------------ búsqueda en lote
  // Busca todas las prepas sin ubicar, una por una (OpenStreetMap pide máximo 1 consulta por segundo), propone el
  // primer resultado DENTRO de la zona de los planteles y deja marcadas solo las que se parecen por nombre.
  // Nada se guarda sin que la persona lo confirme.
  const ZONA = { s: 19.30, n: 20.10, o: -99.60, e: -98.80 };
  const ABREV = [[/\bepo\b/gi, 'Escuela Preparatoria Oficial'], [/\bepoem\b/gi, 'Escuela Preparatoria Oficial'],
                 [/\bprepa\b/gi, 'Preparatoria'], [/\bcbt\b/gi, 'Centro de Bachillerato Tecnológico'],
                 [/\bno\.?\s*/gi, ''], [/#/g, '']];
  const enZona = (x) => x.lat >= ZONA.s && x.lat <= ZONA.n && x.lng >= ZONA.o && x.lng <= ZONA.e;
  const palabras = (t) => (t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().match(/[a-z0-9]+/g) || [];
  function parecido(a, b) {
    const pa = new Set(palabras(a).filter((w) => w.length > 2 || /\d/.test(w)));
    const pb = new Set(palabras(b));
    if (!pa.size) return 0;
    let n = 0; pa.forEach((w) => { if (pb.has(w)) n += 1; });
    return n / pa.size;
  }
  let propuestas = [], capaLote = null, detener = false;

  async function buscarUna(p) {
    let q = p.nombre;
    ABREV.forEach(([re, t]) => { q = q.replace(re, t); });
    q = `${q.trim()}, ${p.municipio || 'Estado de México'}`;
    if (conGoogle) {
      try {
        const r = (await buscarGoogle(q)).filter(enZona);
        if (r.length) return r[0];
      } catch (e) { conGoogle = false; }
    }
    await esperarTurno();
    const r = await fetch(`${NOMINATIM}/search?format=jsonv2&countrycodes=mx&limit=5&accept-language=es&bounded=1&` +
      `viewbox=${ZONA.o},${ZONA.n},${ZONA.e},${ZONA.s}&q=${encodeURIComponent(q)}`, OPC);
    const res = (await r.json()).map((x) => ({ nombre: x.name || '', direccion: x.display_name, lat: +x.lat, lng: +x.lon,
                                               escuela: ['school', 'college', 'university'].includes(x.type) }));
    return res.filter(enZona).sort((a, b) => (b.escuela - a.escuela))[0] || null;
  }

  function filaLote(p, x) {
    const li = document.createElement('li');
    const etiqueta = document.createElement('label');
    const cb = document.createElement('input'); cb.type = 'checkbox';
    const t = document.createElement('div');
    const b = document.createElement('b'); b.textContent = p.nombre;
    const sm = document.createElement('small');
    if (x) {
      const sim = parecido(p.nombre, `${x.nombre} ${x.direccion}`);
      const seguro = sim >= 0.5 || (x.escuela && sim >= 0.3);  // ser escuela no basta: puede ser otra escuela
      cb.checked = seguro; cb.dataset.id = p.id;
      sm.textContent = `${seguro ? '' : 'Revisa: '}${x.nombre ? x.nombre + ', ' : ''}${x.direccion || ''}`;
      if (!seguro) sm.classList.add('ub-dudosa');
      propuestas.push({ prepa: p, x, cb });
      const m = L.circleMarker([x.lat, x.lng], { radius: 7, color: '#fff', weight: 2, fillColor: seguro ? '#ff9500' : '#8e8e93', fillOpacity: 1 })
        .bindTooltip(p.nombre).addTo(capaLote);
      li.addEventListener('mouseenter', () => m.openTooltip());
      li.addEventListener('click', (e) => { if (e.target !== cb) mapa.setView([x.lat, x.lng], 15); });
    } else {
      cb.disabled = true;
      sm.textContent = 'No se encontró: búscala a mano.';
      sm.classList.add('ub-dudosa');
    }
    t.append(b, sm); etiqueta.append(cb, t); li.append(etiqueta);
    return li;
  }

  async function buscarTodas() {
    const panel = $('ub-lote'), ul = $('ub-lote-lista'), estado = $('ub-lote-estado');
    panel.hidden = false; ul.innerHTML = ''; propuestas = []; detener = false;
    if (capaLote) capaLote.remove();
    capaLote = L.featureGroup().addTo(mapa);
    $('ub-todas').disabled = true; $('ub-lote-guardar').disabled = true;
    const pendientes = lista.slice();
    for (let i = 0; i < pendientes.length && !detener; i += 1) {
      estado.textContent = `Buscando ${i + 1} de ${pendientes.length}… (OpenStreetMap permite una búsqueda por segundo)`;
      let x = null;
      try { x = await buscarUna(pendientes[i]); } catch (e) { estado.textContent = 'Sin conexión: no se pudo seguir buscando.'; break; }
      ul.append(filaLote(pendientes[i], x));
    }
    const marcadas = propuestas.filter((p) => p.cb.checked).length;
    estado.textContent = `Se encontraron ${propuestas.length} de ${pendientes.length}. Marcadas ${marcadas}: las que se parecen por nombre. ` +
      'Revisa en el mapa las grises antes de marcarlas.';
    if (capaLote.getLayers().length) mapa.fitBounds(capaLote.getBounds().pad(.2));
    $('ub-todas').disabled = false; $('ub-lote-guardar').disabled = !propuestas.length;
  }

  async function guardarLote() {
    const elegidas = propuestas.filter((p) => p.cb.checked);
    $('ub-lote-guardar').disabled = true;
    let ok = 0;
    for (const p of elegidas) {
      const datos = new FormData();
      datos.append('prepa', p.prepa.id); datos.append('lat', p.x.lat.toFixed(7)); datos.append('lng', p.x.lng.toFixed(7));
      datos.append('municipio', p.x.municipio || p.prepa.municipio || '');
      const r = await fetch(location.pathname, { method: 'POST', body: datos, headers: { 'X-CSRFToken': csrf } });
      const j = await r.json().catch(() => ({}));
      if (r.ok && j.ok) {
        ok += 1;
        p.cb.closest('li').remove();
        lista.splice(lista.indexOf(p.prepa), 1);
        document.querySelector(`#ub-prepas button[data-id="${p.prepa.id}"]`)?.closest('li')?.remove();
        L.circleMarker([p.x.lat, p.x.lng], { radius: 6, color: '#fff', weight: 1, fillColor: '#34c759', fillOpacity: 1 })
          .bindTooltip(p.prepa.nombre).addTo(mapa);
      }
    }
    propuestas = propuestas.filter((p) => document.body.contains(p.cb));
    texto($('ub-cuenta'), lista.length);
    texto($('ub-lote-estado'), `Guardadas ${ok}. Las que quedan: revísalas una por una.`);
    $('ub-lote-guardar').disabled = !propuestas.length;
  }

  const caja = $('ub-mapa');
  MapaMX.cuandoTengaTamano(caja, () => {
    mapa = MapaMX.crear(caja, { tiles: fondo, rueda: true, googleFallo: () => { conGoogle = false; } });
    ubicadas.forEach((p) => L.circleMarker([p.lat, p.lng], { radius: 5, color: '#fff', weight: 1, fillColor: '#8b90a0', fillOpacity: .9 })
      .bindTooltip(p.nombre).addTo(mapa));
    mapa.on('click', (e) => poner(e.latlng, false));
    document.querySelectorAll('#ub-prepas button').forEach((b) => b.addEventListener('click', () => elegir(+b.dataset.id)));
    $('ub-buscar').addEventListener('submit', (e) => { e.preventDefault(); if ($('ub-q').value.trim()) buscar($('ub-q').value.trim()); });
    $('ub-guardar').addEventListener('click', guardar);
    $('ub-todas')?.addEventListener('click', buscarTodas);
    $('ub-lote-guardar').addEventListener('click', guardarLote);
    $('ub-lote-cerrar').addEventListener('click', () => { detener = true; $('ub-lote').hidden = true; if (capaLote) capaLote.remove(); });
    const inicial = document.querySelector('#ub-prepas button.activo') || document.querySelector('#ub-prepas button');
    if (inicial) elegir(+inicial.dataset.id);
  });
})();
