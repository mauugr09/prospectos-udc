/* Inicio: gráfica de actividad y mapa. Toma los colores del tema (claro u oscuro) y se repinta al cambiarlo. */
(function () {
  const nodo = document.getElementById('datos-tablero');
  if (!nodo) return;
  const d = JSON.parse(nodo.textContent);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const tema = () => ({ texto: css('--c-texto-2') || '#8e8e93', separador: css('--c-separador') || 'rgba(60,60,67,.16)',
                        acento: css('--c-acento') || '#2447b8', acentoSuave: css('--c-acento-suave') || 'rgba(36,71,184,.1)',
                        superficie: css('--c-superficie') || '#fff' });
  let c = tema();
  const graficas = [];
  if (window.Chart) { Chart.defaults.font.family = getComputedStyle(document.body).fontFamily; Chart.defaults.color = c.texto; }
  document.addEventListener('udc-tema', () => {
    c = tema();
    if (window.Chart) Chart.defaults.color = c.texto;
    graficas.forEach((g) => g.repintar());
  });

  // ---------------------------------------------------------------- línea chica de las tarjetas de arriba
  const lineas = [...document.querySelectorAll('canvas.tb-kpi-linea[data-serie="actividad"]')];
  const pintarLinea = (cv) => {
    const v = d.actividad.valores || [];
    const r = cv.getBoundingClientRect(), k = window.devicePixelRatio || 1;
    if (!r.width || v.length < 2) return;
    cv.width = r.width * k; cv.height = r.height * k;
    const g = cv.getContext('2d'); g.scale(k, k);
    const max = Math.max(...v, 1), paso = r.width / (v.length - 1), y = (n) => r.height - 3 - (n / max) * (r.height - 6);
    const grad = g.createLinearGradient(0, 0, r.width, 0);
    grad.addColorStop(0, '#f2a33a'); grad.addColorStop(1, '#2bb673');
    g.beginPath(); v.forEach((n, i) => (i ? g.lineTo(i * paso, y(n)) : g.moveTo(0, y(n))));
    g.strokeStyle = grad; g.lineWidth = 2; g.lineJoin = 'round'; g.lineCap = 'round'; g.stroke();
  };
  // La página arranca oculta hasta que carga Alpine: se pinta cuando el lienzo ya tiene tamaño.
  if ('ResizeObserver' in window) lineas.forEach((cv) => new ResizeObserver(() => pintarLinea(cv)).observe(cv));
  else lineas.forEach(pintarLinea);

  // ---------------------------------------------------------------- actividad (una línea; el detalle aparece al pasar el mouse)
  const lienzo = document.getElementById('g-actividad');
  if (lienzo && window.Chart) {
    const a = d.actividad;
    const max = Math.max(...a.valores, 0);
    let activo = -1;
    const tip = document.getElementById('g-actividad-tip');
    const mostrar = (chart) => {
      if (!tip) return;
      const p = activo >= 0 && chart.getDatasetMeta(0).data[activo];
      if (!p) { tip.hidden = true; return; }
      tip.hidden = false;
      tip.replaceChildren();
      const b = document.createElement('b'); b.textContent = a.valores[activo];
      const s = document.createElement('small'); s.textContent = a.etiquetas[activo];
      tip.append(b, s);
      tip.style.left = p.x + 'px'; tip.style.top = (p.y - 12) + 'px';
    };
    const guia = {
      id: 'guia',
      beforeDatasetsDraw(chart) {
        if (activo < 0) return;
        const { ctx, chartArea, scales } = chart;
        const x = scales.x.getPixelForValue(activo);
        ctx.save(); ctx.strokeStyle = c.separador; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke(); ctx.restore();
      },
      afterDatasetsDraw: mostrar,
    };
    const relleno = (ctx) => {
      const area = ctx.chart.chartArea;
      if (!area) return 'transparent';
      const g = ctx.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
      g.addColorStop(0, c.acentoSuave); g.addColorStop(1, 'transparent');
      return g;
    };
    const linea = new Chart(lienzo, {
      type: 'line',
      data: { labels: a.etiquetas, datasets: [{ data: a.valores, borderColor: c.acento, backgroundColor: relleno, fill: true,
        tension: .35, cubicInterpolationMode: 'monotone', borderWidth: 2,
        pointRadius: (x) => x.dataIndex === activo ? 4.5 : 0, pointHoverRadius: 4.5,
        pointBackgroundColor: c.acento, pointBorderColor: c.superficie, pointBorderWidth: 2 }] },
      options: {
        maintainAspectRatio: false, animation: { duration: 500, easing: 'easeOutCubic' },
        interaction: { mode: 'index', intersect: false },
        onHover(e, el, chart) {
          const i = el.length ? el[0].index : -1;
          if (i !== activo) { activo = i; chart.update('none'); }
        },
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
          x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 18, font: { size: 11 } } },
          y: { beginAtZero: true, suggestedMax: Math.ceil(Math.max(1, max) * 1.15), position: 'right',
               grid: { color: c.separador, drawTicks: false }, border: { display: false },
               ticks: { precision: 0, maxTicksLimit: 4, padding: 8, font: { size: 11 } } },
        },
      },
      plugins: [guia],
    });
    lienzo.addEventListener('mouseleave', () => { activo = -1; linea.update('none'); });
    graficas.push({ repintar() {
      linea.options.scales.y.grid.color = c.separador;
      linea.options.scales.x.ticks.color = linea.options.scales.y.ticks.color = c.texto;
      const ds = linea.data.datasets[0];
      ds.borderColor = ds.pointBackgroundColor = c.acento; ds.pointBorderColor = c.superficie;
      linea.update('none');
    } });
  }

  // ---------------------------------------------------------------- mapa (puntos de las preparatorias)
  // La página arranca oculta (x-cloak) hasta que carga Alpine: el mapa se crea cuando ya tiene tamaño.
  const caja = document.getElementById('tb-mapa');
  const crearMapa = () => {
    const mapa = MapaMX.crear(caja, { tiles: d.tiles, zoomControl: false });
    const puntos = d.puntos.filter((p) => p.lat && p.lng);
    if (!puntos.length) return;  // queda la vista de la zona de los planteles
    const limites = L.latLngBounds(puntos.map((p) => [p.lat, p.lng]));
    mapa.fitBounds(limites.pad(.25));  // primero la vista; después los pines
    const capa = [];
    const max = Math.max(1, ...puntos.map((p) => p.total));
    puntos.forEach((p, i) => {
      const lado = Math.round(10 + 12 * Math.sqrt(p.total / max));
      const icono = L.divIcon({ className: 'tb-pin', iconSize: [lado, lado], iconAnchor: [lado / 2, lado / 2],
        html: `<span class="tb-pin-gota" style="width:${lado}px;height:${lado}px;margin:-${lado / 2}px 0 0 -${lado / 2}px"></span>` });
      const m = L.marker([p.lat, p.lng], { icon: icono }).addTo(mapa);
      const div = document.createElement('div');
      const b = document.createElement('b'); b.textContent = p.nombre;
      const s = document.createElement('div');
      s.textContent = `${p.total} aspirante${p.total === 1 ? '' : 's'}${p.municipio ? ', ' + p.municipio : ''}. Cuautitlán ${p.cuautitlan}, Tultepec ${p.tultepec}.`;
      div.append(b, s);
      m.bindTooltip(div, { direction: 'top', offset: [0, -lado / 2 - 4], className: 'tb-mapa-tip' });
      capa.push(m);
    });
  };
  if (caja && window.L) {
    const esperar = () => (caja.offsetWidth > 0 && caja.offsetHeight > 0 ? crearMapa() : requestAnimationFrame(esperar));
    esperar();
  }
})();
