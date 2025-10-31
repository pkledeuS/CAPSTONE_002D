from django import template
register = template.Library()

@register.filter(name="get_item")
def get_item(d, key=None):
    """
    Uso: {{ dic|get_item:"clave" }}
    Devuelve d[clave] o None de forma segura.
    Funciona con dict y, si 'd' es lista/tupla y 'key' es int, indexa.
    """
    try:
        if key is None:
            return None
        if hasattr(d, 'get'):
            return d.get(key)
        if isinstance(key, int) and isinstance(d, (list, tuple)):
            return d[key] if 0 <= key < len(d) else None
        return None
    except Exception:
        return None