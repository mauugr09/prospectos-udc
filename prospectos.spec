# -*- mode: python ; coding: utf-8 -*-
# Construye dist/Prospectos/ (carpeta portable): Prospectos.exe en Windows, Prospectos en Mac.
# En Mac, empaquetado/mac/construir.sh la mete después dentro de Prospectos.app.
# Uso:  python -m PyInstaller --noconfirm prospectos.spec
# Antes: python manage.py collectstatic --noinput   (genera staticfiles/)
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
datas += collect_data_files('django')             # plantillas del admin, traducciones al español, estáticos
datas += collect_data_files('prospectos')          # plantillas, estáticos, fuentes y traducciones propias
datas += collect_data_files('unfold')              # tema del panel
datas += collect_data_files('tzdata')              # zonas horarias (Windows no trae base IANA)
datas += collect_data_files('certifi')
datas += [('staticfiles', 'staticfiles')]
datas += [('docs/manual-usuario.md', 'docs'), ('docs/manual-instalacion-operacion.md', 'docs')]  # el asistente los consulta sin IA

_fuera = ('django.contrib.gis', 'django.contrib.postgres', 'django.db.backends.oracle',
          'django.db.backends.postgresql', 'django.test')
hiddenimports = (collect_submodules('django', filter=lambda n: not n.startswith(_fuera)) + collect_submodules('prospectos') + collect_submodules('config')
                 + collect_submodules('unfold') + collect_submodules('pymysql') + collect_submodules('google_auth_oauthlib')
                 + collect_submodules('waitress') + collect_submodules('whitenoise') + collect_submodules('cheroot') + ['tzdata'])

a = Analysis(
    ['lanzador.py'],
    pathex=['.'],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=['tkinter', 'pytest', 'pytest_django', 'IPython', 'django.contrib.gis', 'django.contrib.postgres',
              'django.db.backends.oracle', 'django.db.backends.postgresql'],
    module_collection_mode={
        # Django busca comandos y migraciones recorriendo carpetas: se incluyen también los .py.
        'django': 'pyz+py',
        'prospectos': 'pyz+py',
        'config': 'pyz+py',
        'unfold': 'pyz+py',
    },
    noarchive=False,
)
pyz = PYZ(a.pure)
# Modo UTF-8 de Python: open() sin encoding usa UTF-8 también en Windows (acentos y ñ en archivos).
MAC = sys.platform == 'darwin'
exe = EXE(pyz, a.scripts, [('X utf8', None, 'OPTION')], exclude_binaries=True, name='Prospectos', console=True, upx=False,
          icon=None if MAC else 'empaquetado/Prospectos.ico',
          target_arch='arm64' if MAC else None,  # Macs con chip Apple (M1 en adelante)
          version='version.txt' if __import__('os').path.exists('version.txt') else None)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name='Prospectos')
