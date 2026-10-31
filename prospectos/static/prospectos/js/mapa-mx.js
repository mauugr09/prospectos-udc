/*
 * Mapa base de México para todas las pantallas.
 * - Contorno de los 32 estados incluido en el programa (Natural Earth, dominio público): se ve SIN internet.
 * - Encima, el fondo de calles: Google Maps si se configuró una llave (Configuración → Mapa), si no OpenStreetMap.
 *   Si la llave falla (vencida, sin facturación, restringida a otra dirección), se cambia solo a OpenStreetMap.
 * - Vista inicial: zona de los planteles (Cuautitlán / Tultepec); no deja irse fuera de México.
 */
window.MapaMX = (function () {
  const ZONA_PLANTELES = [[19.60, -99.30], [19.85, -98.98]];
  const MEXICO = [[14.0, -118.6], [33.0, -86.4]];
  let estadosCache = null;

  function estados() {
    if (!estadosCache) {
      const url = document.querySelector('meta[name="mx-estados"]')?.content || '/static/prospectos/geo/mx-estados.geojson';
      estadosCache = fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    }
    return estadosCache;
  }

  function cuandoTengaTamano(caja, fn) {
    // Las páginas del panel arrancan ocultas (x-cloak) hasta que carga Alpine.
    const esperar = () => (caja.offsetWidth > 0 ? fn() : requestAnimationFrame(esperar));
    esperar();
  }

  function ponerReferencias(mapa) {
    // Sin el fondo de calles: nombres de municipios (aproximados) para orientarse.
    const url = (document.querySelector('meta[name="mx-estados"]')?.content || '/static/prospectos/geo/mx-estados.geojson')
      .replace('mx-estados.geojson', 'mx-referencias.json');
    fetch(url).then((r) => r.json()).then((d) => {
      if (!mapa.getPane('referencias')) mapa.createPane('referencias').style.zIndex = 350;  // debajo de pines y círculos
      const capa = L.layerGroup();
      d.lugares.forEach(([nombre, lat, lng]) => {
        // Leaflet posiciona el marcador con transform: el texto va en un hijo para no pisarlo.
        const icono = L.divIcon({ className: 'mx-ref', html: '<span></span>', iconSize: [0, 0] });
        const m = L.marker([lat, lng], { icon: icono, interactive: false, keyboard: false, pane: 'referencias' });
        m.on('add', () => { const el = m.getElement()?.firstChild; if (el) el.textContent = nombre; });
        capa.addLayer(m);
      });
      const ver = () => (mapa.getZoom() >= 9 ? capa.addTo(mapa) : capa.remove());
      mapa.on('zoomend', ver);
      ver();
    }).catch(() => {});
  }

  // Estilo «noche» de Google Maps, con los azules del programa.
  const NOCHE = [
    { elementType: 'geometry', stylers: [{ color: '#1b2030' }] },
    { elementType: 'labels.text.stroke', stylers: [{ color: '#11141c' }] },
    { elementType: 'labels.text.fill', stylers: [{ color: '#8b90a0' }] },
    { featureType: 'administrative.locality', elementType: 'labels.text.fill', stylers: [{ color: '#c9cdd8' }] },
    { featureType: 'poi', elementType: 'labels.text.fill', stylers: [{ color: '#a5b3df' }] },
    { featureType: 'poi.park', elementType: 'geometry', stylers: [{ color: '#1d2b2b' }] },
    { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#2c3346' }] },
    { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#171b26' }] },
    { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#9ca5b3' }] },
    { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#3a4664' }] },
    { featureType: 'road.highway', elementType: 'labels.text.fill', stylers: [{ color: '#dbe3ff' }] },
    { featureType: 'transit', elementType: 'geometry', stylers: [{ color: '#262c3d' }] },
    { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0e1524' }] },
    { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#4b5a7a' }] },
  ];

  let promesaGoogle = null;
  /** Carga la API de Google Maps una sola vez. Se rechaza si la llave no sirve (Google llama a gm_authFailure). */
  function google(llave) {
    if (!llave) return Promise.reject(new Error('sin llave'));
    if (!promesaGoogle) {
      promesaGoogle = new Promise((resolver, rechazar) => {
        window.__mxGoogleListo = () => resolver(window.google);
        window.gm_authFailure = () => {
          rechazar(new Error('Google rechazó la llave'));
          document.dispatchEvent(new CustomEvent('mx-google-fallo'));
        };
        const sc = document.createElement('script');
        sc.src = 'https://maps.googleapis.com/maps/api/js?key=' + encodeURIComponent(llave) +
          '&v=weekly&loading=async&libraries=places,geocoding&language=es&region=MX&callback=__mxGoogleListo';
        sc.async = true;
        // Las llaves se restringen por dirección (Referer); el programa la oculta por seguridad salvo en el mapa.
        sc.referrerPolicy = 'strict-origin-when-cross-origin';
        sc.onerror = () => rechazar(new Error('Sin conexión con Google'));
        document.head.append(sc);
      });
    }
    return promesaGoogle;
  }

  function enlaceGoogle(lat, lng, texto) {
    // Funciona siempre, con o sin llave: abre Google Maps en otra pestaña.
    const a = document.createElement('a');
    a.href = `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
    a.target = '_blank'; a.rel = 'noopener';
    a.textContent = texto || 'Ver en Google Maps';
    a.className = 'mx-enlace-google';
    return a;
  }

  const esOscuro = () => document.documentElement.classList.contains('dark');

  function crear(caja, opciones = {}) {
    let oscuro = esOscuro();
    const mapa = L.map(caja, {
      zoomControl: opciones.zoomControl !== false, scrollWheelZoom: !!opciones.rueda,
      maxBounds: L.latLngBounds(MEXICO).pad(0.1), minZoom: 4,
    });
    mapa.fitBounds(ZONA_PLANTELES);
    mapa.attributionControl.setPrefix(false);
    // Los estados van debajo de los puntos (si no, su relleno los deslava).
    mapa.createPane('estados').style.zIndex = 250;
    // Con fondo de calles los estados son solo contorno; sin internet se rellenan para que se distingan.
    let conFondo = false, capaEstados = null;
    const relleno = () => ({ color: oscuro ? '#6f8ff2' : '#2447b8', weight: 1, opacity: conFondo ? 0.55 : 0.4,
                             fillColor: oscuro ? '#2c2c2e' : '#ffffff', fillOpacity: conFondo ? 0 : 0.7 });
    estados().then((geo) => {
      if (!geo) return;
      capaEstados = L.geoJSON(geo, { interactive: false, style: relleno, pane: 'estados' }).addTo(mapa);
    });
    const sinInternet = () => {
      ponerReferencias(mapa);
      if (opciones.sinInternet) opciones.sinInternet();
    };
    // `tiles` puede ser una URL (compatibilidad) o {url, atribucion, oscurecer, google: {llave, tipo}}.
    const t = typeof opciones.tiles === 'string' ? { url: opciones.tiles, atribucion: '', oscurecer: false } : (opciones.tiles || {});
    const osm = () => ponerOSM(mapa, t, () => { conFondo = true; if (capaEstados) capaEstados.setStyle(relleno); }, sinInternet);
    let capaGoogle = null;
    // Al cambiar de tema (claro/oscuro) el mapa se adapta sin recargar.
    document.addEventListener('udc-tema', () => {
      oscuro = esOscuro();
      if (capaEstados) capaEstados.setStyle(relleno);
      try {
        if (capaGoogle && capaGoogle._mutant) capaGoogle._mutant.setOptions({ styles: oscuro && (t.google.tipo || 'roadmap') === 'roadmap' ? NOCHE : [] });
      } catch (e) { /* versión distinta de GoogleMutant: queda el estilo anterior hasta recargar */ }
    });
    if (t.google && t.google.llave && L.gridLayer.googleMutant) {
      let capaG = null, yaCambio = false;
      const respaldo = () => {
        if (yaCambio) return;
        yaCambio = true;
        if (capaG) { mapa.removeLayer(capaG); capaG = capaGoogle = null; }
        if (opciones.googleFallo) opciones.googleFallo();
        osm();
      };
      document.addEventListener('mx-google-fallo', respaldo, { once: true });
      google(t.google.llave).then(() => {
        capaG = capaGoogle = L.gridLayer.googleMutant({ type: t.google.tipo || 'roadmap', maxZoom: 20,
          styles: (t.google.tipo || 'roadmap') === 'roadmap' && oscuro ? NOCHE : [] }).addTo(mapa);
        conFondo = true; if (capaEstados) capaEstados.setStyle(relleno);
        mapa.attributionControl.addAttribution('Estados: Natural Earth');
      }).catch(respaldo);
      return mapa;
    }
    osm();
    return mapa;
  }

  function ponerOSM(mapa, t, alCargar, sinInternet) {
    if (t && t.url) {
      const capa = L.tileLayer(t.url, {
        maxZoom: 19, subdomains: 'abc',
        // El programa no manda «Referer» por seguridad; OpenStreetMap lo exige para servir mosaicos.
        referrerPolicy: 'strict-origin-when-cross-origin',
        className: t.oscurecer ? 'mx-tiles-oscuros' : '',  // el CSS solo los oscurece en tema oscuro
        attribution: [t.atribucion, 'Estados: Natural Earth'].filter(Boolean).join(' · '),
      });
      let fallos = 0, cargados = 0;
      capa.on('tileerror', () => { if (++fallos === 4 && !cargados) sinInternet(); });
      capa.on('tileload', () => { if (++cargados === 1) alCargar(); });
      capa.addTo(mapa);
    } else sinInternet();
  }

  /** Marcador de un plantel: el escudo de su universidad en una insignia, con el nombre debajo (o solo el escudo). */
  function escudoSede(s, compacto) {
    const caja = document.createElement('div');
    caja.className = 'mc-sede mc-sede-' + (s.clave || '') + (compacto ? ' compacto' : '');
    const disco = document.createElement('span'); disco.className = 'mc-sede-disco';
    const img = document.createElement('img'); img.src = s.escudo; img.alt = ''; img.draggable = false;
    disco.append(img); caja.append(disco);
    if (!compacto) { const n = document.createElement('span'); n.className = 'mc-sede-nombre'; n.textContent = s.nombre; caja.append(n); }
    return caja;
  }

  return { crear, cuandoTengaTamano, google, enlaceGoogle, escudoSede, ZONA_PLANTELES };
})();
