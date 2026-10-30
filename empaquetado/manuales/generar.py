"""Manuales en PDF: markdown → HTML con portada e índice → PDF (Chromium vía Playwright).
Uso: pip install markdown pypdf playwright && playwright install chromium; python empaquetado/manuales/generar.py
"""
import html, pathlib, re, sys, tempfile

import markdown
from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parents[2]
TMP = pathlib.Path(tempfile.mkdtemp())
DOCS = REPO / 'docs'
FUENTES = REPO / 'prospectos/static/prospectos/fuentes'
MANUALES = [
    ('manual-usuario.md', 'Manual-de-usuario.pdf', 'Manual de usuario', 'Admisiones, coordinación, promotores y directivos', []),
    ('manual-instalacion-operacion.md', 'Manual-de-instalacion-y-operacion.pdf', 'Manual de instalación y operación',
     'Instalación, respaldos, actualización y recuperación', ['puesta-en-marcha.md', 'formularios.md', 'mariadb.md', 'seguridad.md']),
    ('tecnica.md', 'Documentacion-tecnica.pdf', 'Documentación técnica', 'Arquitectura, modelo de datos, mantenimiento y construcción',
     ['decisiones.md', 'autoria.md']),
]
ANEXO_TITULO = {'puesta-en-marcha.md': 'Anexo A', 'formularios.md': 'Anexo B', 'mariadb.md': 'Anexo C', 'seguridad.md': 'Anexo D',
                'decisiones.md': 'Anexo A', 'autoria.md': 'Anexo B'}

