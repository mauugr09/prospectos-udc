/*
 * Teléfonos y tabletas (Android, iPhone, iPad).
 *  - Registra el service worker: permite instalar Prospectos en la pantalla de inicio y, sin red, muestra
 *    «Sin conexión con Prospectos» en vez de un error del navegador. No guarda datos de aspirantes.
 *  - Marca <html> con .app-instalada cuando se abrió desde el icono (sin barra del navegador).
 */
(function () {
  'use strict';
  var html = document.documentElement;
  try {
    var instalada = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || window.navigator.standalone === true;
    if (instalada) html.classList.add('app-instalada');
  } catch (e) { /* navegador viejo: no pasa nada */ }

  if ('serviceWorker' in navigator && window.isSecureContext) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () { /* sin SW el programa funciona igual */ });
    });
  }
})();
