from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """
    Divide una cadena por el separador dado.
    Uso: {{ value|split:"," }}
    """
    return value.split(arg)