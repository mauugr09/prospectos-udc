# Prospectos como servidor (una sola base de datos para todos). Ver docs/servidor.md.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROSPECTOS_DATOS=/datos \
    PROSPECTOS_BD_BIN=/usr/bin \
    PROSPECTOS_ESCUCHAR=0.0.0.0:8000

# mariadb-client: mariadb-dump y mariadb, para los respaldos automáticos y su verificación.
RUN apt-get update \
 && apt-get install -y --no-install-recommends mariadb-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Estáticos dentro de la imagen (whitenoise los sirve comprimidos). La carpeta temporal evita crear llaves aquí.
RUN PROSPECTOS_DATOS=/tmp/construir python manage.py collectstatic --noinput -v0 && rm -rf /tmp/construir

RUN useradd --system --uid 1000 --home /datos prospectos \
 && mkdir -p /datos && chown prospectos /datos
USER prospectos
VOLUME ["/datos"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salud/', timeout=4)"

CMD ["python", "servidor.py"]
