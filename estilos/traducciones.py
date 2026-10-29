"""
Traducciones al español de los textos de django-unfold (no trae catálogo en español).
Genera prospectos/locale/es/LC_MESSAGES/django.mo sin necesitar gettext:
    python estilos/traducciones.py
"""
import array
import pathlib

T = {
    'Light': 'Claro',
    'Dark': 'Oscuro',
    'System': 'Sistema',
    "After you've created a user, you’ll be able to edit more user options.": 'Escribe los datos de la persona y su rol. Al guardar verás su contraseña temporal.',
    'Select an option': 'Elige una opción',
    '- Select an option -': '— Elige una opción —',
    'Welcome back to': 'Bienvenido de nuevo a',
    'Search apps and models...': 'Buscar en el menú…',
    'Type to search': 'Escribe para buscar',
    'Apply Filters': 'Aplicar filtros',
    'Filters': 'Filtros',
    'Reset filters': 'Quitar filtros',
    'Clear all filters': 'Quitar todos los filtros',
    'Toggle filter': 'Mostrar u ocultar filtros',
    'Select action': 'Elige una acción',
    'Select action to run': 'Elige la acción a ejecutar',
    'Run': 'Ejecutar',
    'Run the selected action': 'Ejecutar la acción elegida',
    'Toggle dark/light mode': 'Cambiar tema claro u oscuro',
    'Toggle sidebar': 'Mostrar u ocultar el menú',
    'Toggle password visibility': 'Mostrar u ocultar contraseña',
    'Toggle sorting': 'Cambiar orden',
    'Light': 'Claro',
    'Dark': 'Oscuro',
    'System': 'Sistema',
    'No results found': 'Sin resultados',
    'Nothing matched your search': 'Nada coincide con tu búsqueda',
    'This page yielded into no results.': 'Esta página no tiene resultados.',
    'Recent searches': 'Búsquedas recientes',
    'Open command tool': 'Abrir búsqueda rápida',
    'Return to site': 'Volver al sitio',
    'Show counts': 'Mostrar conteos',
    'Hide counts': 'Ocultar conteos',
    'No data': 'Sin datos',
    'Not enough data.': 'No hay datos suficientes.',
    'Create new record': 'Crear registro',
    'Add new item': 'Agregar elemento',
    'Add row': 'Agregar fila',
    'Go back': 'Regresar',
    'Close': 'Cerrar',
    'Collapse': 'Contraer',
    'Date from': 'Desde',
    'Date to': 'Hasta',
    'Record picture': 'Imagen del registro',
    'All applications': 'Todas las secciones',
    'Select record': 'Seleccionar registro',
    'Open selection': 'Abrir selección',
    'Open selection in new tab': 'Abrir selección en otra pestaña',
    'Available shortcuts': 'Atajos disponibles',
    'Global shortcuts': 'Atajos generales',
    'Changelist shortcuts': 'Atajos de listados',
    'Command tool shortcuts': 'Atajos de búsqueda rápida',
    'Open shortcuts list': 'Ver atajos de teclado',
    'Navigate': 'Navegar',
    'Changes': 'Cambios',
    'Change History': 'Historial de cambios',
    'Changed by': 'Modificado por',
    'Unknown': 'Desconocido',
    'Submit': 'Enviar',
    'Select': 'Seleccionar',
    'Default': 'Predeterminado',
    'Update': 'Actualizar',
}


def escribir_mo(traducciones: dict, destino: pathlib.Path) -> None:
    entradas = {'': 'Content-Type: text/plain; charset=UTF-8\nLanguage: es\n', **traducciones}
    claves = sorted(entradas)
    ids, strs, offsets = b'', b'', []
    for k in claves:
        kb, vb = k.encode(), entradas[k].encode()
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b'\0'
        strs += vb + b'\0'
    n = len(claves)
    inicio_k = 7 * 4 + 16 * n
    inicio_v = inicio_k + len(ids)
    tabla = []
    for o1, l1, o2, l2 in offsets:
        tabla += [l1, o1 + inicio_k]
    for o1, l1, o2, l2 in offsets:
        tabla += [l2, o2 + inicio_v]
    cabecera = array.array('I', [0x950412de, 0, n, 7 * 4, 7 * 4 + n * 8, 0, 0])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(cabecera.tobytes() + array.array('I', tabla).tobytes() + ids + strs)


if __name__ == '__main__':
    raiz = pathlib.Path(__file__).resolve().parent.parent
    escribir_mo(T, raiz / 'prospectos' / 'locale' / 'es' / 'LC_MESSAGES' / 'django.mo')
    print('ok')
