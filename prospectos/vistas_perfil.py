"""Mi perfil (foto, apodo, datos, contraseña, preferencias) y la verificación en 2 pasos."""

import base64
import binascii
import re

from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from unfold.widgets import UnfoldAdminTextInputWidget

from .middleware import SESION_DOS_PASOS, fallo_de_codigo
from .models import Perfil, TipoAviso
from .servicios import auditoria, avisos, dos_pasos
from .views import _ctx

FOTO_MAXIMA = 200 * 1024
SESION_SECRETO = 'dos_pasos_nuevo'


def _tamano_jpeg(datos: bytes):
    """(ancho, alto) leyendo el encabezado SOF del JPEG, o None si no es un JPEG válido."""
    if not datos.startswith(b'\xff\xd8'):
        return None
    i = 2
    while i + 9 < len(datos):
        if datos[i] != 0xFF:
            return None
        marca, largo = datos[i + 1], int.from_bytes(datos[i + 2:i + 4], 'big')
        if marca in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(datos[i + 7:i + 9], 'big'), int.from_bytes(datos[i + 5:i + 7], 'big')
        i += 2 + largo
    return None


def foto_desde_data_url(texto: str) -> bytes:
    m = re.fullmatch(r'data:image/jpeg;base64,([A-Za-z0-9+/=\s]+)', (texto or '').strip())
    if not m:
        raise ValueError('La foto debe ser una imagen JPEG.')
    try:
        datos = base64.b64decode(m.group(1), validate=False)
    except (binascii.Error, ValueError) as e:
        raise ValueError('La foto llegó dañada. Intenta otra vez.') from e
    if len(datos) > FOTO_MAXIMA:
        raise ValueError('La foto es demasiado grande.')
    tam = _tamano_jpeg(datos)
    if not tam or not (32 <= tam[0] <= 1024 and 32 <= tam[1] <= 1024):
        raise ValueError('La foto no es una imagen válida.')
    return datos


def _tipos_de_aviso(user):
    apagados = avisos.apagados(user)
    from .vistas_avisos import ICONOS
    return [{'valor': t.value, 'nombre': t.label, 'icono': ICONOS[t], 'descripcion': avisos.DESCRIPCIONES[t],
             'encendido': t.value not in apagados, 'fijo': t in avisos.OBLIGATORIOS}
            for t in TipoAviso if t not in avisos.OBLIGATORIOS or user.is_superuser]


@staff_member_required
def perfil(request):
    u, p = request.user, Perfil.de(request.user)
    form_clave = PasswordChangeForm(u)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'kuali':  # el interruptor de la ventana de Kuali
            p.kuali_oculto = request.POST.get('oculto') == '1'
            p.save(update_fields=['kuali_oculto'])
            return JsonResponse({'ok': True})
        if accion == 'datos':
            telefono = (request.POST.get('telefono') or '').strip()
            if telefono and not re.fullmatch(r'[\d +()\-]{7,20}', telefono):
                messages.error(request, 'El teléfono solo puede tener números, espacios, + y guiones.')
                return redirect(request.path + '#datos')
            u.first_name = (request.POST.get('first_name') or '').strip()[:150]
            u.last_name = (request.POST.get('last_name') or '').strip()[:150]
            u.save(update_fields=['first_name', 'last_name'])
            p.apodo = re.sub(r'[<>{}]', '', request.POST.get('apodo') or '').strip()[:30]
            p.telefono, p.firma = telefono, (request.POST.get('firma') or '').strip()[:300]
            p.save(update_fields=['apodo', 'telefono', 'firma'])
            auditoria.registrar('perfil_datos', u, {}, request=request)
            messages.success(request, 'Tus datos se guardaron.')
            return redirect(request.path + '#datos')
        if accion == 'foto':
            try:
                p.foto = foto_desde_data_url(request.POST.get('foto'))
            except ValueError as e:
                messages.error(request, str(e))
                return redirect(request.path)
            p.foto_version += 1
            p.save(update_fields=['foto', 'foto_version'])
            messages.success(request, 'Foto actualizada.')
            return redirect(request.path)
        if accion == 'quitar_foto':
            p.foto, p.foto_version = None, p.foto_version + 1
            p.save(update_fields=['foto', 'foto_version'])
            messages.success(request, 'Se quitó tu foto.')
            return redirect(request.path)
        if accion == 'clave':
            form_clave = PasswordChangeForm(u, request.POST)
            if form_clave.is_valid():
                form_clave.save()
                update_session_auth_hash(request, form_clave.user)
                Perfil.objects.filter(usuario=u).update(debe_cambiar_clave=False)
                auditoria.registrar('perfil_clave', u, {}, request=request)
                messages.success(request, 'Tu contraseña cambió. Úsala la próxima vez que entres.')
                return redirect(request.path + '#seguridad')
        if accion == 'preferencias':
            avisos.guardar_preferencias(u, set(request.POST.getlist('tipo')))
            p.kuali_oculto = request.POST.get('kuali_visible') != '1'
            p.save(update_fields=['kuali_oculto'])
            messages.success(request, 'Preferencias guardadas.')
            return redirect(request.path + '#preferencias')
    return render(request, 'prospectos/perfil.html', _ctx(
        request, 'Mi perfil', perfil=p, form_clave=form_clave, tipos=_tipos_de_aviso(u),
        obligatoria=dos_pasos.obligatoria(u), es_demo=dos_pasos.es_demo(u),
        codigos_restantes=len(p.dos_pasos_codigos or [])))


