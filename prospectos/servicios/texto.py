"""Normalización de texto y similitud de nombres en español."""

import re
import unicodedata

PARTICULAS = {'de', 'del', 'la', 'las', 'los', 'y', 'van', 'von', 'da', 'dos'}


def limpiar(texto: str) -> str:
    texto = re.sub(r'[\x00-\x1f\x7f]+', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()


def normalizar(texto: str | None) -> str:
    """Minúsculas, sin acentos, solo [a-z0-9 ]."""
    if not texto:
        return ''
    t = unicodedata.normalize('NFD', texto.strip())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn').lower().replace('ñ', 'n')
    t = re.sub(r'[^a-z0-9 ]+', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def _variantes(token: str) -> str:
    # Variantes ortográficas frecuentes: Ximena/Jimena, Peres/Perez, Baleria/Valeria, Yesenia/Llesenia, H muda.
    token = re.sub(r'^x(?=[ie])', 'j', token)
    token = token.replace('z', 's').replace('ll', 'y').replace('v', 'b')
    token = re.sub(r'(?<!c)h(?=[aeiou])', '', token)
    return re.sub(r'^h', '', token)


def clave_nombre(nombre: str | None) -> str:
    """Clave canónica: normalizado, sin partículas, con variantes y tokens ORDENADOS."""
    tokens = [t for t in normalizar(nombre).split(' ') if t and t not in PARTICULAS]
    return ' '.join(sorted(_variantes(t) for t in tokens))


def jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 0.0 if a == '' else 1.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    ventana = max(0, max(la, lb) // 2 - 1)
    ma, mb = [False] * la, [False] * lb
    m = 0
    for i in range(la):
        for j in range(max(0, i - ventana), min(i + ventana + 1, lb)):
            if not mb[j] and a[i] == b[j]:
                ma[i] = mb[j] = True
                m += 1
                break
    if not m:
        return 0.0
    t, k = 0, 0
    for i in range(la):
        if ma[i]:
            while not mb[k]:
                k += 1
            if a[i] != b[k]:
                t += 1
            k += 1
    jaro = (m / la + m / lb + (m - t / 2) / m) / 3
    prefijo = 0
    for i in range(min(4, la, lb)):
        if a[i] != b[i]:
            break
        prefijo += 1
    return jaro + prefijo * 0.1 * (1 - jaro)


def similitud_nombres(a: str | None, b: str | None) -> float:
    """
    Similitud por tokens: empareja tokens (Jaro-Winkler, voraz global) y penaliza la
    cobertura, para que a un nombre al que le falta un apellido le toque revisión manual.
    """
    ta = [t for t in clave_nombre(a).split(' ') if t]
    tb = [t for t in clave_nombre(b).split(' ') if t]
    if not ta or not tb:
        return 0.0
    cortos, largos = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    pares = sorted(((jaro_winkler(x, y), i, j) for i, x in enumerate(cortos) for j, y in enumerate(largos)), reverse=True)
    usados_i, usados_j, suma, emparejados = set(), set(), 0.0, 0
    for s, i, j in pares:
        if i in usados_i or j in usados_j:
            continue
        usados_i.add(i)
        usados_j.add(j)
        suma += s
        if s >= 0.88:
            emparejados += 1
    promedio = suma / len(cortos)
    cobertura = emparejados / len(largos)
    return round(promedio * (0.5 + 0.5 * cobertura), 4)


def si_no(valor: str | None) -> str | None:
    v = normalizar(valor)
    if v.startswith('si'):
        return 'si'
    if v.startswith('no'):
        return 'no'
    return None


def clave_catalogo(valor: str | None, catalogo: dict[str, str]) -> str | None:
    v = normalizar(valor)
    if not v:
        return None
    for clave, texto in catalogo.items():
        t = normalizar(texto)
        if v in (t, normalizar(clave)) or v.startswith(t) or t.startswith(v):
            return clave
    return None


_RUIDO_PREPA = {'escuela', 'esc', 'preparatoria', 'prepa', 'prep', 'oficial', 'of', 'ofic', 'numero', 'num', 'no', 'n', 'nro', 'de', 'del', 'la',
                'el', 'los', 'las', 'y', 'bachillerato', 'plantel'}


def clave_prepa(nombre: str | None) -> str:
    """
    Clave para comparar nombres de preparatoria escritos a mano: quita las palabras que todos ponen
    distinto («Escuela Preparatoria Oficial Núm. 45» y «Prepa 45» → «45»). Siglas como CBT, CECyTEM,
    CONALEP o CCH se conservan porque sí distinguen escuelas.
    """
    n = normalizar(nombre)
    clave = ' '.join(t for t in n.split(' ') if t and t not in _RUIDO_PREPA)
    return clave or n


def entero(valor: str | None, minimo: int = 0, maximo: int = 10 ** 9) -> int | None:
    """Primer número dentro de un texto libre («17 años» → 17). Fuera de rango → None."""
    m = re.search(r'\d+', valor or '')
    if not m:
        return None
    n = int(m.group())
    return n if minimo <= n <= maximo else None


def clave_opcion(valor: str | None, opciones: dict[str, list[str]]) -> str | None:
    """Como clave_catalogo, pero cada opción puede tener varios textos (el actual y los anteriores)."""
    v = normalizar(valor)
    if not v:
        return None
    for clave, textos in opciones.items():
        normal = [normalizar(t) for t in textos if t] + [normalizar(clave)]
        if v in normal:
            return clave
    for clave, textos in opciones.items():  # coincidencia parcial (p. ej. sin el punto final)
        for t in (normalizar(x) for x in textos if x):
            if t and (v.startswith(t) or t.startswith(v)):
                return clave
    return None