CSS = f"""
@font-face {{ font-family: Montserrat; font-weight: 400; src: url('file://{FUENTES}/montserrat-latin-400-normal.woff2'); }}
@font-face {{ font-family: Montserrat; font-weight: 600; src: url('file://{FUENTES}/montserrat-latin-600-normal.woff2'); }}
@font-face {{ font-family: Montserrat; font-weight: 700; src: url('file://{FUENTES}/montserrat-latin-700-normal.woff2'); }}
@font-face {{ font-family: Montserrat; font-weight: 800; src: url('file://{FUENTES}/montserrat-latin-800-normal.woff2'); }}
@font-face {{ font-family: 'Open Sans'; font-weight: 400; src: url('file://{FUENTES}/open-sans-latin-400-normal.woff2'); }}
@font-face {{ font-family: 'Open Sans'; font-weight: 600; src: url('file://{FUENTES}/open-sans-latin-600-normal.woff2'); }}
@font-face {{ font-family: 'Open Sans'; font-weight: 700; src: url('file://{FUENTES}/open-sans-latin-700-normal.woff2'); }}
@page {{ size: Letter; margin: 22mm 20mm 20mm 20mm; }}
:root {{ --marino: #172852; --rey: #2447b8; --texto: #1d1d1f; --suave: #5f6270; --linea: #dfe1e8; --fondo: #f4f5f8; }}
* {{ box-sizing: border-box; }}
body {{ font-family: 'Open Sans', sans-serif; font-size: 10.3pt; line-height: 1.55; color: var(--texto); margin: 0; }}
h1, h2, h3, h4 {{ font-family: Montserrat, sans-serif; color: var(--marino); line-height: 1.25; break-after: avoid; }}
h1 {{ font-size: 21pt; font-weight: 800; margin: 0 0 6pt; letter-spacing: -.01em; }}
h2 {{ font-size: 15pt; font-weight: 700; margin: 22pt 0 8pt; padding-top: 4pt; border-top: 2px solid var(--marino); }}
h3 {{ font-size: 12pt; font-weight: 700; margin: 16pt 0 6pt; color: var(--rey); }}
h4 {{ font-size: 10.5pt; margin: 12pt 0 4pt; }}
p, li {{ orphans: 3; widows: 3; }}
a {{ color: var(--rey); text-decoration: none; }}
strong {{ font-weight: 700; }}
code {{ font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 8.8pt; background: var(--fondo); padding: 1px 4px; border-radius: 3px; }}
pre {{ background: #10162b; color: #e8ecf8; padding: 9pt 11pt; border-radius: 6px; font-size: 8.6pt; white-space: pre-wrap; break-inside: avoid; }}
pre code {{ background: none; color: inherit; padding: 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 8pt 0 12pt; font-size: 9pt; break-inside: auto; }}
th {{ background: var(--marino); color: #fff; text-align: left; font-family: Montserrat; font-weight: 600; padding: 5pt 7pt; }}
td {{ border-bottom: 1px solid var(--linea); padding: 5pt 7pt; vertical-align: top; }}
tr {{ break-inside: avoid; }}
tbody tr:nth-child(even) td {{ background: #fafbfc; }}
blockquote {{ margin: 10pt 0; padding: 8pt 12pt; border-left: 4px solid var(--rey); background: #eef2fc; border-radius: 0 6px 6px 0; break-inside: avoid; }}
blockquote p {{ margin: 0; }}
img {{ max-width: 100%; border: 1px solid var(--linea); border-radius: 6px; margin: 6pt 0 10pt; box-shadow: 0 2px 6px rgba(0,0,0,.08); break-inside: avoid; }}
p:has(> img:only-child) {{ break-inside: avoid; text-align: center; }}
hr {{ border: 0; border-top: 1px solid var(--linea); margin: 14pt 0; }}
.portada {{ height: 279.4mm; width: 215.9mm; position: relative; background: linear-gradient(160deg, #172852 0%, #1f3a8a 58%, #2447b8 100%);
  color: #fff; padding: 34mm 24mm; break-after: page; overflow: hidden; }}
.portada::after {{ content: ''; position: absolute; right: -40mm; bottom: -50mm; width: 160mm; height: 160mm; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,.12), transparent 65%); }}
.portada .marca {{ font-family: Montserrat; font-weight: 700; letter-spacing: .18em; font-size: 9pt; text-transform: uppercase; opacity: .8; }}
.portada .producto {{ font-family: Montserrat; font-weight: 800; font-size: 46pt; margin-top: 52mm; letter-spacing: -.02em; }}
.portada .titulo {{ font-family: Montserrat; font-weight: 600; font-size: 22pt; margin-top: 4mm; }}
.portada .sub {{ font-size: 12pt; opacity: .85; margin-top: 4mm; max-width: 140mm; }}
.portada .linea {{ width: 26mm; height: 3px; background: linear-gradient(90deg, #2E8B3E 33%, #fff 33% 66%, #D32F2F 66%); margin-top: 10mm; }}
.portada .pie {{ position: absolute; left: 24mm; bottom: 24mm; font-size: 9.5pt; opacity: .85; line-height: 1.6; }}
.indice {{ break-after: page; }}
.indice h2 {{ border: 0; margin-top: 0; }}
.indice ol {{ list-style: none; padding: 0; columns: 1; }}
.indice li {{ display: flex; gap: 8pt; padding: 4pt 0; border-bottom: 1px dotted var(--linea); font-size: 10.5pt; }}
.indice li.sub {{ padding-left: 16pt; font-size: 9.5pt; color: var(--suave); }}
.anexo {{ break-before: page; }}
.anexo > h1:first-child::before {{ content: attr(data-anexo) ' · '; color: var(--rey); }}
"""

def md_a_html(texto, base_rel=''):
    texto = re.sub(r'\]\((?!https?:|#|mailto:)([^)]+?\.md)(#[^)]*)?\)', lambda m: '](#)', texto)  # enlaces a otros .md: sin enlace
    h = markdown.markdown(texto, extensions=['tables', 'fenced_code', 'sane_lists', 'toc'], output_format='html5')
    return h.replace('src="img/', f'src="file://{DOCS}/img/')

