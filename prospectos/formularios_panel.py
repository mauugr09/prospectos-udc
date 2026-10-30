"""Formularios del panel pensados para personas, no para programadores (listas en renglones, casillas, roles)."""

import secrets

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from unfold.widgets import (UnfoldAdminCheckboxSelectMultipleWidget, UnfoldAdminEmailInputWidget, UnfoldAdminSelectWidget,
                            UnfoldAdminTextareaWidget, UnfoldAdminTextInputWidget)

from . import catalogos
from .models import Carrera, Perfil, Preparatoria, Pregunta, TipoPregunta


class LineasField(forms.CharField):
    """Lista de textos que la persona escribe uno por renglón (en la base se guarda como lista)."""

    widget = UnfoldAdminTextareaWidget(attrs={'rows': 3})

    def prepare_value(self, value):
        return '\n'.join(value) if isinstance(value, list) else value

    def to_python(self, value):
        if isinstance(value, list):
            return value
        vistos, res = set(), []
        for linea in (value or '').splitlines():
            t = linea.strip()
            if t and t.lower() not in vistos:
                vistos.add(t.lower())
                res.append(t)
        return res

    def validate(self, value):
        if self.required and not value:
            raise ValidationError(self.error_messages['required'], code='required')


class CarreraForm(forms.ModelForm):
    planteles = forms.MultipleChoiceField(choices=list(catalogos.PLANTELES_CORTO.items()), required=False,
                                          widget=UnfoldAdminCheckboxSelectMultipleWidget,
                                          help_text='Dónde se ofrece. Se usa en los reportes por plantel.')
    alias = LineasField(label='Otras formas de escribirla', required=False,
                        help_text='Cómo aparece en el Form si no es igual al nombre, una por renglón '
                                  '(p. ej. «Ingeniera Industrial»).')

    class Meta:
        model = Carrera
        fields = ['nombre', 'area', 'planteles', 'alias', 'activo']


class PreparatoriaForm(forms.ModelForm):
    alias = LineasField(label='Otras formas de escribirla', required=False,
                        help_text='Cómo la escriben los alumnos, una por renglón. Se llena sola al unir preparatorias.')

    class Meta:
        model = Preparatoria
        fields = '__all__'


class PreguntaForm(forms.ModelForm):
    tipo = forms.ChoiceField(choices=TipoPregunta.choices, widget=UnfoldAdminSelectWidget,
                             help_text='Igual que en el Google Form.')

    class Meta:
        model = Pregunta
        fields = ['cuestionario', 'texto', 'etiqueta', 'tema', 'tipo', 'orden', 'codigo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        p = self.instance
        if p.pk and p.de_sistema:
            # Las reglas dependen de estas: se cambia cómo se ven, no qué son.
            self.fields['tipo'] = forms.CharField(disabled=True, required=False, widget=UnfoldAdminTextInputWidget,
                                                  help_text='Pregunta del sistema: su tipo no se cambia.')
            self.initial['tipo'] = dict(TipoPregunta.choices).get(p.tipo, p.tipo)
        if p.pk:
            for f in ('cuestionario', 'codigo'):
                self.fields[f].disabled = True

    def clean_tipo(self):
        if self.instance.pk and self.instance.de_sistema:
            return self.instance.tipo
        return self.cleaned_data['tipo']

    def clean_codigo(self):
        if self.instance.pk:
            return self.instance.codigo
        from .servicios import texto
        c = texto.normalizar(self.cleaned_data.get('codigo') or '').replace(' ', '_')
        return c


class OpcionesFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        claves = set()
        for f in self.forms:
            if not hasattr(f, 'cleaned_data') or not f.cleaned_data:
                continue
            o = f.instance
            if f.cleaned_data.get('DELETE') and o.pk and o.fija:
                raise ValidationError(f'La opción «{o.texto}» la usan las reglas de prioridad: puedes cambiarle el texto, '
                                      'pero no borrarla.')
            if f.cleaned_data.get('DELETE'):
                continue
            from .servicios import texto
            t = texto.normalizar(f.cleaned_data.get('texto'))
            if t in claves:
                raise ValidationError(f'La opción «{f.cleaned_data.get("texto")}» está repetida.')
            claves.add(t)


class NuevoUsuarioForm(forms.ModelForm):
    """Alta en un solo paso: correo, nombre, rol y contraseña temporal (se cambia al primer ingreso)."""

    email = forms.EmailField(label='Correo', widget=UnfoldAdminEmailInputWidget,
                             help_text='Con este correo entra al programa.')
    rol = forms.ModelChoiceField(queryset=Group.objects.order_by('name'), widget=UnfoldAdminSelectWidget,
                                 help_text='Qué puede ver y hacer. Se puede cambiar después.')
    codigo_promotor = forms.CharField(label='Código de promotor', required=False, max_length=20,
                                      widget=UnfoldAdminTextInputWidget,
                                      help_text='Solo para promotores (p. ej. P04). Viaja en el QR de sus eventos.')
    clave = forms.CharField(label='Contraseña temporal', required=False, min_length=12, widget=UnfoldAdminTextInputWidget,
                            help_text='Déjala vacía para generar una. La persona la cambia al entrar por primera vez.')
    password1 = password2 = None  # el admin de Django los busca en add_form; aquí no se usan

    class Meta:
        model = get_user_model()
        fields = ['email', 'first_name', 'last_name']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['first_name'].label, self.fields['last_name'].label = 'Nombre', 'Apellidos'
        for f in ('first_name', 'last_name'):
            self.fields[f].widget = UnfoldAdminTextInputWidget()

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if get_user_model().objects.filter(username__iexact=email).exists():
            raise ValidationError('Ya existe un usuario con ese correo.')
        return email

    def clean_codigo_promotor(self):
        c = (self.cleaned_data.get('codigo_promotor') or '').strip().upper() or None
        if c and Perfil.objects.filter(codigo_promotor=c).exists():
            raise ValidationError('Ese código ya lo tiene otro promotor.')
        return c

    def save(self, commit=True):
        u = super().save(commit=False)
        u.username = u.email
        u.is_staff, u.is_active = True, True
        self.clave_generada = self.cleaned_data.get('clave') or ''.join(
            secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789') for _ in range(14))
        u.set_password(self.clave_generada)
        self._usuario = u
        self.save_m2m = self._rol_y_perfil  # ModelForm.save(commit=False) pone su propio save_m2m
        if commit:
            u.save()
            self.save_m2m()
        return u

    def _rol_y_perfil(self):
        """El admin lo llama después de guardar el usuario: rol y perfil."""
        u = self._usuario
        u.groups.set([self.cleaned_data['rol']])
        Perfil.objects.update_or_create(usuario=u, defaults={'codigo_promotor': self.cleaned_data.get('codigo_promotor'),
                                                             'debe_cambiar_clave': True})
