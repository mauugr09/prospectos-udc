#!/usr/bin/env bash
# «ITV» del programa: la misma revisión que hace GitHub antes de aceptar un cambio.
# Uso:  bash empaquetado/itv.sh          (todo)
#       bash empaquetado/itv.sh rapida   (sin las pruebas lentas de MariaDB: lo que corre antes de cada push)
set -uo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python )}
fallas=()
paso() { local nombre="$1"; shift; printf '\n▶ %s\n' "$nombre"; if "$@"; then echo "  ✓ $nombre"; else echo "  ✗ $nombre"; fallas+=("$nombre"); fi; }

paso 'Estilo y errores comunes (ruff)'        "$PY" -m ruff check .
paso 'Seguridad del código (bandit)'          "$PY" -m bandit -q -r prospectos config lanzador.py -x prospectos/migrations -ll -ii
paso 'Dependencias con fallas conocidas'       "$PY" -m pip_audit -r requirements.txt --progress-spinner off
paso 'Migraciones al día'                      "$PY" manage.py makemigrations --check --dry-run --settings=config.settings_pruebas
paso 'Pruebas y cobertura (mínimo 80 %)'       "$PY" -m pytest -q -o addopts="" --cov=prospectos --cov=config --cov-report=term:skip-covered --cov-fail-under=80

echo
if [ ${#fallas[@]} -eq 0 ]; then echo '✅ Pasó la ITV.'; else printf '❌ No pasó la ITV: %s\n' "${fallas[*]}"; exit 1; fi
