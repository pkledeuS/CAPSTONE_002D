import random
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Tuple
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, DecimalField, F, IntegerField, Max, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .models import (
    CategoriaProducto,
    EspecificacionProducto,
    Producto,
    ProductoVisto,
    ProductReference,
    ProductReview,
    PreferenciaUsuario,
    ProductosFavoritos,
    TipoProducto,
    Profile,
    UserViewStat,
)
from .forms import ProductReviewForm
from .views import SPEC_CANON, SPEC_TEMPLATES, _norm_key

# ===========================
# Utilidades / helpers
# ===========================

def _short_text(text: str, max_len: int = 72) -> str:
    if not text:
        return "Explora decisiones y trade-offs antes de elegir."
    text = " ".join(text.strip().split())
    if len(text) <= max_len:
        return text
    trimmed = text[:max_len].rsplit(" ", 1)[0]
    return f"{trimmed}..."


def _format_currency(value: Decimal | None) -> str | None:
    if value is None:
        return None
    try:
        integer = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return "${:,}".format(integer).replace(",", ".")


def _build_spec_map(product: Producto) -> Dict[str, str]:
    specs = getattr(product, "prefetched_specs", None)
    if specs is None:
        specs = EspecificacionProducto.objects.filter(producto=product)
    mapped: Dict[str, str] = {}
    for spec in specs:
        canonical = SPEC_CANON.get(_norm_key(spec.nombre_especificacion), spec.nombre_especificacion)
        mapped[canonical] = spec.valor_especificacion
    return mapped


def _categories_with_inventory():
    return (
        CategoriaProducto.objects.annotate(
            prod_count=Count(
                "producto",
                filter=Q(producto__is_active=True),
                distinct=True,
            )
            + Count(
                "productos_extra",
                filter=Q(productos_extra__is_active=True),
                distinct=True,
            )
        )
        .filter(prod_count__gt=0)
    )


def _favorite_ids_for(user) -> set[int]:
    if not user.is_authenticated:
        return set()
    return set(
        ProductosFavoritos.objects.filter(usuario=user).values_list("producto_id", flat=True)
    )


PRICE_BANDS = [
    {"lower": 0, "upper": 400000, "label": "0-400k", "query": "0-400000"},
    {"lower": 400000, "upper": 800000, "label": "400k-800k", "query": "400000-800000"},
    {"lower": 800000, "upper": 1200000, "label": "800k-1.2M", "query": "800000-1200000"},
    {"lower": 1200000, "upper": None, "label": "1.2M+", "query": "1200000-0"},
]

PREFERENCE_WEIGHTS = {
    "category": 45,
    "type": 35,
    "budget": 20,
}


def _price_band_key(value: Decimal | None) -> str | None:
    if value is None:
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    for band in PRICE_BANDS:
        lower = band["lower"]
        upper = band["upper"]
        meets_lower = (lower is None) or (amount >= lower)
        meets_upper = (upper is None) or (amount < upper)
        if meets_lower and meets_upper:
            return band["label"]
    return PRICE_BANDS[-1]["label"]


def _budget_query_value(label: str | None) -> str | None:
    for band in PRICE_BANDS:
        if band["label"] == (label or ""):
            return band["query"]
    return ""


def _price_band_limits(label: str | None) -> Tuple[int | None, int | None]:
    if not label:
        return (None, None)
    for band in PRICE_BANDS:
        if band["label"] == label:
            return band["lower"], band["upper"]
    return (None, None)


def _budget_limits_from_value(value: str | None) -> Tuple[int | None, int | None]:
    if not value:
        return (None, None)
    for band in PRICE_BANDS:
        if band["query"] == value:
            return band["lower"], band["upper"]
    parts = value.split("-")
    if len(parts) == 2:
        try:
            low = int(parts[0]) if parts[0] else None
            high = int(parts[1]) if parts[1] else None
            if high == 0:
                high = None
            return low, high
        except ValueError:
            pass
    return (None, None)


def _budget_value_from_limits(min_value: int | None, max_value: int | None) -> str | None:
    for band in PRICE_BANDS:
        low_match = (band["lower"] or 0) == (min_value or 0)
        upper_match = (band["upper"] or 0) == (max_value or 0)
        if low_match and upper_match:
            return band["query"]
    return None


def _format_budget_label(min_value: int | None, max_value: int | None) -> str | None:
    if not min_value and not max_value:
        return None
    if min_value and max_value:
        return f"{_format_currency(Decimal(str(min_value)))} - {_format_currency(Decimal(str(max_value)))}"
    if min_value:
        return f"Desde {_format_currency(Decimal(str(min_value)))}"
    if max_value:
        return f"Hasta {_format_currency(Decimal(str(max_value)))}"
    return None


def _increment_user_view_stat(user, metric: str, key: str | None) -> None:
    if not user.is_authenticated or not key:
        return
    obj, created = UserViewStat.objects.get_or_create(
        usuario=user,
        metric=metric,
        key=key,
        defaults={"count": 1},
    )
    if not created:
        UserViewStat.objects.filter(pk=obj.pk).update(count=F("count") + 1)


def _register_user_view(user, product: Producto, min_price: Decimal | None = None) -> None:
    if not user.is_authenticated:
        return
    ProductoVisto.objects.create(usuario=user, producto=product)

    if product.marca_producto_id and product.marca_producto and product.marca_producto.nombre_marca:
        _increment_user_view_stat(
            user,
            UserViewStat.METRIC_BRAND,
            product.marca_producto.nombre_marca,
        )

    if product.categoria_producto_id and product.categoria_producto:
        _increment_user_view_stat(
            user,
            UserViewStat.METRIC_CATEGORY,
            f"{product.categoria_producto_id}:{product.categoria_producto.nombre_categoria}",
        )

    if product.tipo_producto_id and product.tipo_producto:
        _increment_user_view_stat(
            user,
            UserViewStat.METRIC_TYPE,
            f"{product.tipo_producto_id}:{product.tipo_producto.nombre_tipo}",
        )

    price_value = min_price
    if price_value is None:
        price_value = getattr(product, "min_price", None)
    price_band = _price_band_key(price_value)
    if price_band:
        _increment_user_view_stat(
            user,
            UserViewStat.METRIC_PRICE,
            price_band,
        )


def _top_view_stats(user, metric: str, limit: int = 3) -> List[Dict[str, object]]:
    if not user.is_authenticated:
        return []
    stats = (
        UserViewStat.objects.filter(usuario=user, metric=metric)
        .order_by("-count", "-last_seen")
    )
    payload: List[Dict[str, object]] = []
    for stat in stats:
        label = stat.key
        ref_id = None
        if metric in (UserViewStat.METRIC_CATEGORY, UserViewStat.METRIC_TYPE):
            if ":" in stat.key:
                ref_id_str, ref_label = stat.key.split(":", 1)
                label = ref_label
                try:
                    ref_id = int(ref_id_str)
                except ValueError:
                    ref_id = None
        payload.append(
            {
                "label": label,
                "count": stat.count,
                "ref_id": ref_id,
            }
        )
    return payload


def _collect_user_radar_data(user, days: int = 14) -> Dict[str, object]:
    data = {
        "timeline": [],
        "total_views": 0,
        "window_days": days,
    }
    if not user.is_authenticated:
        return data
    since = timezone.now() - timedelta(days=days)
    view_qs = (
        ProductoVisto.objects.filter(usuario=user, fecha_visto__gte=since)
        .annotate(day=TruncDate("fecha_visto"))
        .values("day")
        .order_by("day")
        .annotate(total=Count("id"))
    )
    timeline: List[Dict[str, object]] = []
    total = 0
    for entry in view_qs:
        day = entry["day"]
        label = day.strftime("%d %b") if hasattr(day, "strftime") else str(day)
        timeline.append({"label": label, "value": entry["total"]})
        total += entry["total"]
    data["timeline"] = timeline
    data["total_views"] = total
    return data


def _build_affinity_suggestions(user, pref_ctx: Dict[str, object], limit: int = 4) -> Tuple[List[Dict[str, object]], Dict[str, str]]:
    suggestions: List[Dict[str, object]] = []
    seen_ids: set[int] = set()
    base_qs = _base_product_queryset().order_by("-view_count", "-avg_rating")
    if user.is_authenticated:
        base_qs = base_qs.exclude(productovisto__usuario=user)

    view_stats = pref_ctx.get("view_stats", {})
    brand_stats = view_stats.get("brands") or []
    price_label = pref_ctx.get("budget_label")
    min_limit, max_limit = _price_band_limits(price_label)

    def _append_from_brand(brand_name: str):
        nonlocal suggestions
        qs = base_qs.filter(marca_producto__nombre_marca__iexact=brand_name)
        if min_limit:
            qs = qs.filter(min_price__gte=min_limit)
        if max_limit:
            qs = qs.filter(min_price__lt=max_limit)
        for prod in qs[:limit]:
            if prod.id in seen_ids:
                continue
            payload = _product_payload(prod)
            _apply_preference_match(payload, pref_ctx)
            payload.pop("_spec_map", None)
            label = brand_name
            if price_label:
                label = f"{brand_name} · {price_label}"
            payload["insight_label"] = label
            suggestions.append(payload)
            seen_ids.add(prod.id)
            if len(suggestions) >= limit:
                break

    fallback_focus = None
    top_brand = brand_stats[0]["label"] if brand_stats else None
    if top_brand:
        _append_from_brand(top_brand)
        fallback_focus = _brand_focus_payload(user, top_brand, pref_ctx, limit=limit)

    if len(suggestions) < limit and not brand_stats:
        qs = base_qs
        if min_limit:
            qs = qs.filter(min_price__gte=min_limit)
        if max_limit:
            qs = qs.filter(min_price__lt=max_limit)
        label = price_label or "Mas vistos"
        for prod in qs[:limit]:
            if prod.id in seen_ids:
                continue
            payload = _product_payload(prod)
            _apply_preference_match(payload, pref_ctx)
            payload.pop("_spec_map", None)
            payload["insight_label"] = label
            suggestions.append(payload)
            seen_ids.add(prod.id)
            if len(suggestions) >= limit:
                break

    if len(suggestions) < limit and fallback_focus:
        brand_name = top_brand or brand_stats[0]["label"]
        for entry in fallback_focus.get("less_viewed", []):
            if entry["id"] in seen_ids:
                continue
            payload = entry.copy()
            payload["insight_label"] = f"{brand_name} · pocas vistas"
            suggestions.append(payload)
            seen_ids.add(entry["id"])
            if len(suggestions) >= limit:
                break

    suggestions = suggestions[:limit]
    explore_params = {}
    if brand_stats:
        explore_params["marca"] = brand_stats[0]["label"]
    budget_query = _budget_query_value(pref_ctx.get("budget_label"))
    if budget_query:
        explore_params["presupuesto"] = budget_query
    return suggestions, explore_params


def _user_preference_context(user) -> Dict[str, object]:
    context = {
        "categories": [],
        "category_ids": set(),
        "types": [],
        "type_ids": set(),
        "budget_min": None,
        "budget_max": None,
        "budget_label": None,
        "notes": "",
        "has_prefs": False,
    }
    if not user.is_authenticated:
        return context

    pref_entries = PreferenciaUsuario.objects.filter(usuario=user)
    category_ids = {pref.categoria_id for pref in pref_entries if pref.categoria_id}
    type_ids = {pref.tipo_producto_id for pref in pref_entries if pref.tipo_producto_id}

    manual_categories = []
    manual_category_ids = set(category_ids)
    if manual_category_ids:
        manual_categories = list(
            CategoriaProducto.objects.filter(id__in=manual_category_ids)
            .values("id", "nombre_categoria")
            .order_by("nombre_categoria")
        )
    context["categories"] = manual_categories
    context["category_ids"] = set(manual_category_ids)
    context["categories_manual"] = manual_categories
    context["category_ids_manual"] = manual_category_ids

    manual_types = []
    manual_type_ids = set(type_ids)
    if manual_type_ids:
        manual_types = list(
            TipoProducto.objects.filter(id__in=manual_type_ids)
            .values("id", "nombre_tipo")
            .order_by("nombre_tipo")
        )
    context["types"] = manual_types
    context["type_ids"] = set(manual_type_ids)
    context["types_manual"] = manual_types
    context["type_ids_manual"] = manual_type_ids

    profile = Profile.objects.filter(user=user).first()
    if profile:
        context["budget_min"] = profile.preferred_budget_min
        context["budget_max"] = profile.preferred_budget_max if profile.preferred_budget_max else None
        context["budget_label"] = _format_budget_label(profile.preferred_budget_min, profile.preferred_budget_max)
        context["notes"] = profile.preference_notes or ""
        context["budget_value"] = _budget_value_from_limits(
            profile.preferred_budget_min, profile.preferred_budget_max
        )
        context["budget_manual"] = bool(profile.preferred_budget_manual and context["budget_value"])
    else:
        context["budget_manual"] = False
        context["budget_value"] = None

    context["manual_pref_active"] = bool(
        manual_category_ids or manual_type_ids or context["budget_manual"]
    )

    brand_stats = _top_view_stats(user, UserViewStat.METRIC_BRAND, limit=4)
    category_stats = _top_view_stats(user, UserViewStat.METRIC_CATEGORY, limit=4)
    type_stats = _top_view_stats(user, UserViewStat.METRIC_TYPE, limit=4)
    price_stats = _top_view_stats(user, UserViewStat.METRIC_PRICE, limit=2)

    if not context["categories"] and category_stats:
        context["categories"] = [
            {"id": stat["ref_id"], "nombre_categoria": stat["label"]}
            for stat in category_stats
            if stat["ref_id"]
        ]
        context["category_ids"] = {stat["ref_id"] for stat in category_stats if stat["ref_id"]}
    if not context["types"] and type_stats:
        context["types"] = [
            {"id": stat["ref_id"], "nombre_tipo": stat["label"]}
            for stat in type_stats
            if stat["ref_id"]
        ]
        context["type_ids"] = {stat["ref_id"] for stat in type_stats if stat["ref_id"]}
    if not context["budget_label"] and price_stats and not context["budget_manual"]:
        top_label = price_stats[0]["label"]
        context["budget_label"] = top_label
        min_limit, max_limit = _price_band_limits(top_label)
        context["budget_min"] = min_limit
        context["budget_max"] = max_limit
        context["budget_value"] = context.get("budget_value") or _budget_value_from_limits(min_limit, max_limit)

    context["preferred_brands"] = [stat["label"] for stat in brand_stats]
    context["view_stats"] = {
        "brands": brand_stats,
        "categories": category_stats,
        "types": type_stats,
        "prices": price_stats,
    }

    context["has_prefs"] = bool(
        context["categories"]
        or context["types"]
        or context["budget_label"]
        or context["notes"]
        or context["preferred_brands"]
    )
    return context



