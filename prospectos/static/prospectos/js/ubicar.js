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

  const caja = $('ub-mapa');
  MapaMX.cuandoTengaTamano(caja, () => {
    mapa = MapaMX.crear(caja, { tiles: fondo, rueda: true, googleFallo: () => { conGoogle = false; } });
    ubicadas.forEach((p) => L.circleMarker([p.lat, p.lng], { radius: 5, color: '#fff', weight: 1, fillColor: '#8b90a0', fillOpacity: .9 })
      .bindTooltip(p.nombre).addTo(mapa));
    mapa.on('click', (e) => poner(e.latlng, false));
    document.querySelectorAll('#ub-prepas button').forEach((b) => b.addEventListener('click', () => elegir(+b.dataset.id)));
    $('ub-buscar').addEventListener('submit', (e) => { e.preventDefault(); if ($('ub-q').value.trim()) buscar($('ub-q').value.trim()); });
    $('ub-guardar').addEventListener('click', guardar);
    const inicial = document.querySelector('#ub-prepas button.activo') || document.querySelector('#ub-prepas button');
    if (inicial) elegir(+inicial.dataset.id);
  });
})();
