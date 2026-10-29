"""Textos que cambian según la preparatoria en las cartas oficiales (solicitud y cartas de beca)."""

from __future__ import annotations

from .texto import normalizar

# Primera palabra del nombre → artículo. «CBT», «CETIS», «Colegio»… son masculinos; lo demás se trata como preparatoria.
_FEMENINO = {'preparatoria', 'prepa', 'escuela', 'universidad', 'normal', 'secundaria', 'unidad', 'academia', 'facultad', 'enp', 'epo', 'eso'}
_MASCULINO = {'instituto', 'colegio', 'centro', 'bachillerato', 'plantel', 'liceo', 'cbt', 'cbta', 'cbtis', 'cetis', 'cecyt',
              'cecytem', 'conalep', 'cch', 'cobaem', 'cobach', 'cetmar', 'cbtf', 'telebachillerato', 'emsad', 'cedart'}


def de_la_prepa(nombre: str) -> tuple[str, str]:
    """Para escribir «de la Preparatoria Oficial No. 45» o «del CBT No. 2»: devuelve («de», «la …») o («del», «…»).
    Si el nombre no dice qué es («Isidro Fabela»), se antepone «Preparatoria» para que la frase no quede coja."""
    nombre = (nombre or '').strip()
    if not nombre:
        return 'de', 'su preparatoria'
    primera = normalizar(nombre.split()[0]).strip('.,')
    if primera in _MASCULINO:
        return 'del', nombre
    if primera in _FEMENINO:
        return 'de', f'la {nombre}'
    return 'de', f'la Preparatoria {nombre}'


def folios(codigo_evento: str, desde: int, hasta: int) -> list[str]:
    return [f'{codigo_evento}-{i:03d}' for i in range(desde, hasta + 1)]
