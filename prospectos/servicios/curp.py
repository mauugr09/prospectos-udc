"""
CURP: validación y datos que la propia clave trae dentro. SIN consultar a RENAPO ni a gob.mx.

¿Por qué no se consulta la página del gobierno?
  - gob.mx/curp no tiene API pública; la página usa captcha precisamente para impedir consultas automáticas.
    El acceso oficial a RENAPO requiere convenio con la Secretaría de Gobernación.
  - Consultar un registro oficial de menores para captar prospectos no es proporcional a la finalidad (LFPDPPP).
  - Lo que RENAPO devolvería (fecha de nacimiento, sexo, entidad) ya viene codificado en la CURP; solo
    agregaría el nombre oficial, que el Form ya pregunta.

Estructura (18 caracteres): AAAA AAMMDD S EE CCC H V
  4 letras del nombre · fecha de nacimiento · sexo (H/M/X) · entidad · 3 consonantes internas ·
  homoclave (dígito si nació antes de 2000, letra desde 2000) · dígito verificador.
"""

from __future__ import annotations

import datetime as dt
import re

_PATRON = re.compile(r'^[A-Z][AEIOUX][A-Z]{2}(\d{2})(\d{2})(\d{2})([HMX])([A-Z]{2})[B-DF-HJ-NP-TV-Z]{3}([0-9A-Z])(\d)$')
_ALFABETO = '0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ'

ENTIDADES = {
    'AS': 'Aguascalientes', 'BC': 'Baja California', 'BS': 'Baja California Sur', 'CC': 'Campeche', 'CL': 'Coahuila',
    'CM': 'Colima', 'CS': 'Chiapas', 'CH': 'Chihuahua', 'DF': 'Ciudad de México', 'DG': 'Durango', 'GT': 'Guanajuato',
    'GR': 'Guerrero', 'HG': 'Hidalgo', 'JC': 'Jalisco', 'MC': 'Estado de México', 'MN': 'Michoacán', 'MS': 'Morelos',
    'NT': 'Nayarit', 'NL': 'Nuevo León', 'OC': 'Oaxaca', 'PL': 'Puebla', 'QT': 'Querétaro', 'QR': 'Quintana Roo',
    'SP': 'San Luis Potosí', 'SL': 'Sinaloa', 'SR': 'Sonora', 'TC': 'Tabasco', 'TS': 'Tamaulipas', 'TL': 'Tlaxcala',
    'VZ': 'Veracruz', 'YN': 'Yucatán', 'ZS': 'Zacatecas', 'NE': 'Nacido en el extranjero',
}


def limpiar(valor: str | None) -> str:
    return re.sub(r'[^A-Z0-9Ñ]', '', (valor or '').upper())


def digito_verificador(curp17: str) -> int:
    suma = sum(_ALFABETO.index(c) * (18 - i) for i, c in enumerate(curp17))
    return (10 - suma % 10) % 10


def analizar(valor: str | None) -> dict | None:
    """Devuelve {curp, fecha_nacimiento, sexo, entidad} si la CURP es válida; si no, None."""
    c = limpiar(valor)
    m = _PATRON.match(c)
    if not m or m.group(5) not in ENTIDADES:
        return None
    aa, mm, dd, sexo, _, homoclave, verificador = m.groups()
    siglo = 2000 if homoclave.isalpha() else 1900
    try:
        nacimiento = dt.date(siglo + int(aa), int(mm), int(dd))
    except ValueError:
        return None
    if int(verificador) != digito_verificador(c[:17]):
        return None
    return {'curp': c, 'fecha_nacimiento': nacimiento, 'sexo': {'H': 'hombre', 'M': 'mujer', 'X': 'no binario'}[sexo],
            'entidad': ENTIDADES[m.group(5)]}


def edad(nacimiento: dt.date, hoy: dt.date | None = None) -> int:
    hoy = hoy or dt.date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
