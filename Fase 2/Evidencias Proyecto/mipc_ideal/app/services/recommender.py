# services/recommender.py
# services/recommender.py
import re
import unicodedata
from django.db.models import Count, Min, Q, Case, When, IntegerField
from app.models import Producto, PreferenciaUsuario, CategoriaProducto, TipoProducto

def _norm(s: str) -> str:
    """Minúsculas y sin tildes/diacríticos para comparar de forma estable."""
    s = s or ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def _extract_budget_clp(text: str):
    t = _norm(text).replace(".", "").replace("$", " ").strip()
    m_k = re.search(r'\b(\d+)\s*k\b', t)
    if m_k:
        return int(m_k.group(1)) * 1000
    m = re.search(r'\b(\d{5,7})\b', t)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None

def _match_by_names(text: str, qs, field_name: str):
    """
    Devuelve IDs cuyo nombre aparece en el texto como palabra completa (no subcadenas),
    con normalización (sin acentos) para robustez.
    """
    text_n = _norm(text)
    found_ids = []
    for obj in qs:
        name = getattr(obj, field_name, "") or ""
        name_n = re.escape(_norm(name))
        if not name_n:
            continue
        # palabra completa: límites \b; ejemplo: 'gamer' no debe activar 'programer'
        if re.search(rf'\b{name_n}\b', text_n):
            found_ids.append(obj.id)
    return found_ids

def parse_requirements(user, text: str):
    budget = _extract_budget_clp(text)
    cats_all = list(CategoriaProducto.objects.all())
    types_all = list(TipoProducto.objects.all())

    cats_from_text = _match_by_names(text, cats_all, "nombre_categoria")
    types_from_text = _match_by_names(text, types_all, "nombre_tipo")

    pref_cat_ids, pref_type_ids = [], []
    if user and user.is_authenticated:
        pref_cat_ids = list(
            PreferenciaUsuario.objects.filter(usuario=user, categoria__isnull=False)
            .values_list("categoria_id", flat=True)
        )
        pref_type_ids = list(
            PreferenciaUsuario.objects.filter(usuario=user, tipo_producto__isnull=False)
            .values_list("tipo_producto_id", flat=True)
        )

    return {
        "budget": budget,
        "cat_text": cats_from_text,
        "type_text": types_from_text,
        "pref_cats": pref_cat_ids,
        "pref_types": pref_type_ids,
    }

def recommend_products(user, text: str, limit=8, sticky_cats=None, sticky_types=None, sticky_budget=None):
    """
    Prioridad de filtros: TEXTO > STICKY > PREFERENCIAS.
    """
    req = parse_requirements(user, text)
    qs = Producto.objects.all()

    cat_ids = req["cat_text"] or (sticky_cats or []) or req["pref_cats"]
    type_ids = req["type_text"] or (sticky_types or []) or req["pref_types"]

    if cat_ids:
        qs = qs.filter(categoria_producto_id__in=cat_ids)
    if type_ids:
        qs = qs.filter(tipo_producto_id__in=type_ids)

    qs = qs.annotate(
        views_count=Count("productovisto"),
        min_price=Min("referencias__precio"),
    )

    budget = req["budget"] if req["budget"] is not None else sticky_budget
    if budget:
        qs = qs.annotate(
            over_budget=Case(
                When(min_price__gt=budget, then=1),
                default=0,
                output_field=IntegerField()
            )
        ).order_by("over_budget", "min_price", "-views_count", "-fecha_creacion")
    else:
        qs = qs.order_by("-views_count", "min_price", "-fecha_creacion")

    qs = qs[:limit]
    filtros_aplicados = {
        "categorias": cat_ids or [],
        "tipos": type_ids or [],
        "budget": budget,
    }
    return qs, filtros_aplicados