def _apply_preference_match(payload: Dict[str, object], pref_ctx: Dict[str, object]) -> None:
    payload.setdefault("match_summary_list", [])
    payload["_affinity_flags"] = {}
    manual_enabled = bool(pref_ctx and pref_ctx.get("manual_pref_active"))
    if not manual_enabled:
        payload["match_summary"] = None
        payload["match_caption"] = None
        payload["sort_match"] = -payload.get("match", 0)
        payload["show_match"] = False
        payload["personal_match"] = None
        return

    payload["show_match"] = True
    factors: List[str] = []
    category_label = None
    type_label = None

    manual_categories = pref_ctx.get("category_ids_manual") or set()
    manual_category_meta = pref_ctx.get("categories_manual") or []
    product_categories = set(payload.get("category_all_ids") or [])
    category_matched = None
    if manual_categories:
        category_matched = bool(product_categories & manual_categories)
        if category_matched:
            category_label = next(
                (
                    cat["nombre_categoria"]
                    for cat in manual_category_meta
                    if cat["id"] in product_categories
                ),
                None,
            )
            if category_label:
                factors.append(f"Categoria guardada: {category_label}")
        else:
            factors.append("Fuera de tus categorias guardadas")

    manual_types = pref_ctx.get("type_ids_manual") or set()
    manual_type_meta = pref_ctx.get("types_manual") or []
    type_matched = None
    if manual_types:
        type_matched = payload.get("type_id") in manual_types
        if type_matched:
            type_label = next(
                (
                    tipo["nombre_tipo"]
                    for tipo in manual_type_meta
                    if tipo["id"] == payload.get("type_id")
                ),
                None,
            )
            if type_label:
                factors.append(f"Formato que sigues: {type_label}")
        else:
            factors.append("Formato fuera de tus preferencias")

    budget_manual = pref_ctx.get("budget_manual")
    min_budget = pref_ctx.get("budget_min") if budget_manual else None
    max_budget = pref_ctx.get("budget_max") if budget_manual else None
    price_value = payload.get("min_price_value")
    budget_checked = budget_manual and (min_budget is not None or max_budget is not None)
    budget_matched = None
    if budget_checked and price_value is not None:
        within = True
        if min_budget is not None and price_value < min_budget:
            within = False
        if max_budget is not None and price_value > max_budget:
            within = False
        budget_matched = within
        if within:
            factors.append("Dentro de tu rango de inversion")
        else:
            factors.append("Fuera de tu rango de inversion")
    elif budget_checked:
        factors.append("Sin precio para comparar con tu presupuesto")

    avg_rating = payload.get("avg_rating")
    review_count = payload.get("review_count", 0)
    if avg_rating and review_count:
        factors.append(f"Valorado {avg_rating:.1f}/5 ({review_count} resenas)")

    caption_parts: List[str] = []
    if category_label:
        caption_parts.append(category_label)
    if type_label:
        caption_parts.append(type_label)
    if budget_matched:
        caption_parts.append("Presupuesto guardado")

    affinity_total = 0
    affinity_score = 0
    flags = {"category": None, "type": None, "budget": None}
    if manual_categories:
        affinity_total += PREFERENCE_WEIGHTS["category"]
        if category_matched:
            affinity_score += PREFERENCE_WEIGHTS["category"]
            flags["category"] = True
        else:
            flags["category"] = False
    if manual_types:
        affinity_total += PREFERENCE_WEIGHTS["type"]
        if type_matched:
            affinity_score += PREFERENCE_WEIGHTS["type"]
            flags["type"] = True
        else:
            flags["type"] = False
    if budget_checked and price_value is not None:
        affinity_total += PREFERENCE_WEIGHTS["budget"]
        if budget_matched:
            affinity_score += PREFERENCE_WEIGHTS["budget"]
            flags["budget"] = True
        else:
            flags["budget"] = False

    payload["_affinity_flags"] = flags
    if affinity_total == 0:
        payload["match_summary"] = "; ".join(factors)
        payload["match_summary_list"] = [item.strip() for item in factors if item.strip()]
        payload["match_caption"] = None
        payload["sort_match"] = -payload.get("match", 0)
        payload["personal_match"] = None
        payload["show_match"] = False
        return

    personal_match = int(round((affinity_score / affinity_total) * 100))
    payload["personal_match"] = max(0, min(100, personal_match))
    payload["match"] = payload["personal_match"]
    payload["match_summary"] = "; ".join(factors)
    payload["match_summary_list"] = [item.strip() for item in factors if item.strip()]
    payload["match_caption"] = " - ".join(caption_parts) if caption_parts else None
    payload["sort_match"] = -payload["match"]

def _preference_weight(card: Dict[str, object], pref_ctx: Dict[str, object]) -> float:
    flags = card.get("_affinity_flags")
    if not flags:
        return 0.0
    weight = 0.0
    for key, matched in flags.items():
        if matched is None:
            continue
        delta = PREFERENCE_WEIGHTS.get(key, 0)
        if matched:
            weight += delta
        else:
            weight -= delta * 0.3
    return weight

def _prioritize_cards(cards: List[Dict[str, object]], pref_ctx: Dict[str, object]) -> List[Dict[str, object]]:
    if not pref_ctx or not pref_ctx.get("has_prefs"):
        return cards
    weighted: List[Tuple[float, Dict[str, object]]] = []
    for card in cards:
        score = card.get("match", 0) + _preference_weight(card, pref_ctx)
        weighted.append((score, card))
    weighted.sort(key=lambda item: (-item[0], item[1].get("sort_value")))
    return [card for _, card in weighted]