@staff_member_required
def foto(request, pk):
    p = Perfil.objects.filter(usuario_id=pk).only('foto').first()
    if not p or not p.foto:
        raise Http404
    r = HttpResponse(bytes(p.foto), content_type='image/jpeg')
    r['Cache-Control'] = 'private, max-age=31536000, immutable'  # la URL lleva ?v=versión
    return r


# --------------------------------------------------------------------------- verificación en 2 pasos

class FormCodigo(forms.Form):
    codigo = forms.CharField(
        label='Código de la app', max_length=9,
        help_text='Abre Google o Microsoft Authenticator y escribe el código de «Prospectos UDC». '
                  '¿Perdiste tu teléfono? Escribe uno de tus códigos de recuperación (como ABCD-2345).',
        widget=UnfoldAdminTextInputWidget(attrs={'autocomplete': 'one-time-code', 'autofocus': True, 'placeholder': '123 456',
                                      'inputmode': 'text', 'class': 'tracking-widest'}))


def _ir(request, defecto='admin:index'):
    destino = request.POST.get('next') or request.GET.get('next') or ''
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect(defecto)


def _paso_aprobado(request):
    request.session.cycle_key()
    request.session[SESION_DOS_PASOS] = request.user.pk


def verificar(request):
    """Pantalla del código después de la contraseña (sin menú: todavía no se ha comprobado quién es)."""
    if not request.user.is_authenticated:
        return redirect('admin:login')
    p = Perfil.de(request.user)
    if not p.dos_pasos_activo or request.session.get(SESION_DOS_PASOS) == request.user.pk:
        return _ir(request)
    if request.method == 'POST':
        tipo = dos_pasos.verificar(p, request.POST.get('codigo', ''))
        if tipo:
            _paso_aprobado(request)
            auditoria.registrar('dos_pasos_entrada', request.user, {'con': tipo}, request=request)
            if tipo == 'recuperacion':
                quedan = len(p.dos_pasos_codigos)
                messages.warning(request, f'Entraste con un código de recuperación; te quedan {quedan}. '
                                          'Si perdiste tu teléfono, configura la verificación otra vez en Mi perfil.')
            return _ir(request)
        if fallo_de_codigo(request):
            messages.error(request, 'Demasiados códigos equivocados. Espera 15 minutos antes de volver a entrar.')
            return redirect('admin:login')
        messages.error(request, 'Ese código no es correcto o ya se usó. Revisa que la hora de esta computadora y la del teléfono estén bien.')
    from django.contrib import admin
    return render(request, 'prospectos/verificar.html', admin.site.each_context(request) | {
        'title': 'Verificación en 2 pasos', 'next': request.GET.get('next', ''), 'form': FormCodigo()})


@staff_member_required
def configurar_dos_pasos(request):
    u, p = request.user, Perfil.de(request.user)
    obligatoria = dos_pasos.obligatoria(u)
    ctx = {'perfil': p, 'obligatoria': obligatoria, 'codigos': None}
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'activar' and not p.dos_pasos_activo:
            secreto = request.session.get(SESION_SECRETO)
            codigos = dos_pasos.activar(p, secreto, request.POST.get('codigo', '')) if secreto else None
            if codigos:
                request.session.pop(SESION_SECRETO, None)
                _paso_aprobado(request)
                auditoria.registrar('dos_pasos_activar', u, {}, request=request)
                messages.success(request, 'Listo: la verificación en 2 pasos está activa.')
                ctx['codigos'] = codigos
            else:
                messages.error(request, 'El código no coincide. Escribe el que muestra la app ahora (cambia cada 30 segundos).')
        elif accion in ('regenerar', 'desactivar') and p.dos_pasos_activo:
            codigo_ok = dos_pasos.comprobar(p.dos_pasos_secreto, request.POST.get('codigo', ''), p.dos_pasos_ultimo)
            if accion == 'desactivar' and obligatoria:
                messages.error(request, 'Las cuentas de administrador no pueden quitarla.')
            elif codigo_ok is None or (accion == 'desactivar' and not u.check_password(request.POST.get('clave', ''))):
                if fallo_de_codigo(request):
                    return redirect('admin:login')
                messages.error(request, 'El código o la contraseña no son correctos.')
            else:
                p.dos_pasos_ultimo = codigo_ok
                p.save(update_fields=['dos_pasos_ultimo'])
                if accion == 'regenerar':
                    ctx['codigos'] = dos_pasos.nuevos_codigos_recuperacion(p)
                    auditoria.registrar('dos_pasos_codigos', u, {}, request=request)
                    messages.success(request, 'Nuevos códigos de recuperación. Los anteriores ya no sirven.')
                else:
                    dos_pasos.desactivar(p)
                    auditoria.registrar('dos_pasos_desactivar', u, {}, request=request)
                    messages.warning(request, 'Se quitó la verificación en 2 pasos de tu cuenta.')
                    return redirect('prospectos:perfil')
    if not p.dos_pasos_activo:
        secreto = request.session.get(SESION_SECRETO) or dos_pasos.nuevo_secreto()
        request.session[SESION_SECRETO] = secreto
        ctx.update(secreto=' '.join(secreto[i:i + 4] for i in range(0, len(secreto), 4)),
                   qr=dos_pasos.qr_svg(dos_pasos.uri(secreto, u.get_username())))
    ctx['codigos_restantes'] = len(p.dos_pasos_codigos or [])
    return render(request, 'prospectos/dos_pasos.html', _ctx(request, 'Verificación en 2 pasos', **ctx))