def indice(cuerpo, anexos=()):
    filas = []
    for nivel, texto in re.findall(r'<h([23])[^>]*>(.*?)</h\1>', cuerpo):
        t = re.sub('<[^>]+>', '', texto)
        filas.append(f'<li class="{"sub" if nivel == "3" else ""}">{t}</li>')
    for etiqueta, nombre in anexos:
        filas.append(f'<li><b>{etiqueta}</b>&nbsp;· {nombre}</li>')
    return '<section class="indice"><h2>Contenido</h2><ol>' + ''.join(filas) + '</ol></section>'

def generar(fuente, salida, titulo, sub, anexos, version, fecha):
    principal = (DOCS / fuente).read_text(encoding='utf-8')
    principal = re.sub(r'^# .*\n', '', principal, count=1)  # el título va en la portada
    cuerpo = md_a_html(principal)
    # Los anexos que solo remitían a un archivo: se reemplazan por el documento completo
    cuerpo = re.sub(r'<h2[^>]*>Anexo [A-D]\..*?</h2>\s*<p>.*?</p>(\s*<p>.*?</p>)?', '', cuerpo, flags=re.S)
    principal_html = cuerpo
    lista_anexos = []
    for a in anexos:
        t = re.search(r'^# (.+)$', (DOCS / a).read_text(encoding='utf-8'), re.M)
        lista_anexos.append((ANEXO_TITULO[a], t.group(1) if t else a))
        cuerpo += f'<section class="anexo" data-anexo="{ANEXO_TITULO[a]}">' + md_a_html((DOCS / a).read_text(encoding='utf-8')) + '</section>'
    portada = f'''<section class="portada"><div class="marca">NullSpace Studio</div><div class="producto">Prospectos</div>
      <div class="titulo">{titulo}</div><div class="sub">{sub}</div><div class="linea"></div>
      <div class="pie">Versión {version} · {fecha}<br>Sistema de admisiones · Universidad de Cuautitlán<br>© 2026 NullSpace Studio. Todos los derechos reservados.</div></section>'''
    cabeza = f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{titulo}</title><style>{CSS}</style></head><body>'
    paginas = {'portada': cabeza.replace('</style>', '@page { margin: 0 }</style>') + portada + '</body></html>', 'cuerpo': cabeza + indice(principal_html, lista_anexos) + cuerpo + '</body></html>'}
    from pypdf import PdfReader, PdfWriter
    pie = (f'<div style="font-family:Arial;font-size:7.5pt;color:#8a8d99;width:100%;padding:0 20mm;display:flex;justify-content:space-between">'
           f'<span>Prospectos · {html.escape(titulo)} · v{version}</span><span>© 2026 NullSpace Studio · <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
    partes = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for nombre, contenido in paginas.items():
            tmp = TMP / f'{salida}.{nombre}.html'
            tmp.write_text(contenido, encoding='utf-8')
            pg = b.new_page()
            pg.goto(tmp.as_uri(), wait_until='networkidle')
            destino = tmp.with_suffix('.pdf')
            pg.pdf(path=str(destino), format='Letter', print_background=True, prefer_css_page_size=True,
                   display_header_footer=nombre == 'cuerpo', header_template='<div></div>', footer_template=pie)
            partes.append(destino)
        b.close()
    w = PdfWriter()
    for parte in partes:
        for pagina in PdfReader(str(parte)).pages:
            w.add_page(pagina)
    w.add_metadata({'/Title': f'Prospectos · {titulo}', '/Author': 'NullSpace Studio', '/Subject': sub})
    with open(DOCS / salida, 'wb') as f:
        w.write(f)
    print(salida, (DOCS / salida).stat().st_size // 1024, 'KB')

if __name__ == '__main__':
    sys.path.insert(0, str(REPO))
    from config import version as v
    for m in MANUALES:
        generar(*m, v.VERSION, 'octubre de 2026')