def _norm(text: str) -> str:
    text = (text or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _spec_lookup(spec_map: Dict[str, str], *candidates: str) -> str | None:
    if not spec_map:
        return None
    norm_map = { _norm(name): value for name, value in spec_map.items() }
    for candidate in candidates:
        value = norm_map.get(_norm(candidate))
        if value:
            return value
    return None


def _spec_value(spec_map: Dict[str, str], key):
    if isinstance(key, (list, tuple)):
        for candidate in key:
            value = _spec_lookup(spec_map, candidate)
            if value:
                return value
        return None
    return _spec_lookup(spec_map, key)


def _spec_contains(spec_map: Dict[str, str], term: str) -> str | None:
    goal = _norm(term)
    for name, value in spec_map.items():
        if goal in _norm(name):
            return value
    return None


def _parse_first_float(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:[\.,]\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _extract_weight(spec_map: Dict[str, str], description: str) -> float | None:
    weight_text = _spec_contains(spec_map, "peso")
    weight = _parse_first_float(weight_text) if weight_text else None
    if weight:
        return weight
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s?kg", (description or "").lower())
    if match:
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def _extract_tdp(spec_map: Dict[str, str], description: str) -> float | None:
    tdp_text = _spec_contains(spec_map, "tdp")
    tdp = _parse_first_float(tdp_text) if tdp_text else None
    if tdp:
        return tdp
    match = re.search(r"tdp\s*(\d+)", (description or "").lower())
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _convert_capacity_unit(value: float | None, unit: str) -> float | None:
    if value is None:
        return None
    unit = unit.lower()
    if unit == "tb":
        return value * 1024
    if unit == "mb":
        return value / 1024
    return value


def _parse_capacity_gb(text: str | None) -> float | None:
    if not text:
        return None
    sample = text.lower()
    unit_hint = "gb"
    if "tb" in sample:
        unit_hint = "tb"
    elif "mb" in sample:
        unit_hint = "mb"
    multi = re.search(r"(\d+(?:[\.,]\d+)?)\s*x\s*(\d+(?:[\.,]\d+)?)", sample)
    if multi:
        qty = _safe_float(multi.group(1))
        size = _safe_float(multi.group(2))
        if qty is not None and size is not None:
            return _convert_capacity_unit(qty * size, unit_hint)
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(tb|gb|mb)", sample)
    if match:
        value = _safe_float(match.group(1))
        return _convert_capacity_unit(value, match.group(2))
    return None


def _parse_weight_grams(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(kg|g)", text.lower())
    if not match:
        return None
    value = _safe_float(match.group(1))
    if value is None:
        return None
    unit = match.group(2)
    if unit == "kg":
        return value * 1000
    return value


def _parse_battery_wh(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(wh|mwh)", text.lower())
    if not match:
        return None
    value = _safe_float(match.group(1))
    if value is None:
        return None
    if match.group(2) == "mwh":
        return value / 1000
    return value


def _parse_watts(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*w", text.lower())
    if not match:
        return None
    return _safe_float(match.group(1))


def _parse_threads(text: str | None) -> float | None:
    if not text:
        return None
    sample = text.lower()
    match = re.search(r"(\d+)\s*(?:hilos|threads)", sample)
    if match:
        return _safe_float(match.group(1))
    match = re.search(r"/\s*(\d+)", sample)
    if match:
        return _safe_float(match.group(1))
    return None


def _parse_resolution_width(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d+)\s*[x×]\s*(\d+)", text.lower())
    if not match:
        return None
    try:
        first = int(match.group(1))
        second = int(match.group(2))
    except ValueError:
        return None
    return max(first, second)


def _parse_gpu_bus_version(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"pci(?:e| express)?\s*(\d+(?:\.\d+)?)", text.lower())
    if not match:
        return None
    return _safe_float(match.group(1))


def _spec_value_contains(spec_map: Dict[str, str], term: str) -> bool:
    needle = _norm(term)
    if not needle:
        return False
    for value in spec_map.values():
        if needle in _norm(value):
            return True
    return False


def _required_bus_version(token: str) -> float | None:
    match = re.search(r"(\d+(?:[\.,]\d+)?)", token.lower())
    if not match:
        return None
    return _safe_float(match.group(1))


SPEC_FILTER_QUERY_KEYS = {
    "ram_min",
    "storage_min",
    "storage",
    "gpu_bus",
    "socket_hint",
    "psu_w_min",
    "battery_wh_min",
    "weight_max",
    "display_resolution",
    "gpu_mem_min",
    "port_hint",
    "threads_min",
}

SPEC_FILTER_ORDER = [
    "ram_min",
    "storage_min",
    "storage",
    "gpu_mem_min",
    "gpu_bus",
    "socket_hint",
    "psu_w_min",
    "battery_wh_min",
    "weight_max",
    "display_resolution",
    "port_hint",
    "threads_min",
]

NUMERIC_SPEC_FILTERS = (
    "ram_min",
    "storage_min",
    "gpu_mem_min",
    "battery_wh_min",
    "weight_max",
    "psu_w_min",
    "threads_min",
)

STRING_SPEC_FILTERS = ("storage", "gpu_bus", "socket_hint", "port_hint", "display_resolution")

STORAGE_SPEC_KEYS = ["Almacenamiento", "Memoria interna", "Almacenamiento interno", "Almacenamiento total"]
BATTERY_SPEC_KEYS = ["Batería", "Bateria"]
WEIGHT_SPEC_KEYS = ["Peso"]
DISPLAY_SPEC_KEYS = ["Pantalla", "Display"]


def _extract_spec_filters(params) -> Dict[str, object]:
    filters: Dict[str, object] = {}
    for key in NUMERIC_SPEC_FILTERS:
        raw_value = params.get(key)
        if not raw_value:
            continue
        try:
            filters[key] = int(float(raw_value))
        except (TypeError, ValueError):
            continue
    for key in STRING_SPEC_FILTERS:
        raw_value = params.get(key)
        if not raw_value:
            continue
        if key == "socket_hint":
            filters[key] = raw_value.upper()
        else:
            filters[key] = raw_value.lower()
    return filters


def _format_spec_filter_badges(raw_params: Dict[str, str]) -> List[str]:
    badges: List[str] = []
    for key in SPEC_FILTER_ORDER:
        value = raw_params.get(key)
        if not value:
            continue
        if key == "ram_min":
            badges.append(f"RAM ≥ {value} GB")
        elif key == "storage_min":
            badges.append(f"Almacenamiento ≥ {value} GB")
        elif key == "storage":
            val = value.lower()
            if val == "nvme":
                badges.append("Solo NVMe")
            elif val == "ssd":
                badges.append("Solo SSD/NVMe")
            else:
                badges.append(f"Almacenamiento {value}")
        elif key == "gpu_mem_min":
            badges.append(f"VRAM ≥ {value} GB")
        elif key == "gpu_bus":
            bus_version = _required_bus_version(value) or value
            if isinstance(bus_version, float):
                badges.append(f"PCIe {bus_version:g}")
            else:
                badges.append(f"Bus {value.upper()}")
        elif key == "socket_hint":
            badges.append(f"Socket {value.upper()}")
        elif key == "psu_w_min":
            badges.append(f"Fuente ≥ {value} W")
        elif key == "battery_wh_min":
            badges.append(f"Batería ≥ {value} Wh")
        elif key == "weight_max":
            try:
                grams = float(value)
            except ValueError:
                badges.append(f"Peso ≤ {value}")
            else:
                if grams >= 1000:
                    kg = grams / 1000
                    badges.append(f"Peso ≤ {kg:.1f} kg")
                else:
                    badges.append(f"Peso ≤ {int(grams)} g")
        elif key == "display_resolution":
            label_map = {
                "fhd": "Resolución FHD+",
                "2k": "Resolución 2K+",
                "qhd": "Resolución QHD",
                "4k": "Resolución 4K",
                "uhd": "Resolución UHD",
            }
            badges.append(label_map.get(value.lower(), f"Resolución {value.upper()}"))
        elif key == "port_hint":
            badges.append(f"Conector {value.upper()}")
        elif key == "threads_min":
            badges.append(f"{value}+ hilos")
    return badges


def _matches_spec_filters(product: Producto, specs: Dict[str, str], filters: Dict[str, object]) -> bool:
    if not filters:
        return True
    type_name = _norm(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "")
    description = product.descripcion_producto or ""

    if "ram_min" in filters:
        ram_text = _spec_value(specs, ["RAM", "Memoria RAM"])
        if not ram_text and ("memoria" in type_name or "ram" in type_name):
            ram_text = _spec_value(specs, "Capacidad")
        ram_gb = _parse_capacity_gb(ram_text)
        if ram_gb is None or ram_gb < filters["ram_min"]:
            return False

    if "threads_min" in filters:
        threads_text = _spec_value(specs, ["Núcleos / hilos", "Nucleos / hilos"])
        if not threads_text:
            threads_text = _spec_contains(specs, "hilos")
        threads = _parse_threads(threads_text)
        if threads is None or threads < filters["threads_min"]:
            return False

    storage_text = None
    if "storage_min" in filters or "storage" in filters:
        storage_text = _spec_value(specs, STORAGE_SPEC_KEYS)
        if not storage_text:
            storage_text = _spec_contains(specs, "almacenamiento")
        if not storage_text:
            return False

    if "storage_min" in filters:
        storage_gb = _parse_capacity_gb(storage_text)
        if storage_gb is None or storage_gb < filters["storage_min"]:
            return False

    if "storage" in filters:
        storage_kind = filters["storage"]
        sample = (storage_text or "").lower()
        if storage_kind == "nvme":
            if "nvme" not in sample:
                return False
        elif storage_kind == "ssd":
            if "ssd" not in sample and "nvme" not in sample:
                return False

    if "gpu_mem_min" in filters:
        vram_text = _spec_value(specs, "Memoria")
        vram_gb = _parse_capacity_gb(vram_text)
        if vram_gb is None or vram_gb < filters["gpu_mem_min"]:
            return False

    if "gpu_bus" in filters:
        bus_text = _spec_value(specs, "Bus")
        if not bus_text:
            bus_text = _spec_value(specs, "Expansiones")
        if not bus_text:
            return False
        bus_version = _parse_gpu_bus_version(bus_text)
        required = _required_bus_version(filters["gpu_bus"])
        if required is not None:
            if bus_version is None or bus_version + 1e-6 < required:
                return False
        elif filters["gpu_bus"] not in bus_text.lower():
            return False

    if "socket_hint" in filters:
        socket_text = _spec_value(specs, "Socket")
        if not socket_text or filters["socket_hint"] not in socket_text.upper():
            return False

    if "psu_w_min" in filters:
        potencia_text = _spec_value(specs, "Potencia")
        if not potencia_text:
            potencia_text = _spec_contains(specs, "potencia")
        watts = _parse_watts(potencia_text)
        if watts is None or watts < filters["psu_w_min"]:
            return False

    if "battery_wh_min" in filters:
        battery_text = _spec_value(specs, BATTERY_SPEC_KEYS)
        if not battery_text:
            battery_text = _spec_contains(specs, "bateria")
        battery_wh = _parse_battery_wh(battery_text)
        if battery_wh is None or battery_wh < filters["battery_wh_min"]:
            return False

    if "weight_max" in filters:
        weight_text = _spec_value(specs, WEIGHT_SPEC_KEYS)
        grams = _parse_weight_grams(weight_text)
        if grams is None:
            grams = _parse_weight_grams(description)
        if grams is None or grams > filters["weight_max"]:
            return False

    if "display_resolution" in filters:
        display_text = _spec_value(specs, DISPLAY_SPEC_KEYS)
        if not display_text:
            display_text = _spec_contains(specs, "pantalla")
        width = _parse_resolution_width(display_text)
        if width is None:
            return False
        thresholds = {
            "fhd": 1900,
            "2k": 2000,
            "qhd": 2500,
            "4k": 3800,
            "uhd": 3800,
        }
        goal = thresholds.get(filters["display_resolution"], 0)
        if width < goal:
            return False

    if "port_hint" in filters and not _spec_value_contains(specs, filters["port_hint"]):
        return False

    return True


def _value_profile(min_price: Decimal | None) -> Tuple[str, int]:
    if min_price is None:
        return ("Pendiente", 3)
    price = float(min_price)
    if price <= 400000:
        return ("Muy alto", 0)
    if price <= 700000:
        return ("Alto", 1)
    if price <= 1100000:
        return ("Equilibrado", 2)
    return ("Inversion", 3)


def _value_product(product: Producto, specs: Dict[str, str], price: Decimal | None) -> Tuple[str, int]:
    """
    Determina el valor/precio específico para cada tipo de producto.
    Ranking: 0 = Económico, 1 = Medio, 2 = Alto, 3 = Premium
    """
    if price is None:
        return ("Pendiente", 3)
    tipo = _norm(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "")
    price_float = float(price)
    # Procesadores
    if "procesador" in tipo:
        if price_float >= 400000:
            return ("Premium", 3)
        elif price_float >= 250000:
            return ("Alto Rendimiento", 2)
        elif price_float >= 150000:
            return ("Gama Media", 1)
        return ("Básico / Económico", 0)
    # Placas madre
    if "placa" in tipo or "motherboard" in tipo:
        if price_float >= 250000:
            return ("Premium", 3)
        elif price_float >= 150000:
            return ("Alto Rendimiento", 2)
        elif price_float >= 80000:
            return ("Gama Media", 1)
        return ("Básico / Económico", 0)
    # Memoria RAM
    if "memoria" in tipo:
        if price_float >= 100000:
            return ("Premium", 3)
        elif price_float >= 60000:
            return ("Alto Rendimiento", 2)
        elif price_float >= 35000:
            return ("Gama Media", 1)
        return ("Básico / Económico", 0)
    # Tarjetas gráficas
    if "tarjeta" in tipo:
        if price_float >= 800000:
            return ("Premium", 3)
        elif price_float >= 400000:
            return ("Alto Rendimiento", 2)
        elif price_float >= 200000:
            return ("Gama Media", 1)
        return ("Básico / Económico", 0)
    # Fuentes de poder
    if "fuente" in tipo:
        if price_float >= 120000:
            return ("Premium", 3)
        elif price_float >= 80000:
            return ("Alto Rendimiento", 2)
        elif price_float >= 45000:
            return ("Gama Media", 1)
        return ("Básico / Económico", 0)
    # Notebooks/Laptops
    if "notebook" in tipo or "laptop" in tipo:
        if price_float >= 1100000:
            return ("Premium", 3)
        elif price_float >= 700000:
            return ("Alto Rendimiento", 2)
        elif price_float >= 400000:
            return ("Gama Media", 1)
        return ("Básico / Económico", 0)
    # All in One
    if "all in one" in tipo:
        if price_float >= 1200000:
            return ("Premium", 3)
        elif price_float >= 800000:
            return ("Estándar", 2)
        elif price_float >= 500000:
            return ("Medio", 1)
        return ("Básico / Económico", 0)
    # Para otros productos usar rangos generales
    if price_float >= 1000000:
        return ("Premium", 3)
    elif price_float >= 600000:
        return ("Estándar", 2)
    elif price_float >= 300000:
        return ("Medio", 1)
    return ("Básico / Económico", 0)


def _ventilation_profile(product: Producto, specs: Dict[str, str], description: str) -> Tuple[str, int]:
    tipo = _norm(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "")
    if "procesador" in tipo:
        return ("Activa (Ventilador)", 2)
    if "placa" in tipo or "motherboard" in tipo:
        return ("Pasiva (Disipadores Fijos)", 1)
    if "memoria" in tipo or "almacenamiento" in tipo:
        return ("Pasiva (Disipador)", 1)
    if "tarjeta" in tipo:
        return ("Activa (Doble/Triple Ventilador)", 2)
    if "fuente" in tipo:
        return ("Semi-Pasivo (Ventilador)", 2)
    if "notebook" in tipo or "all in one" in tipo:
        return ("Activa (Interna)", 2)
    return ("No requiere disipación", 0)


def _portability_profile(product: Producto, specs: Dict[str, str], description: str) -> Tuple[str, int]:
    tipo = _norm(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "")
    if "tablet" in tipo:
        return ("Ultraligera", 0)
    if "notebook" in tipo or "laptop" in tipo:
        weight = _extract_weight(specs, description)
        if weight is not None:
            if weight <= 1300:
                return ("Ultraligera", 0)
            if weight <= 1800:
                return ("Ligera", 1)
            return (f"{weight:.1f} g", 2)
        return ("Portatil", 1)
    if "all-in-one" in tipo:
        return ("Movible", 2)
    return ("Estacionaria", 3)


def _thermal_profile(product: Producto, specs: Dict[str, str], description: str) -> Tuple[str, int]:
    tipo = _norm(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "")
    if "procesador" in tipo:
        return ("Revisa la pasta térmica y el ventilador.", 2)
    if "placa" in tipo or "motherboard" in tipo:
        return ("Permite el paso del aire sobre los chips.", 1)
    if "memoria" in tipo or "almacenamiento" in tipo:
        return ("Garantiza aire fresco y estable.", 1)
    if "tarjeta" in tipo or "fuente" in tipo:
        return ("Asegura la salida del aire caliente.", 1)
    if "fuente" in tipo:
        return ("Evita que aspire aire caliente de la PC.", 2)
    if "notebook" in tipo or "laptop" in tipo:
        return ("No lo cubras ni lo dejes cerca de calor extremo.", 1)
    if "all-in-one" in tipo or "laptop" in tipo:
        return ("No lo cubras ni lo dejes cerca de calor extremo.", 1)
    return ("No requiere flujo", 0)


def _compute_match(avg_rating: float, review_count: int, view_count: int, min_price: Decimal | None, stock_total: int) -> int:
    score = 82
    if avg_rating:
        score += min(10, round(avg_rating * 2))
    if review_count >= 8:
        score += 4
    elif review_count >= 3:
        score += 2
    if view_count >= 15:
        score += 2
    elif view_count >= 5:
        score += 1
    if min_price and float(min_price) <= 600000:
        score += 2
    if stock_total <= 0:
        score -= 3
    return max(80, min(98, score))


def _product_reasons(product: Producto, min_price: Decimal | None, avg_rating: float, review_count: int) -> List[str]:
    reasons: List[str] = []
    brand = product.marca_producto.nombre_marca if product.marca_producto_id else ""
    tipo = product.tipo_producto.nombre_tipo if product.tipo_producto_id else ""
    categoria = product.categoria_producto.nombre_categoria if product.categoria_producto_id else ""
    if brand and tipo:
        reasons.append(f"{brand} en {tipo}")
    elif brand:
        reasons.append(f"Marca {brand}")
    if avg_rating:
        reasons.append(f"Resenas {avg_rating:.1f}/5 ({review_count})")
    elif min_price:
        price_display = _format_currency(min_price)
        if price_display:
            reasons.append(f"Referencias desde {price_display}")
    if len(reasons) < 2 and categoria:
        reasons.append(f"Categoria {categoria}")
    return reasons[:2] or ["Analisis editorial"]


def _product_tradeoffs(min_price: Decimal | None, review_count: int, stock_total: int) -> List[str]:
    tradeoffs: List[str] = []
    if stock_total <= 0:
        tradeoffs.append("Stock por confirmar")
    elif stock_total < 5:
        tradeoffs.append("Stock limitado")
    if review_count < 2:
        tradeoffs.append("Pocas resenas verificadas")
    elif min_price and float(min_price) > 1200000:
        tradeoffs.append("Inversion alta")
    if not tradeoffs and min_price:
        tradeoffs.append("Precio varía segun tienda")
    return tradeoffs[:1]


def _educational_hint(avg_rating: float, review_count: int, min_price: Decimal | None, tipo: str) -> str:
    if min_price:
        price_display = _format_currency(min_price)
        if price_display:
            return f"Valida compatibilidad con tu equipo antes de invertir {price_display}."
    tipo = (tipo or "").lower()
    if "notebook" in tipo or "laptop" in tipo:
        return "Confirma peso, autonomia y puertos contra tus jornadas reales."
    return "Revisa especificaciones clave y compara alternativas cercanas."


def _build_criteria(product: Producto, specs: Dict[str, str], description: str) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    value_label, value_rank = _value_product(product, specs, product.min_price)
    ventilation_label, ventilation_rank = _ventilation_profile(product, specs, description)
    portability_label, portability_rank = _portability_profile(product, specs, description)
    thermal_label, thermal_rank = _thermal_profile(product, specs, description)
    criteria = [
        {"label": "Gama", "value": value_label},
        {"label": "Disipación", "value": ventilation_label},
        {"label": "Portabilidad", "value": portability_label},
        {"label": "Temperaturas", "value": thermal_label},
    ]
    ranks = {
        "value": value_rank,
        "quiet": ventilation_rank,
        "portable": portability_rank,
        "thermals": thermal_rank,
    }
    return criteria, ranks


def _key_specs(product: Producto, specs: Dict[str, str]) -> List[Dict[str, str]]:
    ordered: List[Dict[str, str]] = []
    seen = set()
    template = SPEC_TEMPLATES.get(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "", [])
    for label in template:
        value = _spec_lookup(specs, label)
        if value:
            ordered.append({"name": label, "value": value})
            seen.add(_norm(label))
        if len(ordered) >= 6:
            break
    if len(ordered) < 6:
        for raw_name, raw_value in specs.items():
            norm_name = _norm(raw_name)
            if norm_name in seen:
                continue
            ordered.append({"name": raw_name, "value": raw_value})
            seen.add(norm_name)
            if len(ordered) >= 6:
                break
    return ordered


def _build_type_profile(product: Producto, specs: Dict[str, str]) -> Dict[str, List[str]]:
    type_name = product.tipo_producto.nombre_tipo if product.tipo_producto_id else "Producto"
    type_norm = _norm(type_name)
    profile = {
        "label": type_name,
        "highlights": [],
        "metrics": [],
    }

    def add_highlight(text: str):
        if text and len(profile["highlights"]) < 3:
            profile["highlights"].append(text)

    def add_metric(label: str, value: str):
        if value and len(profile["metrics"]) < 4:
            profile["metrics"].append({"label": label, "value": value})

    if "procesador" in type_norm:
        freq = _spec_lookup(specs, "Frecuencia")
        turbo = _spec_lookup(specs, "Frecuencia turbo maxima")
        if freq and turbo:
            add_highlight(f"{freq} base / {turbo} turbo")
        elif freq:
            add_highlight(f"Frecuencia {freq}")
        cores = _spec_lookup(specs, "Nucleos / hilos")
        add_highlight(cores)
        igpu = _spec_lookup(specs, "Graficos integrados")
        if igpu and "no" not in igpu.lower():
            add_highlight(f"iGPU {igpu}")
        add_metric("Socket", _spec_lookup(specs, "Socket"))
        add_metric("Cores", _spec_lookup(specs, "Nucleos / hilos"))
        add_metric("TDP", _spec_lookup(specs, "TDP"))
        add_metric("Cooler", _spec_lookup(specs, "Cooler"))

    elif "notebook" in type_norm:
        add_highlight(_spec_lookup(specs, "Procesador"))
        add_highlight(_spec_lookup(specs, "RAM"))
        add_highlight(_spec_lookup(specs, "Tarjetas de video"))
        add_highlight(_spec_lookup(specs, "Almacenamiento"))
        add_metric("Pantalla", _spec_lookup(specs, "Pantalla"))
        add_metric("Peso", _spec_lookup(specs, "Peso"))
        add_metric("Bateria", _spec_lookup(specs, "Bateria"))
        add_metric("SO", _spec_lookup(specs, "Sistema Operativo"))

    elif "tablet" in type_norm:
        add_highlight(_spec_lookup(specs, "Pantalla"))
        add_highlight(_spec_lookup(specs, "Memoria interna"))
        add_highlight(_spec_lookup(specs, "RAM"))
        add_metric("Procesador", _spec_lookup(specs, "Procesador"))
        add_metric("Peso", _spec_lookup(specs, "Peso"))
        add_metric("Bateria", _spec_lookup(specs, "Bateria"))
        add_metric("SO", _spec_lookup(specs, "Sistema operativo"))

    elif "all-in-one" in type_norm or "all in one" in type_norm:
        add_highlight(_spec_lookup(specs, "Procesador"))
        add_highlight(_spec_lookup(specs, "RAM"))
        add_highlight(_spec_lookup(specs, "Tarjeta de video"))
        add_metric("Pantalla", _spec_lookup(specs, "Pantalla"))
        add_metric("Procesador", _spec_lookup(specs, "Procesador"))
        add_metric("Almacenamiento", _spec_lookup(specs, "Almacenamiento"))
        add_metric("SO", _spec_lookup(specs, "Sistema Operativo"))

    elif "tarjeta" in type_norm or "grafica" in type_norm or "gráfica" in type_norm:
        add_highlight(_spec_lookup(specs, "GPU"))
        add_highlight(_spec_lookup(specs, "Memoria"))
        add_highlight(_spec_lookup(specs, "Frecuencias core (base / boost)"))
        add_metric("Bus", _spec_lookup(specs, "Bus"))
        add_metric("Memoria", _spec_lookup(specs, "Memoria"))
        add_metric("Refrigeracion", _spec_lookup(specs, "Refrigeracion"))
        add_metric("Largo", _spec_lookup(specs, "Largo"))

    elif "memoria" in type_norm:
        add_highlight(_spec_lookup(specs, "Capacidad"))
        add_highlight(_spec_lookup(specs, "Velocidad"))
        add_highlight(_spec_lookup(specs, "Latencia Cl (CAS)"))
        add_metric("Tipo", _spec_lookup(specs, "Tipo"))
        add_metric("Voltaje", _spec_lookup(specs, "Voltaje"))
        add_metric("Velocidad", _spec_lookup(specs, "Velocidad"))
        add_metric("Capacidad", _spec_lookup(specs, "Capacidad"))

    elif "fuente" in type_norm or "power" in type_norm:
        add_highlight(_spec_lookup(specs, "Potencia"))
        add_highlight(_spec_lookup(specs, "Certificacion"))
        modular = _spec_lookup(specs, "Modular")
        if modular:
            add_highlight(f"Modular: {modular}")
        add_metric("Potencia", _spec_lookup(specs, "Potencia"))
        add_metric("Modular", _spec_lookup(specs, "Modular"))
        add_metric("Tamaño", _spec_lookup(specs, "Tamano"))
        add_metric("Conectores", _spec_lookup(specs, "Conectores de energia"))

    elif "placa" in type_norm or "mother" in type_norm:
        socket = _spec_lookup(specs, "Socket")
        chipset = _spec_lookup(specs, "Chipset")
        if socket and chipset:
            add_highlight(f"{socket} · {chipset}")
        else:
            add_highlight(socket or chipset)
        add_highlight(_spec_lookup(specs, "Formato"))
        add_highlight(_spec_lookup(specs, "Soporte RGB"))
        add_metric("Socket", _spec_lookup(specs, "Socket"))
        add_metric("Slots RAM", _spec_lookup(specs, "Slots memorias"))
        add_metric("Canales memoria", _spec_lookup(specs, "Canales memoria"))
        add_metric("Puertos de video", _spec_lookup(specs, "Puertos de video"))

    if not profile["highlights"]:
        for value in list(specs.values())[:3]:
            add_highlight(value)
    if not profile["metrics"]:
        for name, value in list(specs.items())[:4]:
            add_metric(name, value)
    return profile


def _select_top_recommendations(cards: List[Dict], limit: int = 6, per_type: int = 2) -> List[Dict]:
    selected: List[Dict] = []
    type_counts = defaultdict(int)
    seen = set()
    for card in cards:
        key = (_norm(card.get("type", "")) or "otro")
        if type_counts[key] >= per_type:
            continue
        selected.append(card)
        seen.add(id(card))
        type_counts[key] += 1
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for card in cards:
            if id(card) in seen:
                continue
            selected.append(card)
            if len(selected) >= limit:
                break
    return selected


def _build_similarity_signature(product: Producto, specs: Dict[str, str]) -> Dict[str, str]:
    tipo = product.tipo_producto.nombre_tipo if product.tipo_producto_id else ""
    tipo_norm = _norm(tipo)
    signature: Dict[str, str] = {}
    if "procesador" in tipo_norm:
        signature["socket"] = _spec_lookup(specs, "Socket") or ""
        signature["tdp"] = _spec_lookup(specs, "TDP") or ""
        signature["cores"] = _spec_lookup(specs, "Nucleos / hilos") or ""
    elif "notebook" in tipo_norm:
        signature["cpu"] = _spec_lookup(specs, "Procesador") or ""
        signature["peso"] = _spec_lookup(specs, "Peso") or ""
        signature["pantalla"] = _spec_lookup(specs, "Pantalla") or ""
    elif "tablet" in tipo_norm:
        signature["pantalla"] = _spec_lookup(specs, "Pantalla") or ""
        signature["ram"] = _spec_lookup(specs, "RAM") or ""
    elif "fuente" in tipo_norm:
        signature["potencia"] = _spec_lookup(specs, "Potencia") or ""
        signature["certificacion"] = _spec_lookup(specs, "Certificacion") or ""
    elif "tarjeta" in tipo_norm or "grafica" in tipo_norm:
        signature["gpu"] = _spec_lookup(specs, "GPU") or ""
        signature["memoria"] = _spec_lookup(specs, "Memoria") or ""
        signature["bus"] = _spec_lookup(specs, "Bus") or ""
    elif "placa" in tipo_norm:
        signature["socket"] = _spec_lookup(specs, "Socket") or ""
        signature["chipset"] = _spec_lookup(specs, "Chipset") or ""
    return signature


def _compare_signatures(base: Dict[str, str], other: Dict[str, str]) -> List[str]:
    match_points: List[str] = []
    for key, value in base.items():
        if value and other.get(key) == value:
            if key == "socket":
                match_points.append(f"Socket {value}")
            elif key == "tdp":
                match_points.append(f"TDP {value}")
            elif key == "cores":
                match_points.append(value)
            elif key == "cpu":
                match_points.append(value)
            elif key == "pantalla":
                match_points.append(f"Pantalla {value}")
            elif key == "potencia":
                match_points.append(f"{value} W")
            elif key == "certificacion":
                match_points.append(value)
            elif key == "gpu":
                match_points.append(value)
            elif key == "memoria":
                match_points.append(value)
            elif key == "bus":
                match_points.append(f"Bus {value}")
            elif key == "chipset":
                match_points.append(value)
    return match_points[:2]


def _match_spec_value(base_value: str | None, target_value: str | None) -> bool:
    if not base_value or not target_value:
        return False
    base_norm = _norm(base_value)
    target_norm = _norm(target_value)
    if not base_norm or not target_norm:
        return False
    if base_norm in target_norm or target_norm in base_norm:
        return True

    def extract_tokens(text: str) -> set[str]:
        tokens = set()
        tokens.update(re.findall(r"(ddr\s*\d+)", text))
        tokens.update(re.findall(r"(pci[e]?\s*[\d\.]+)", text))
        pin_tokens = re.findall(r"(\d+\+?\d*\s*pines)", text)
        for token in pin_tokens:
            tokens.add(token)
            sum_match = re.match(r"(\d+)\+(\d+)\s*pines", token)
            if sum_match:
                total = int(sum_match.group(1)) + int(sum_match.group(2))
                tokens.add(f"{total} pines")
        return {token.strip() for token in tokens if token and token.strip()}

    base_tokens = extract_tokens(base_norm)
    target_tokens = extract_tokens(target_norm)
    if base_tokens and target_tokens and base_tokens.intersection(target_tokens):
        return True

    return False


MATCH_FUNCS = {}


def register_match_func(name):
    def decorator(func):
        MATCH_FUNCS[name] = func
        return func
    return decorator


def _parse_pcie_descriptor(text: str) -> dict:
    desc = (text or "").lower()
    if "pci" not in desc:
        return {}
    version = None
    lanes = None
    version_match = re.search(r'(?:pci[e]?\s*express?\s*)(\d+(?:\.\d+)?)', desc)
    if version_match:
        try:
            version = float(version_match.group(1))
        except ValueError:
            version = None
    lane_match = re.search(r'x\s*(\d+)', desc)
    if lane_match:
        try:
            lanes = int(lane_match.group(1))
        except ValueError:
            lanes = None
    return {"version": version, "lanes": lanes}


@register_match_func("gpu_board")
def _gpu_board_match(base_specs: Dict[str, str], target_specs: Dict[str, str]) -> tuple[bool, str | None]:
    gpu_bus = _spec_value(base_specs, ["bus", "bus pci"])
    board_expansions = _spec_value(target_specs, ["expansiones", "expansiones memorias"])
    if not gpu_bus or not board_expansions:
        return False, None
    gpu_info = _parse_pcie_descriptor(gpu_bus)
    base_lanes = gpu_info.get("lanes") or 16
    base_version = gpu_info.get("version")
    degrade_notes = []
    compatible = False

    for part in re.split(r',\s*', board_expansions):
        slot = _parse_pcie_descriptor(part)
        if not slot:
            continue
        lanes = slot.get("lanes") or 0
        version = slot.get("version")
        if lanes >= base_lanes or lanes >= 16:
            compatible = True
            if base_version and version and version < base_version:
                degrade_notes.append(f"placa PCIe {version} limitará GPU {base_version}")
            break
        elif lanes >= 8:
            compatible = True
            degrade_notes.append(f"slot x{lanes} limitará GPU x{base_lanes}")
            break

    if not compatible:
        return False, None
    message = "PCIe x{}".format(base_lanes if base_lanes else 16)
    if degrade_notes:
        message += f" ({'; '.join(degrade_notes)})"
    return True, message


SIMILAR_KEYS = {
    "procesador": ["socket"],
    "placa": ["socket"],
    "memoria": ["tipo", "tipo ram"],
    "tarjeta": ["gpu"],
    "fuente": ["potencia"],
}


def _is_similar_candidate(type_key: str, base_specs: Dict[str, str], candidate_specs: Dict[str, str]) -> bool:
    keys = SIMILAR_KEYS.get(type_key)
    if not keys:
        return True
    for key in keys:
        base_val = _spec_value(base_specs, key)
        cand_val = _spec_value(candidate_specs, key)
        if base_val and cand_val and _match_spec_value(base_val, cand_val):
            return True
    return False

def _canonical_type_key(type_name: str) -> str:
    norm_name = _norm(type_name or "")
    for key in COMPATIBILITY_MAP.keys():
        if key in norm_name:
            return key
    return norm_name


def _supports_compatibility(type_name: str) -> bool:
    key = _canonical_type_key(type_name)
    return key in COMPATIBILITY_MAP


def _compatibility_matches(base_type: str, alt_type: str, base_specs: Dict[str, str], alt_specs: Dict[str, str]) -> List[str]:
    base_norm = _canonical_type_key(base_type)
    alt_norm = _canonical_type_key(alt_type)
    rules = COMPATIBILITY_MAP.get(base_norm)
    matches: List[str] = []
    if not rules:
        return matches
    for rule in rules:
        target_norm = _norm(rule["type"])
        if target_norm not in alt_norm:
            continue
        match_func = MATCH_FUNCS.get(rule.get("match_func"))
        if match_func:
            matched, msg = match_func(base_specs, alt_specs)
            if matched:
                matches.append(msg or rule.get("label") or "Compatible")
            continue
        base_value = _spec_value(base_specs, rule["base_key"])
        target_value = _spec_value(alt_specs, rule["target_key"])
        if _match_spec_value(base_value, target_value):
            label = rule.get("label") or ""
            if label and base_value:
                matches.append(f"{label} {base_value}")
            elif base_value:
                matches.append(base_value)
    return matches[:2]


def _fetch_related_products(
    product: Producto,
    base_specs: Dict[str, str],
    per_type_limit: int | None = 3,
    include_same_type: bool = True,
    compatibility_only: bool = False,
) -> List[Producto]:
    if compatibility_only:
        include_same_type = False
    tipo = _canonical_type_key(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "")
    related = []
    seen_ids = set()

    if include_same_type and not compatibility_only:
        same_type_qs = (
            _base_product_queryset()
            .filter(tipo_producto_id=product.tipo_producto_id)
            .exclude(pk=product.pk)
            .order_by("-avg_rating", "min_price")[:6]
        )
        for item in same_type_qs:
            if item.id not in seen_ids:
                candidate_specs = _build_spec_map(item)
                if _is_similar_candidate(tipo, base_specs, candidate_specs):
                    related.append(item)
                    seen_ids.add(item.id)

    mapping = COMPATIBILITY_MAP.get(tipo)
    if mapping:
        for rule in mapping:
            target_type_name = rule["type"]
            target_qs = (
                _base_product_queryset()
                .filter(tipo_producto__nombre_tipo__icontains=target_type_name)
                .order_by("-avg_rating", "min_price")
            )
            count = 0
            for item in target_qs:
                if item.id in seen_ids:
                    continue
                if rule.get("match_func"):
                    related.append(item)
                    seen_ids.add(item.id)
                    count += 1
                else:
                    base_value = _spec_value(base_specs, rule.get("base_key"))
                    if not base_value:
                        continue
                    item_specs = _build_spec_map(item)
                    target_value = _spec_value(item_specs, rule.get("target_key"))
                    if _match_spec_value(base_value, target_value):
                        related.append(item)
                        seen_ids.add(item.id)
                        count += 1
                if per_type_limit and count >= per_type_limit:
                    break
    return related


def _compatibility_partners(
    product: Producto,
    base_specs: Dict[str, str],
    limit: int = 2,
    pref_ctx: Dict[str, object] | None = None,
) -> List[Dict[str, object]]:
    partners: List[Dict[str, object]] = []
    base_type = product.tipo_producto.nombre_tipo if product.tipo_producto_id else ""
    if not _supports_compatibility(base_type):
        return partners
    related = _fetch_related_products(
        product,
        base_specs,
        per_type_limit=limit,
        include_same_type=False,
        compatibility_only=True,
    )
    for rel in related:
        card = _product_payload(rel)
        _apply_preference_match(card, pref_ctx or {})
        rel_specs = card.pop("_spec_map", None) or {}
        matches = _compatibility_matches(
            base_type,
            rel.tipo_producto.nombre_tipo if rel.tipo_producto_id else "",
            base_specs,
            rel_specs,
        )
        if not matches:
            continue
        partners.append(
            {
                "id": card["id"],
                "name": card["name"],
                "type": card["type"],
                "detail_url": card["detail_url"],
                "match": card["match"],
                "match_caption": card.get("match_caption"),
                "matches": matches,
                "category_id": card["category_id"],
            }
        )
        if len(partners) >= limit:
            break
    return partners


def _make_alt_card(card: Dict[str, object], summary: str, compat_points: List[str] | None = None) -> Dict[str, object]:
    return {
        "id": card["id"],
        "name": card["name"],
        "match": card["match"],
        "match_caption": card.get("match_caption"),
        "detail_url": card["detail_url"],
        "summary": summary,
        "type_highlights": card["type_profile"]["highlights"][:2],
        "type_id": card["type_id"],
        "category_id": card["category_id"],
        "type": card["type"],
        "compat_points": compat_points or [],
    }


def _build_alternatives_payload(
    product: Producto,
    base_signature: Dict[str, str],
    pref_ctx: Dict[str, object] | None = None,
) -> Dict[str, List[Dict[str, object]]]:
    specs = _build_spec_map(product)
    related_products = _fetch_related_products(product, specs, per_type_limit=3, include_same_type=True)
    similar: List[Dict[str, object]] = []
    compatible: List[Dict[str, object]] = []
    seen_ids = {product.id}
    base_type = product.tipo_producto.nombre_tipo if product.tipo_producto_id else ""

    for alt in related_products:
        if alt.id in seen_ids:
            continue
        card = _product_payload(alt)
        _apply_preference_match(card, pref_ctx or {})
        alt_specs = card.pop("_spec_map", {})
        similarity = _compare_signatures(base_signature, _build_similarity_signature(alt, alt_specs))
        compat_matches = _compatibility_matches(
            base_type,
            alt.tipo_producto.nombre_tipo if alt.tipo_producto_id else "",
            specs,
            alt_specs,
        )

        card_summary = card["educational_hint"]
        target_list = similar
        if compat_matches:
            card_summary = "Compatible: " + ", ".join(compat_matches)
            target_list = compatible
        elif similarity:
            card_summary = "Coincide en " + ", ".join(similarity)
            target_list = similar
        elif card["tradeoffs"]:
            card_summary = f"Trade-off: {card['tradeoffs'][0]}"

        target_list.append(_make_alt_card(card, card_summary, compat_matches if compat_matches else None))
        seen_ids.add(alt.id)

    return {
        "similar": similar[:6],
        "compatible": compatible[:6],
    }


def _compatibility_empty_notice(product: Producto) -> str:
    type_name = product.tipo_producto.nombre_tipo if product.tipo_producto_id else ""
    product_name = product.nombre_producto
    if not _supports_compatibility(type_name):
        type_label = type_name or "este producto"
        return (
            f"{type_label} no tiene compatibilidades automatizadas en esta fase. "
            f"Mostramos el listado general tras intentar combinar {product_name}."
        )
    return (
        f"No encontramos componentes compatibles activos para {product_name}. "
        "Revisa filtros manuales o vuelve mas tarde."
    )


COMPATIBILITY_MAP = {
    "procesador": [
        {"type": "placa", "base_key": "socket", "target_key": "socket", "label": "Socket"},
        {"type": "placa", "base_key": "tdp", "target_key": "tdp", "label": "TDP"},
    ],
    "placa": [
        {"type": "procesador", "base_key": "socket", "target_key": "socket", "label": "Socket"},
        {"type": "memoria", "base_key": ["slots memorias", "slots ram"], "target_key": ["tipo", "tipo ram"], "label": "RAM"},
        {"type": "fuente", "base_key": ["puertos de energia", "puertos de energía"], "target_key": ["conectores de energia", "conectores de energía"], "label": "Alimentacion"},
        {"type": "tarjeta", "base_key": ["expansiones", "expansiones memorias"], "target_key": ["bus", "bus pci"], "label": "Expansiones"},
    ],
    "memoria": [
        {"type": "placa", "base_key": ["tipo", "tipo ram"], "target_key": ["slots memorias", "slots ram"], "label": "Tipo RAM"},
    ],
    "tarjeta": [
        {"type": "placa", "match_func": "gpu_board"},
        {"type": "fuente", "base_key": ["conectores de poder", "conectores pci"], "target_key": ["conectores de energia", "conectores de energía"], "label": "Conector PCIe"},
    ],
    "fuente": [
        {"type": "placa", "base_key": ["conectores de energia", "puertos de energia"], "target_key": ["puertos de energia", "puertos de energía"], "label": "24/CPU"},
        {"type": "tarjeta", "base_key": ["conectores de energia", "conectores pci", "conectores de poder"], "target_key": ["conectores de poder", "conectores pci"], "label": "Conector PCIe"},
    ],
}


def _base_product_queryset():
    return (
        Producto.objects.filter(is_active=True)
        .select_related("marca_producto", "categoria_producto", "tipo_producto")
        .prefetch_related(
            Prefetch(
                "especificacionproducto_set",
                queryset=EspecificacionProducto.objects.all(),
                to_attr="prefetched_specs",
            ),
            "categorias_extra",
            Prefetch(
                "referencias",
                queryset=ProductReference.objects.all(),
                to_attr="prefetched_references",
            ),
        )
        .annotate(
            avg_rating=Avg("reviews__rating"),
            review_count=Count("reviews", distinct=True),
            min_price=Min("referencias__precio"),
            max_price=Coalesce(
                Max("referencias__precio"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            stock_total=Coalesce(
                Sum("referencias__stock"),
                Value(0),
                output_field=IntegerField(),
            ),
            view_count=Count("productovisto", distinct=True),
        )
    )


def _product_payload(product: Producto) -> Dict[str, object]:
    specs = _build_spec_map(product)
    avg_rating = float(product.avg_rating or 0.0)
    review_count = int(product.review_count or 0)
    min_price = product.min_price
    stock_total = int(product.stock_total or 0)
    match_score = _compute_match(avg_rating, review_count, int(product.view_count or 0), min_price, stock_total)
    criteria, criteria_ranks = _build_criteria(product, specs, product.descripcion_producto or "")
    type_profile = _build_type_profile(product, specs)
    type_name = product.tipo_producto.nombre_tipo if product.tipo_producto_id else ""
    extra_categories = list(product.categorias_extra.all())
    extra_category_names = [cat.nombre_categoria for cat in extra_categories]
    extra_category_ids = [cat.id for cat in extra_categories]
    primary_category_name = product.categoria_producto.nombre_categoria if product.categoria_producto_id else ""
    primary_category_id = product.categoria_producto_id
    category_labels: List[str] = []
    category_ids: List[int] = []
    if primary_category_name:
        category_labels.append(primary_category_name)
        category_ids.append(primary_category_id)
    seen_category_ids = set(category_ids)
    for cat in extra_categories:
        if cat.id in seen_category_ids:
            continue
        category_labels.append(cat.nombre_categoria)
        category_ids.append(cat.id)
        seen_category_ids.add(cat.id)
    categories_meta = []
    for idx, label in enumerate(category_labels):
        cat_id = category_ids[idx] if idx < len(category_ids) else None
        categories_meta.append(
            {
                "id": cat_id,
                "name": label,
            }
        )
    payload = {
        "id": product.id,
        "name": product.nombre_producto,
        "model": product.modelo_producto,
        "image": product.imagen_producto.url if product.imagen_producto else None,
        "image_alt": product.nombre_producto,
        "match": match_score,
        "type_name": type_name,
        "reasons": _product_reasons(product, min_price, avg_rating, review_count),
        "tradeoffs": _product_tradeoffs(min_price, review_count, stock_total),
        "criteria": criteria,
        "min_price_display": _format_currency(min_price),
        "min_price_value": float(min_price) if min_price is not None else None,
        "avg_rating": avg_rating,
        "review_count": review_count,
        "brand": product.marca_producto.nombre_marca if product.marca_producto_id else "",
        "category": primary_category_name,
        "category_id": primary_category_id,
        "categories_all": category_labels,
        "category_all_ids": category_ids,
        "extra_categories": extra_category_names,
        "extra_category_ids": extra_category_ids,
        "categories_meta": categories_meta,
        "type": type_name,
        "type_id": product.tipo_producto_id,
        "description": product.descripcion_producto,
        "detail_url": f"{reverse('reco_detail')}?id={product.id}",
        "stock_total": stock_total,
        "educational_hint": _educational_hint(avg_rating, review_count, min_price, type_name),
        "sort_match": -match_score,
        "sort_value": criteria_ranks["value"],
        "sort_quiet": criteria_ranks["quiet"],
        "sort_portable": criteria_ranks["portable"],
        "sort_thermals": criteria_ranks["thermals"],
        "type_profile": type_profile,
        "type_highlights": type_profile["highlights"][:2],
        "type_metrics": type_profile["metrics"][:4],
        "supports_compatibility": _supports_compatibility(type_name),
        "match_base": match_score,
        "show_match": True,
        "match_summary_list": [],
    }
    payload["_spec_map"] = specs
    return payload


def _build_home_compatibility_pairs(
    top_cards: List[Dict[str, object]],
    products_by_id: Dict[int, Producto],
    favorite_ids: set[int] | None = None,
    pref_ctx: Dict[str, object] | None = None,
) -> List[Dict[str, object]]:
    favorite_ids = favorite_ids or set()
    pairs: List[Dict[str, object]] = []
    for card in top_cards:
        product = products_by_id.get(card["id"])
        if not product:
            continue
        specs = card.get("_spec_map") or _build_spec_map(product)
        partners = _compatibility_partners(product, specs, limit=2, pref_ctx=pref_ctx)
        if not partners:
            continue
        focus_points: List[str] = []
        for partner in partners:
            focus_points.extend(partner.get("matches", []))
        focus_points = focus_points[:2]
        pairs.append(
            {
                "base": {
                    "id": card["id"],
                    "name": card["name"],
                    "type": card["type"],
                    "match": card["match"],
                    "detail_url": card["detail_url"],
                    "highlights": card.get("type_highlights", []),
                    "is_favorite": card.get("is_favorite", False),
                    "match_caption": card.get("match_caption"),
                },
                "partners": [
                    {
                        **partner,
                        "is_favorite": partner["id"] in favorite_ids,
                    }
                    for partner in partners
                ],
                "focus_points": focus_points,
                "cta": f"{reverse('reco_explore')}?compat_with={card['id']}",
            }
        )
        if len(pairs) >= 3:
            break
    return pairs


# ===========================
# Vistas principales (home / exploración)
# ===========================
def reco_home(request):
    categorias = _categories_with_inventory().order_by("-prod_count", "nombre_categoria")[:6]
    favorite_ids = _favorite_ids_for(request.user)
    preference_context = _user_preference_context(request.user)
    perfiles = [
        {
            "name": cat.nombre_categoria,
            "subtitle": _short_text(cat.descripcion_categoria, 58),
            "initial": cat.nombre_categoria[:1].upper(),
            "url": f"{reverse('reco_explore')}?categoria={cat.id}",
        }
        for cat in categorias
    ]

    products_qs = list(
        _base_product_queryset()
        .order_by("-avg_rating", "-review_count", "min_price")[:32]
    )
    product_cards = []
    products_by_id: Dict[int, Producto] = {}
    for prod in products_qs:
        payload = _product_payload(prod)
        payload["is_favorite"] = payload["id"] in favorite_ids
        _apply_preference_match(payload, preference_context)
        product_cards.append(payload)
        products_by_id[prod.id] = prod
    prioritized_cards = _prioritize_cards(product_cards, preference_context)
    if not preference_context.get("has_prefs"):
        rng = random.Random(timezone.now().date().toordinal())
        rng.shuffle(prioritized_cards)
    top_recommendations = _select_top_recommendations(prioritized_cards, limit=6, per_type=2)
    compatibility_pairs = _build_home_compatibility_pairs(
        top_recommendations,
        products_by_id,
        favorite_ids,
        preference_context,
    )
    for card in product_cards:
        card.pop("_spec_map", None)
        card.pop("_affinity_flags", None)

    guides = []
    for cat in categorias[:3]:
        guides.append(
            {
                "title": f"{cat.nombre_categoria}: que revisar",
                "summary": _short_text(cat.descripcion_categoria, 120),
                "url": f"{reverse('reco_guides')}?categoria={cat.id}",
            }
        )

    context = {
        "perfiles": perfiles,
        "top_recommendations": top_recommendations,
        "guides": guides,
        "compatibility_pairs": compatibility_pairs,
        "preference_context": preference_context,
    }
    return render(request, "lab/reco_home.html", context)


def _apply_filters(request, queryset):
    categoria_values = request.GET.getlist("categoria")
    perfil_value = request.GET.get("perfil")
    if not categoria_values and perfil_value:
        categoria_values = [perfil_value]
    tipo_values = request.GET.getlist("tipo")
    presupuesto = request.GET.get("presupuesto")
    search = request.GET.get("q")
    brand = request.GET.get("marca")

    categoria_ids = []
    for value in categoria_values:
        if value.isdigit():
            categoria_ids.append(int(value))
    if categoria_ids:
        queryset = queryset.filter(
            Q(categoria_producto_id__in=categoria_ids) | Q(categorias_extra__id__in=categoria_ids)
        ).distinct()

    tipo_ids = []
    for value in tipo_values:
        if value.isdigit():
            tipo_ids.append(int(value))
    if tipo_ids:
        queryset = queryset.filter(tipo_producto_id__in=tipo_ids)
    if presupuesto:
        try:
            low_str, high_str = presupuesto.split("-", 1)
            low = int(low_str) if low_str else None
            high = int(high_str) if high_str else None
            if low is not None:
                queryset = queryset.filter(referencias__precio__gte=low)
            if high is not None:
                queryset = queryset.filter(referencias__precio__lte=high)
        except ValueError:
            pass
    if search:
        queryset = queryset.filter(
            Q(nombre_producto__icontains=search) |
            Q(modelo_producto__icontains=search) |
            Q(descripcion_producto__icontains=search)
        )
    if brand:
        queryset = queryset.filter(marca_producto__nombre_marca__iexact=brand)
    spec_filters = _extract_spec_filters(request.GET)
    return queryset, spec_filters, [str(id_) for id_ in categoria_ids], [str(id_) for id_ in tipo_ids]


def reco_explore(request):
    categorias = _categories_with_inventory().order_by("nombre_categoria")
    tipos = TipoProducto.objects.annotate(
        prod_count=Count("producto", filter=Q(producto__is_active=True))
    ).filter(prod_count__gt=0).order_by("nombre_tipo")
    favorite_ids = _favorite_ids_for(request.user)
    preference_context = _user_preference_context(request.user)

    compat_with = request.GET.get("compat_with")
    compat_source = None
    compat_notice = None
    compat_notice_level = "info"
    compat_results = False
    products: List[Dict[str, object]] = []
    base_queryset = _base_product_queryset()
    products_qs, parsed_spec_filters, selected_categoria_values, selected_tipo_values = _apply_filters(
        request, base_queryset
    )
    raw_spec_params = {key: request.GET.get(key) for key in SPEC_FILTER_QUERY_KEYS if request.GET.get(key)}

    if compat_with and compat_with.isdigit():
        compat_source = _base_product_queryset().filter(pk=int(compat_with)).first()
        if compat_source:
            specs = _build_spec_map(compat_source)
            compat_products = _fetch_related_products(
                compat_source,
                specs,
                per_type_limit=None,
                include_same_type=False,
                compatibility_only=True,
            )
            if compat_products:
                products = []
                for prod in compat_products:
                    payload = _product_payload(prod)
                    _apply_preference_match(payload, preference_context)
                    payload["is_favorite"] = payload["id"] in favorite_ids
                    products.append(payload)
                compat_notice = f"Mostrando productos compatibles con {compat_source.nombre_producto}"
                compat_results = True
            else:
                compat_notice = _compatibility_empty_notice(compat_source)
                compat_notice_level = "warning"

    if not products:
        fetch_limit = 200 if parsed_spec_filters else 50
        candidates = list(products_qs[:fetch_limit])
        if parsed_spec_filters:
            filtered: List[Producto] = []
            for prod in candidates:
                specs = _build_spec_map(prod)
                if _matches_spec_filters(prod, specs, parsed_spec_filters):
                    filtered.append(prod)
            candidates = filtered
        products = []
        for prod in candidates[:50]:
            payload = _product_payload(prod)
            payload["is_favorite"] = payload["id"] in favorite_ids
            _apply_preference_match(payload, preference_context)
            products.append(payload)

    sort_param = request.GET.get("sort", "match")
    if sort_param == "value":
        products.sort(key=lambda p: (p["sort_value"], p["sort_match"]))
    elif sort_param == "quiet":
        products.sort(key=lambda p: (p["sort_quiet"], p["sort_match"]))
    elif sort_param == "portable":
        products.sort(key=lambda p: (p["sort_portable"], p["sort_match"]))
    else:
        products.sort(key=lambda p: (p["sort_match"], p["sort_value"]))

    if not compat_results:
        products = products[:8]
    for payload in products:
        payload["match_score"] = payload["match"]
        payload["match_pill"] = payload.get("match_summary") or payload.get("educational_hint")
        payload["criteria"] = [
            {"label": "Gama", "value": payload["criteria"][0]["value"]},
            {"label": "Disipación", "value": payload["criteria"][1]["value"]},
            {"label": "Portabilidad", "value": payload["criteria"][2]["value"]},
            {"label": "Temperaturas", "value": payload["criteria"][3]["value"]},
        ]

    selected = {
        "categorias": selected_categoria_values,
        "tipos": selected_tipo_values,
        "categoria": selected_categoria_values[0] if selected_categoria_values else "",
        "tipo": selected_tipo_values[0] if selected_tipo_values else "",
        "presupuesto": request.GET.get("presupuesto") or "",
        "marca": request.GET.get("marca") or "",
        "sort": sort_param,
        "spec": raw_spec_params,
    }
    selected_categoria = None
    selected_tipo = None
    categoria_labels: List[str] = []
    tipo_labels: List[str] = []
    if selected["categorias"]:
        for value in selected["categorias"]:
            cat_obj = next((c for c in categorias if str(c.id) == value), None)
            if cat_obj:
                categoria_labels.append(cat_obj.nombre_categoria)
        if selected["categoria"]:
            selected_categoria = next((c for c in categorias if str(c.id) == selected["categoria"]), None)
    if selected["tipos"]:
        for value in selected["tipos"]:
            tipo_obj = next((t for t in tipos if str(t.id) == value), None)
            if tipo_obj:
                tipo_labels.append(tipo_obj.nombre_tipo)
        if selected["tipo"]:
            selected_tipo = next((t for t in tipos if str(t.id) == selected["tipo"]), None)
    selected["categoria_labels"] = categoria_labels
    selected["tipo_labels"] = tipo_labels

    budget_options = [
        {"label": "Hasta $400.000", "value": "0-400000"},
        {"label": "$400.000 - $800.000", "value": "400000-800000"},
        {"label": "$800.000 - $1.200.000", "value": "800000-1200000"},
        {"label": "$1.200.000 o mas", "value": "1200000-0"},
    ]

    def _build_sort_url(option: str) -> str:
        params = request.GET.copy()
        params["sort"] = option
        query = params.urlencode()
        return f"?{query}" if query else f"?sort={option}"

    sort_urls = {
        "match": _build_sort_url("match"),
        "value": _build_sort_url("value"),
        "quiet": _build_sort_url("quiet"),
        "portable": _build_sort_url("portable"),
    }

    active_spec_badges = [] if compat_results else _format_spec_filter_badges(raw_spec_params)
    clear_spec_filters_url = reverse("reco_explore")
    show_clear_filters = bool(raw_spec_params) or bool(selected["marca"]) or bool(selected["categorias"]) or bool(selected["tipos"])
    if show_clear_filters:
        params_for_clear = request.GET.copy()
        for key in SPEC_FILTER_QUERY_KEYS:
            params_for_clear.pop(key, None)
        params_for_clear.pop("categoria", None)
        params_for_clear.pop("tipo", None)
        params_for_clear.pop("marca", None)
        remaining = params_for_clear.urlencode()
        if remaining:
            clear_spec_filters_url = f"{reverse('reco_explore')}?{remaining}"
    if selected["categoria_labels"] and not compat_results:
        for label in selected["categoria_labels"]:
            active_spec_badges.append(f"Categoria {label}")
    if selected["tipo_labels"] and not compat_results:
        for label in selected["tipo_labels"]:
            active_spec_badges.append(f"Tipo {label}")
    if selected["marca"] and not compat_results:
        active_spec_badges.append(f"Marca {selected['marca']}")

    context = {
        "categories": categorias,
        "types": tipos,
        "budget_options": budget_options,
        "selected_filters": selected,
        "products": products,
        "selected_categoria": selected_categoria,
        "selected_tipo": selected_tipo,
        "compat_notice": compat_notice,
        "compat_notice_level": compat_notice_level,
        "compat_results": compat_results,
        "active_spec_filters": active_spec_badges,
        "sort_urls": sort_urls,
        "clear_spec_filters_url": clear_spec_filters_url,
        "preference_context": preference_context,
    }
    return render(request, "lab/reco_explore.html", context)


def _for_whom_text(product: Producto) -> str:
    tipo = product.tipo_producto.nombre_tipo if product.tipo_producto_id else ""
    categoria = product.categoria_producto.nombre_categoria if product.categoria_producto_id else ""
    if "Notebook" in tipo or "Laptop" in tipo:
        return "Ideal para usuarios que combinan sesiones creativas y movilidad semanal."
    if "Procesador" in tipo:
        return "Pensado para entusiastas que buscan renovar builds sin comprometer compatibilidad."
    if "Tarjeta" in tipo:
        return "Apropiado para jugadores y creadores que necesitan mas fps sin cambiar todo el equipo."
    if categoria:
        return f"Enfocado en perfiles que priorizan {categoria.lower()} con contexto tecnico claro."
    return "Dirigido a quienes prefieren recomendaciones explicadas antes de comprar."


def _why_text(product: Producto, min_price: Decimal | None, avg_rating: float) -> str:
    tipo = product.tipo_producto.nombre_tipo if product.tipo_producto_id else ""
    price_display = _format_currency(min_price)
    if avg_rating:
        return f"Balancea rendimiento y experiencia real con promedio {avg_rating:.1f}/5 y referencias controladas."
    if price_display:
        return f"Ofrece referencias desde {price_display}, permitiendo planificar la inversion con trade-offs claros."
    if "Notebook" in tipo or "Laptop" in tipo:
        return "Combina componentes actuales con chasis probado; destaca en sesiones multitarea."
    return "Resume specs relevantes y trade-offs para decidir sin lenguaje comercial."


def _detail_summary(product_payload: Dict[str, object]) -> List[str]:
    bullets: List[str] = []
    avg_rating = product_payload["avg_rating"]
    review_count = product_payload["review_count"]
    if avg_rating and review_count:
        bullets.append(f"Promedio {avg_rating:.1f}/5 basado en {review_count} reseñas.")
    else:
        bullets.append("Aun recopilamos reseñas verificadas; revisa compatibilidad antes de decidir.")
    price_display = product_payload.get("min_price_display")
    if price_display:
        bullets.append(f"Referencias de tiendas desde {price_display}, sin patrocinio.")
    else:
        bullets.append("Precio de referencia pendiente; valida directamente con tiendas.")
    tradeoffs = product_payload["tradeoffs"]
    if tradeoffs:
        bullets.append(f"Trade-off destacado: {tradeoffs[0]}.")
    else:
        bullets.append("Trade-offs equilibrados; revisa alternativas cercanas.")
    return bullets[:3]


# ===========================
# Detalle, guías y preferencias
# ===========================
def reco_detail(request):
    product_id = request.GET.get("id")
    if not product_id or not product_id.isdigit():
        raise Http404("Producto no encontrado.")
    favorite_ids = _favorite_ids_for(request.user)

    spec_prefetch = Prefetch(
        "especificacionproducto_set",
        queryset=EspecificacionProducto.objects.all(),
        to_attr="prefetched_specs",
    )
    reference_prefetch = Prefetch(
        "referencias",
        queryset=ProductReference.objects.all(),
        to_attr="prefetched_references",
    )
    review_prefetch = Prefetch(
        "reviews",
        queryset=ProductReview.objects.select_related("user").order_by("-created_at"),
        to_attr="prefetched_reviews",
    )

    product_qs = (
        Producto.objects.filter(pk=int(product_id), is_active=True)
        .select_related("marca_producto", "categoria_producto", "tipo_producto")
        .prefetch_related(spec_prefetch, reference_prefetch, review_prefetch)
        .annotate(
            avg_rating=Avg("reviews__rating"),
            review_count=Count("reviews", distinct=True),
            min_price=Min("referencias__precio"),
            max_price=Coalesce(
                Max("referencias__precio"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            stock_total=Coalesce(
                Sum("referencias__stock"),
                Value(0),
                output_field=IntegerField(),
            ),
            view_count=Count("productovisto", distinct=True),
        )
    )
    product = get_object_or_404(product_qs)
    specs = _build_spec_map(product)
    base_signature = _build_similarity_signature(product, specs)
    if request.user.is_authenticated:
        _register_user_view(request.user, product, product.min_price)
    preference_context = _user_preference_context(request.user)
    payload = _product_payload(product)
    payload["is_favorite"] = product.id in favorite_ids
    _apply_preference_match(payload, preference_context)
    specs = payload.pop("_spec_map", specs)
    payload["criteria"] = [
        {"label": "Gama", "value": payload["criteria"][0]["value"]},
        {"label": "Disipación", "value": payload["criteria"][1]["value"]},
        {"label": "Portabilidad", "value": payload["criteria"][2]["value"]},
        {"label": "Temperaturas", "value": payload["criteria"][3]["value"]},
    ]
    payload["summary_bullets"] = _detail_summary(payload)
    payload["for_whom"] = _for_whom_text(product)
    payload["why"] = _why_text(product, product.min_price, float(product.avg_rating or 0.0))
    payload["key_specs"] = _key_specs(product, specs)
    payload["image"] = payload["image"] or None

    references = sorted(
        getattr(product, "prefetched_references", []),
        key=lambda ref: ref.precio or Decimal("0"),
    )
    stores = []
    for reference in references:
        stores.append(
            {
                "name": reference.nombre_fuente,
                "price": _format_currency(reference.precio),
                "url": reference.url_fuente,
                "note": reference.nota,
                "reference_id": reference.id,
            }
        )

    reviews = []
    for review in getattr(product, "prefetched_reviews", []):
        reviews.append(
            {
                "user": review.user.username if review.user_id else "Anonimo",
                "rating": review.rating,
                "date": review.created_at.strftime("%d-%m-%Y"),
                "comment": review.comment,
            }
        )

    user_review = None
    if request.user.is_authenticated:
        user_review = ProductReview.objects.filter(producto=product, user=request.user).first()
    user_has_review = bool(user_review)

    show_review_form = False
    if request.method == "POST":
        if not request.user.is_authenticated:
            login_url = f"{reverse('login')}?next={request.get_full_path()}"
            return redirect(login_url)
        form_review = ProductReviewForm(request.POST)
        show_review_form = True
        if form_review.is_valid():
            ProductReview.objects.update_or_create(
                producto=product,
                user=request.user,
                defaults={
                    "rating": form_review.cleaned_data["rating"],
                    "comment": form_review.cleaned_data["comment"],
                },
            )
            messages.success(request, "Tu reseña fue guardada.")
            detail_url = f"{reverse('reco_detail')}?id={product.id}#reco-reviews"
            return redirect(detail_url)
        if not user_has_review and ProductReview.objects.filter(producto=product, user=request.user).exists():
            user_has_review = True
    else:
        initial = {}
        if user_has_review and user_review:
            initial = {"rating": user_review.rating, "comment": user_review.comment}
        form_review = ProductReviewForm(initial=initial)
        show_review_form = False
    if request.method != "POST":
        form_review_errors = None
    else:
        form_review_errors = form_review.errors if form_review else None

    alternatives = _build_alternatives_payload(product, base_signature)
    similar_alts = alternatives["similar"]
    compatible_alts = alternatives["compatible"]

    similar_more_link = reverse("reco_explore")
    if product.categoria_producto_id or product.tipo_producto_id:
        params = []
        if product.categoria_producto_id:
            params.append(f"categoria={product.categoria_producto_id}")
        if product.tipo_producto_id:
            params.append(f"tipo={product.tipo_producto_id}")
        similar_more_link = f"{reverse('reco_explore')}?{'&'.join(params)}"

    compatible_more_link = reverse("reco_explore")
    if compatible_alts:
        compatible_more_link = f"{reverse('reco_explore')}?compat_with={product.id}"

    compatibility_story: List[Dict[str, object]] = []
    for alt in compatible_alts[:3]:
        points = alt.get("compat_points") if isinstance(alt, dict) else None
        if not points:
            continue
        compatibility_story.append(
            {
                "name": alt["name"],
                "type": alt["type"],
                "matches": points,
                "detail_url": alt["detail_url"],
            }
        )
    if not compatibility_story:
        fallback_partners = _compatibility_partners(product, specs, limit=2)
        for partner in fallback_partners:
            compatibility_story.append(
                {
                    "name": partner["name"],
                    "type": partner["type"],
                    "matches": partner.get("matches", []),
                    "detail_url": partner["detail_url"],
                }
            )
            if len(compatibility_story) >= 2:
                break

    context = {
        "product": payload,
        "stores": stores,
        "reviews": reviews,
        "alternatives_similar": similar_alts,
        "alternatives_compatible": compatible_alts,
        "alternatives_similar_link": similar_more_link,
        "alternatives_compatible_link": compatible_more_link,
        "compatibility_story": compatibility_story,
        "form_review": form_review,
        "show_review_form": show_review_form,
        "user_has_review": user_has_review,
        "preference_notes": preference_context.get("notes", ""),
        "preference_context": preference_context,
    }
    return render(request, "lab/reco_detail.html", context)


_GUIDE_BLUEPRINTS = {   'diseno': {   'checklist': [   'Busca resoluciones 2K+ (2360x1640) y cobertura sRGB/AdobeRGB.',
                                   'GPUs de 8 GB GDDR6 con bus PCIe 4.0 x8 aseguran aceleracion en '
                                   'render.',
                                   'Placas con multiples DisplayPort/HDMI y headers ARGB facilitan '
                                   'estaciones calibradas.'],
                  'filters': [   {'label': 'Pantalla 2K+', 'params': {'display_resolution': '2k'}},
                                 {'label': 'GPU 8 GB', 'params': {'gpu_mem_min': '8'}},
                                 {   'label': 'Dual DisplayPort',
                                     'params': {'port_hint': 'displayport'}}],
                  'persona': 'Creativos que usan suites Adobe/Autodesk y exigen color consistente.',
                  'spec_focus': [   'Pantalla/Resolucion',
                                    'Memoria GPU',
                                    'Bus PCIe',
                                    'Salidas de video'],
                  'themes': ['Pantalla/resolucion', 'Memoria GPU', 'Salidas de video'],
                  'tradeoffs': [   'Pantallas de alta resolucion consumen mas bateria en '
                                   'tablets/notebooks.',
                                   'GPUs profesionales elevan TDP y requieren fuentes 700 W 80+ '
                                   'Bronze o superiores.']},
    'estudio': {   'checklist': [   'Notebooks/tablets con baterias >50 Wh y peso <1.5 kg.',
                                    'Pantallas FHD de 11-14 pulgadas equilibran consumo.',
                                    'Almacenamiento minimo de 256 GB para material de estudio.'],
                   'filters': [   {'label': 'Bateria 50 Wh+', 'params': {'battery_wh_min': '50'}},
                                  {'label': 'Peso < 1.5 kg', 'params': {'weight_max': '1500'}},
                                  {   'label': '256 GB de almacenamiento',
                                      'params': {'storage_min': '256'}}],
                   'persona': 'Estudiantes que priorizan autonomia, peso y conectividad sencilla.',
                   'spec_focus': ['Bateria (Wh)', 'Peso', 'Pantalla', 'Almacenamiento'],
                   'themes': ['Bateria', 'Peso', 'Almacenamiento minimo'],
                   'tradeoffs': [   'Tablets sin conectividad celular dependen del WiFi del '
                                    'campus.',
                                    'Chasis ultradelgados limitan ventilacion y upgrades.']},
    'gamer': {   'checklist': [   'Cruza memoria y bus de la GPU (8 GB GDDR6, PCIe 4.0 x8) con los '
                                  'slots de tu placa.',
                                  'Sincroniza CPU (frecuencia turbo y nucleos/hilos) con sockets '
                                  'LGA/AM4 para evitar cuellos de botella.',
                                  'Asegura fuentes de 650 W+ con conectores 6+2/8 pines para '
                                  'graficas actuales.'],
                 'filters': [   {'label': 'Bus PCIe 4.0', 'params': {'gpu_bus': 'pcie4'}},
                                {'label': 'Socket AM', 'params': {'socket_hint': 'AM'}},
                                {'label': 'Socket LGA', 'params': {'socket_hint': 'LGA'}},
                                {'label': 'Fuente 650W+', 'params': {'psu_w_min': '650'}}],
                 'persona': 'Jugadores que requieren fps estables y compatibilidad con monitores '
                            '144/240 Hz.',
                 'spec_focus': ['GPU Bus', 'Conectores 8 pines', 'Nucleos/Hilos', 'TDP'],
                 'themes': ['GPU y bus PCIe', 'Refrigeracion', 'Fuente dedicada'],
                 'tradeoffs': [   'Tarjetas con TDP alto elevan ruido y temperatura si el gabinete '
                                  'no respira bien.',
                                  'Placas con pocos headers RGB o slots M.2 limitan upgrades '
                                  'esteticos y de almacenamiento.']},
    'hogar': {   'checklist': [   'Mantente en 16 GB de RAM DDR4/DDR5 para multitarea familiar.',
                                  'Prefiere SSD SATA o NVMe para reducir tiempos de arranque y '
                                  'copias.',
                                  'Confirma que la fuente incluya conectores SATA/Molex para NAS y '
                                  'perifericos.'],
                 'filters': [   {'label': 'RAM >= 16 GB', 'params': {'ram_min': '16'}},
                                {'label': 'Solo SSD/NVMe', 'params': {'storage': 'ssd'}},
                                {'label': 'Puertos USB/RJ-45', 'params': {'port_hint': 'usb'}}],
                 'persona': 'Usuarios que combinan tareas de oficina ligera, clases en linea y uso '
                            'compartido.',
                 'spec_focus': ['RAM', 'Almacenamiento', 'Puertos', 'Potencia PSU'],
                 'themes': ['RAM base', 'SSD obligatorio', 'Conectores domesticos'],
                 'tradeoffs': [   'Gabinetes micro limitan bahias o ranuras M.2 para futuros '
                                  'upgrades.',
                                  'Fuentes genericas sin certificacion pueden fallar con UPS '
                                  'domesticos.']},
    'trabajo': {   'checklist': [   'Busca procesadores con al menos 6 P-cores y 12 hilos.',
                                    'Incluye SSD NVMe de 512 GB+ para datasets locales y backups '
                                    'rapidos.',
                                    'Elige notebooks/all-in-one con RJ-45 y multiples '
                                    'USB-C/DisplayPort.'],
                   'filters': [   {'label': '12 hilos o mas', 'params': {'threads_min': '12'}},
                                  {'label': 'RJ-45 + USB-C', 'params': {'port_hint': 'rj-45'}},
                                  {'label': 'SSD NVMe', 'params': {'storage': 'nvme'}}],
                   'persona': 'Profesionales que alternan Excel/PowerBI, videollamadas y edicion '
                              'ligera.',
                   'spec_focus': ['Nucleos/Hilos', 'RAM', 'SSD NVMe', 'Puertos RJ-45 / USB-C'],
                   'themes': ['CPU con P-cores', 'SSD NVMe', 'Red cableada'],
                   'tradeoffs': [   'Ultrabooks reducen puertos fisicos y dependen de hubs.',
                                    'All-in-one simplifican cableado pero encarecen upgrades de '
                                    'RAM/SSD.']}}

def _guide_payload(cat: CategoriaProducto) -> Dict[str, object]:
    key = cat.nombre_categoria.lower()
    blueprint = None
    for slug, data in _GUIDE_BLUEPRINTS.items():
        if slug in key:
            blueprint = data
            break
    if blueprint is None:
        blueprint = {
            "persona": _short_text(cat.descripcion_categoria, 120),
            "themes": ["Compatibilidad", "Budget", "Garantia"],
            "checklist": [
                "Define requisitos de uso antes de ver precios.",
                "Revisa trade-offs en terminos de ruido, calor y upgrades.",
                "Valida disponibilidad real en tiendas neutrales.",
            ],
            "tradeoffs": [
                "Productos economicos suelen sacrificar soporte.",
                "Componentes de alto rendimiento consumen mas energia.",
            ],
            "filters": ["categoria", "tipo_producto", "presupuesto"],
            "spec_focus": ["Compatibilidad", "Budget", "Garantia"],
        }
    explore_base = reverse("reco_explore")
    filter_links = []
    for filter_cfg in blueprint["filters"]:
        if isinstance(filter_cfg, dict):
            label = filter_cfg.get("label") or "Filtro sugerido"
            params = {"categoria": cat.id}
            params.update(filter_cfg.get("params", {}))
        else:
            label = str(filter_cfg).title()
            params = {"categoria": cat.id}
        filter_links.append(
            {
                "label": label,
                "url": f"{explore_base}?{urlencode(params, doseq=True)}",
                "params": params,
            }
        )
    return {
        "id": cat.id,
        "title": cat.nombre_categoria,
        "summary": _short_text(cat.descripcion_categoria, 180),
        "persona": blueprint["persona"],
        "themes": blueprint["themes"],
        "checklist": blueprint["checklist"],
        "tradeoffs": blueprint["tradeoffs"],
        "filters": filter_links,
        "spec_focus": blueprint.get("spec_focus", []),
        "cta_url": f"{explore_base}?categoria={cat.id}",
    }


def reco_guides(request):
    categorias = _categories_with_inventory().order_by("-prod_count", "nombre_categoria")[:8]
    cards = [_guide_payload(cat) for cat in categorias]

    selected_id = request.GET.get("categoria")
    selected_card = None
    if selected_id and selected_id.isdigit():
        selected_card = next((card for card in cards if card["id"] == int(selected_id)), None)
    if not selected_card and cards:
        selected_card = cards[0]

    context = {
        "selected_guide": selected_card,
        "guide_cards": cards,
    }
    return render(request, "lab/reco_guides.html", context)


@login_required
def reco_preferences(request):
    categorias = _categories_with_inventory().order_by("nombre_categoria")
    tipos = TipoProducto.objects.annotate(
        prod_count=Count("producto", filter=Q(producto__is_active=True))
    ).filter(prod_count__gt=0).order_by("nombre_tipo")

    budget_options = [
        {"label": "Hasta $400.000", "value": "0-400000"},
        {"label": "$400.000 - $800.000", "value": "400000-800000"},
        {"label": "$800.000 - $1.200.000", "value": "800000-1200000"},
        {"label": "$1.200.000 o mas", "value": "1200000-0"},
    ]

    if request.method == "POST":
        category_ids = [int(cid) for cid in request.POST.getlist("categorias") if cid.isdigit()]
        type_ids = [int(tid) for tid in request.POST.getlist("tipos") if tid.isdigit()]
        budget_value = request.POST.get("presupuesto") or ""
        notes = (request.POST.get("notas") or "").strip()

        PreferenciaUsuario.objects.filter(usuario=request.user).delete()
        entries: List[PreferenciaUsuario] = []
        for cat_id in category_ids:
            entries.append(PreferenciaUsuario(usuario=request.user, categoria_id=cat_id))
        for type_id in type_ids:
            entries.append(PreferenciaUsuario(usuario=request.user, tipo_producto_id=type_id))
        if entries:
            PreferenciaUsuario.objects.bulk_create(entries)

        profile, _ = Profile.objects.get_or_create(
            user=request.user,
            defaults={"profile_type": "admin" if request.user.is_staff else "usuario"},
        )
        min_budget, max_budget = _budget_limits_from_value(budget_value)
        profile.preferred_budget_min = min_budget
        profile.preferred_budget_max = max_budget
        profile.preference_notes = notes
        profile.preferred_budget_manual = True
        profile.save()

        messages.success(request, "Preferencias guardadas y sincronizadas con el radar.")
        return redirect("reco_preferences")

    preference_context = _user_preference_context(request.user)
    selected_categories = sorted(list(preference_context.get("category_ids") or []))
    selected_types = sorted(list(preference_context.get("type_ids") or []))
    selected_budget_value = preference_context.get("budget_value") or ""
    selected_notes = preference_context.get("notes", "")

    explore_params_list: List[tuple[str, str]] = []
    for cid in selected_categories:
        explore_params_list.append(("categoria", str(cid)))
    for tid in selected_types:
        explore_params_list.append(("tipo", str(tid)))
    if selected_budget_value:
        explore_params_list.append(("presupuesto", selected_budget_value))
    explore_url = reverse("reco_explore")
    if explore_params_list:
        explore_url = f"{explore_url}?{urlencode(explore_params_list, doseq=True)}"

    context = {
        "categories": categorias,
        "types": tipos,
        "budget_options": budget_options,
        "selected_categories": selected_categories,
        "selected_types": selected_types,
        "selected_budget": selected_budget_value,
        "selected_notes": selected_notes,
        "preference_context": preference_context,
        "explore_url": explore_url,
    }
    return render(request, "lab/reco_preferences.html", context)


@login_required
# ===========================
# Endpoints auxiliares / APIs
# ===========================
def reco_update_checklist(request):
    next_url = request.POST.get("next") or reverse("reco_preferences")
    if request.method != "POST":
        if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(next_url)
        return redirect("reco_preferences")

    notes = (request.POST.get("notes") or "").strip()
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={"profile_type": "admin" if request.user.is_staff else "usuario"},
    )
    profile.preference_notes = notes
    profile.save(update_fields=["preference_notes"])
    messages.success(request, "Actualizamos tu checklist personal.")

    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect("reco_preferences")


@login_required
def reco_radar(request):
    preference_context = _user_preference_context(request.user)
    radar_data = _collect_user_radar_data(request.user, days=14)
    view_stats = preference_context.get("view_stats", {})

    def _chart_payload(items: List[Dict[str, object]]):
        return {
            "labels": [item["label"] for item in items],
            "values": [item["count"] for item in items],
        }

    brand_chart = _chart_payload(view_stats.get("brands", []))
    type_chart = _chart_payload(view_stats.get("types", []))
    price_raw = view_stats.get("prices", [])
    total_price_views = sum(item["count"] for item in price_raw) or 1
    price_percentages = [round(entry["count"] * 100 / total_price_views, 1) for entry in price_raw]
    price_chart = {
        "labels": [
            f"{entry['label']} ({percent}%)"
            for entry, percent in zip(price_raw, price_percentages)
        ],
        "values": price_percentages,
    }

    brand_focus = None
    if brand_chart["labels"]:
        brand_focus = _brand_focus_payload(request.user, brand_chart["labels"][0], preference_context, limit=4)

    affinity_cards, affinity_params = _build_affinity_suggestions(request.user, preference_context, limit=4)
    affinity_explore_url = None
    if affinity_params:
        query = urlencode(affinity_params)
        affinity_explore_url = f"{reverse('reco_explore')}?{query}"

    context = {
        "preference_context": preference_context,
        "radar_data": radar_data,
        "brand_chart_data": brand_chart,
        "type_chart_data": type_chart,
        "price_chart_data": price_chart,
        "timeline_data": radar_data["timeline"],
        "affinity_cards": affinity_cards,
        "affinity_params": affinity_params,
        "affinity_explore_url": affinity_explore_url,
        "brand_focus": brand_focus or {},
    }
    return render(request, "lab/reco_radar.html", context)


@login_required
def reco_toggle_favorite(request):
    if request.method != "POST":
        return redirect("reco_saved")
    product_id = request.POST.get("product_id")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("reco_home")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = reverse("reco_home")
    if not product_id or not product_id.isdigit():
        messages.error(request, "No pudimos identificar el producto a guardar.")
        return redirect(next_url)
    product = (
        Producto.objects.filter(pk=int(product_id), is_active=True)
        .only("id")
        .first()
    )
    if not product:
        messages.error(request, "El producto seleccionado ya no esta disponible.")
        return redirect(next_url)
    mode = request.POST.get("mode", "add")
    if mode == "remove":
        removed, _ = ProductosFavoritos.objects.filter(usuario=request.user, producto=product).delete()
        if removed:
            messages.info(request, "Producto eliminado de tus guardados.")
        else:
            messages.info(request, "Este producto ya no estaba en tus guardados.")
    else:
        favorite, created = ProductosFavoritos.objects.get_or_create(
            usuario=request.user,
            producto=product,
        )
        if created:
            messages.success(request, "Guardamos este producto para que lo revises con calma.")
        else:
            messages.success(request, "Ya tenias este producto guardado.")
    return redirect(next_url)


@login_required
def reco_saved(request):
    if request.method == "POST":
        fav_id = request.POST.get("favorite_id")
        if fav_id and fav_id.isdigit():
            deleted, _ = ProductosFavoritos.objects.filter(id=int(fav_id), usuario=request.user).delete()
            if deleted:
                messages.success(request, "Producto eliminado de tus guardados.")
            return redirect("reco_saved")

    favoritos = list(
        ProductosFavoritos.objects.filter(usuario=request.user)
        .select_related("producto")
        .order_by("-id")
    )
    preference_context = _user_preference_context(request.user)
    product_ids = [fav.producto_id for fav in favoritos]
    products_by_id = {}
    raw_products = {}
    if product_ids:
        products = _base_product_queryset().filter(id__in=product_ids)
        for prod in products:
            raw_products[prod.id] = prod
            payload = _product_payload(prod)
            _apply_preference_match(payload, preference_context)
            products_by_id[prod.id] = payload

    saved_cards = []
    type_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    match_values: list[int] = []
    affinity_counters = {
        "category": {"matched": 0, "total": 0, "label": "categorias guardadas"},
        "type": {"matched": 0, "total": 0, "label": "formatos guardados"},
        "budget": {"matched": 0, "total": 0, "label": "rango de inversion"},
    }
    price_values: list[float] = []
    price_labels: list[str] = []

    for fav in favoritos:
        payload = products_by_id.get(fav.producto_id)
        if not payload:
            continue
        type_counter[payload.get("type")] += 1
        if payload.get("min_price_value") is not None:
            price_values.append(payload["min_price_value"])
            price_labels.append(payload.get("min_price_display") or "")
        for cat in payload.get("categories_meta", []):
            label = cat.get("name")
            if label:
                category_counter[label] += 1

        flags = payload.pop("_affinity_flags", {})

        mismatch_tags: List[str] = []
        if flags.get("category") is False:
            mismatch_tags.append("Fuera de tus categorias guardadas")
        if flags.get("type") is False:
            mismatch_tags.append("Formato distinto a lo que sigues")
        if flags.get("budget") is False:
            mismatch_tags.append("Por fuera de tu rango de inversion")
        saved_cards.append(
            {
                "favorite_id": fav.id,
                "product": payload,
                "note": "Revisa trade-offs y criterios actualizados antes de decidir.",
                "mismatch_tags": mismatch_tags,
            }
        )
        if payload.get("show_match") and payload.get("match") is not None:
            match_values.append(payload["match"])
        for key, info in affinity_counters.items():
            flag = flags.get(key)
            if flag is None:
                continue
            info["total"] += 1
            if flag:
                info["matched"] += 1

    insights = {
        "total": len(saved_cards),
        "avg_match": round(sum(match_values) / len(match_values), 1) if match_values else None,
        "top_type": None,
        "top_category": None,
        "price_range": None,
        "spotlights": [],
        "match_reason": None,
    }

    if type_counter:
        top_type, count = type_counter.most_common(1)[0]
        insights["top_type"] = {
            "label": top_type,
            "count": count,
        }
    if category_counter:
        top_cat, count = category_counter.most_common(1)[0]
        insights["top_category"] = {
            "label": top_cat,
            "count": count,
        }
    if price_values:
        low = min(price_values)
        high = max(price_values)
        low_fmt = _format_currency(Decimal(str(low)))
        high_fmt = _format_currency(Decimal(str(high)))
        label = low_fmt if low == high else f"{low_fmt} - {high_fmt}"
        insights["price_range"] = label

    if saved_cards:
        best_match_entry = max(saved_cards, key=lambda entry: entry["product"].get("match", 0))
        insights["spotlights"].append(
            {
                "title": "Mejor match",
                "product": best_match_entry["product"],
                "favorite_id": best_match_entry["favorite_id"],
            }
        )
        value_candidates = [
            entry for entry in saved_cards if entry["product"].get("min_price_value") is not None
        ]
        if value_candidates:
            best_value_entry = min(value_candidates, key=lambda entry: entry["product"]["min_price_value"])
            if not insights["spotlights"] or insights["spotlights"][0]["favorite_id"] != best_value_entry["favorite_id"]:
                insights["spotlights"].append(
                    {
                        "title": "Mejor valor",
                        "product": best_value_entry["product"],
                        "favorite_id": best_value_entry["favorite_id"],
                    }
                )

    mismatch_notes: List[str] = []
    for key, info in affinity_counters.items():
        if info["total"] and info["matched"] < info["total"]:
            diff = info["total"] - info["matched"]
            plural = "s" if diff != 1 else ""
            mismatch_notes.append(f"{diff} guardado{plural} fuera de tus {info['label']}")
    if mismatch_notes:
        insights["match_reason"] = " / ".join(mismatch_notes)

    context = {
        "saved_cards": saved_cards,
        "saved_total": len(saved_cards),
        "saved_insights": insights,
    }
    return render(request, "lab/reco_saved.html", context)
def _brand_focus_payload(user, brand_name: str, pref_ctx: Dict[str, object], limit: int = 4) -> Dict[str, object]:
    payload = {"top_product": None, "less_viewed": []}
    if not user.is_authenticated or not brand_name:
        return payload
    seen = (
        ProductoVisto.objects.filter(usuario=user, producto__marca_producto__nombre_marca__iexact=brand_name)
        .values("producto_id")
        .annotate(views=Count("id"))
        .order_by("-views")
    )
    product_counts = {entry["producto_id"]: entry["views"] for entry in seen}
    if not product_counts:
        return payload

    product_qs = (
        Producto.objects.filter(id__in=product_counts.keys())
        .select_related("marca_producto", "categoria_producto", "tipo_producto")
        .annotate(
            avg_rating=Avg("reviews__rating"),
            review_count=Count("reviews", distinct=True),
            min_price=Min("referencias__precio"),
            max_price=Coalesce(
                Max("referencias__precio"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            stock_total=Coalesce(
                Sum("referencias__stock"),
                Value(0),
                output_field=IntegerField(),
            ),
            view_count=Count("productovisto", distinct=True),
        )
    )
    products_map = {prod.id: prod for prod in product_qs}
    sorted_ids = sorted(product_counts.items(), key=lambda pair: (-pair[1], -pair[0]))
    top_entry = sorted_ids[0]
    top_product = products_map.get(top_entry[0])
    if top_product:
        top_payload = _product_payload(top_product)
        _apply_preference_match(top_payload, pref_ctx)
        top_payload.pop("_spec_map", None)
        top_payload["view_count_user"] = top_entry[1]
        summary_text = top_payload.get("match_summary") or ""
        top_payload["match_summary_list"] = [item.strip() for item in summary_text.split(";") if item.strip()]
        payload["top_product"] = {
            "product": top_payload,
            "views": top_entry[1],
        }

    less_seen = sorted(sorted_ids[1:], key=lambda pair: (pair[1], pair[0]))
    for prod_id, view_count in less_seen[:limit]:
        product = products_map.get(prod_id)
        if not product:
            continue
        product_payload = _product_payload(product)
        _apply_preference_match(product_payload, pref_ctx)
        product_payload.pop("_spec_map", None)
        product_payload["view_count_user"] = view_count
        summary_text = product_payload.get("match_summary") or ""
        product_payload["match_summary_list"] = [item.strip() for item in summary_text.split(";") if item.strip()]
        payload["less_viewed"].append(product_payload)
    payload["less_viewed_total"] = len(less_seen)

    return payload
    mismatch_notes: List[str] = []
    for key, info in affinity_counters.items():
        if info["total"] and info["matched"] < info["total"]:
            diff = info["total"] - info["matched"]
            plural = "s" if diff != 1 else ""
            mismatch_notes.append(f"{diff} guardado{plural} fuera de tus {info['label']}")
    if mismatch_notes:
        insights["match_reason"] = " / ".join(mismatch_notes)
