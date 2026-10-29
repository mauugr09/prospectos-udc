from django import template

register = template.Library()


@register.filter
def abs_es(valor):
    try:
        return abs(valor)
    except TypeError:
        return valor
