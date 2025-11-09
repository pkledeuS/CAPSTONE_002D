import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Dict, List, Tuple
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, DecimalField, IntegerField, Max, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .models import (
    CategoriaProducto,
    EspecificacionProducto,
    Producto,
    ProductReference,
    ProductReview,
    PreferenciaUsuario,
    ProductosFavoritos,
    TipoProducto,
    Profile,
)
from .forms import ProductReviewForm
from .views import SPEC_CANON, SPEC_TEMPLATES, _norm_key


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

    if category_ids:
        categories = list(
            CategoriaProducto.objects.filter(id__in=category_ids)
            .values("id", "nombre_categoria")
            .order_by("nombre_categoria")
        )
        context["categories"] = categories
        context["category_ids"] = {cat["id"] for cat in categories}
    if type_ids:
        types = list(
            TipoProducto.objects.filter(id__in=type_ids)
            .values("id", "nombre_tipo")
            .order_by("nombre_tipo")
        )
        context["types"] = types
        context["type_ids"] = {tipo["id"] for tipo in types}

    profile = Profile.objects.filter(user=user).first()
    if profile:
        context["budget_min"] = profile.preferred_budget_min
        context["budget_max"] = profile.preferred_budget_max if profile.preferred_budget_max else None
        context["budget_label"] = _format_budget_label(profile.preferred_budget_min, profile.preferred_budget_max)
        context["notes"] = profile.preference_notes or ""

    context["has_prefs"] = bool(context["categories"] or context["types"] or context["budget_label"] or context["notes"])
    return context


def _apply_preference_match(payload: Dict[str, object], pref_ctx: Dict[str, object]) -> None:
    if not pref_ctx or not pref_ctx.get("has_prefs"):
        payload["match_summary"] = None
        payload["sort_match"] = -payload.get("match", 0)
        return

    base_match = payload.get("match", 0)
    bonus = 0
    factors: List[str] = []
    category_label = None
    type_label = None
    budget_caption = None
    categories = pref_ctx.get("category_ids") or set()
    if categories:
        product_categories = set(payload.get("category_all_ids") or [])
        if product_categories & categories:
            bonus += 4
            category_label = next(
                (cat["nombre_categoria"] for cat in pref_ctx.get("categories", []) if cat["id"] in product_categories),
                None,
            )
            if category_label:
                factors.append(f"Categoria preferida: {category_label}")
        else:
            factors.append("Fuera de tus categorias principales")
            bonus -= 1

    types = pref_ctx.get("type_ids") or set()
    if types:
        if payload.get("type_id") in types:
            bonus += 3
            type_label = next(
                (tipo["nombre_tipo"] for tipo in pref_ctx.get("types", []) if tipo["id"] == payload.get("type_id")),
                None,
            )
            if type_label:
                factors.append(f"Formato que sigues: {type_label}")
        else:
            factors.append("Formato distinto a tus preferencias")

    min_budget = pref_ctx.get("budget_min")
    max_budget = pref_ctx.get("budget_max")
    price_value = payload.get("min_price_value")
    if price_value is not None and (min_budget or max_budget):
        within = True
        if min_budget and price_value < min_budget:
            within = False
        if max_budget and price_value > max_budget:
            within = False
        if within:
            bonus += 3
            factors.append("En tu rango de inversion")
        else:
            bonus -= 2
            factors.append("Revisa rango de inversion")
    elif min_budget or max_budget:
        factors.append("Sin precio para comparar con tu inversion")

    avg_rating = payload.get("avg_rating")
    review_count = payload.get("review_count", 0)
    if avg_rating and review_count:
        factors.append(f"Valorado {avg_rating:.1f}/5 ({review_count} reseñas)")

    payload["match"] = max(75, min(99, base_match + bonus))
    caption_parts: List[str] = []
    if category_label:
        caption_parts.append(category_label)
    if type_label:
        caption_parts.append(type_label)
    budget_label = pref_ctx.get("budget_label")
    if budget_label:
        caption_parts.append(budget_label)

    payload["match_summary"] = "; ".join(factors)
    payload["match_caption"] = " · ".join(caption_parts) if caption_parts else None
    payload["sort_match"] = -payload["match"]

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


def _silence_profile(product: Producto, specs: Dict[str, str], description: str) -> Tuple[str, int]:
    tipo = _norm(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "")
    if "memoria" in tipo or "almacenamiento" in tipo:
        return ("Silencioso", 0)
    if "fuente" in tipo:
        return ("Ventilador semi-passive", 1)
    tdp = _extract_tdp(specs, description)
    if "notebook" in tipo or "laptop" in tipo:
        return ("Balanceado", 1)
    if tdp is None:
        return ("Depende del armado", 2)
    if tdp <= 65:
        return ("Controlado", 1)
    if tdp <= 105:
        return (f"TDP {int(tdp)} W", 2)
    return (f"TDP {int(tdp)} W", 3)


def _portability_profile(product: Producto, specs: Dict[str, str], description: str) -> Tuple[str, int]:
    tipo = _norm(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "")
    if "tablet" in tipo:
        return ("Ultraligera", 0)
    if "notebook" in tipo or "laptop" in tipo:
        weight = _extract_weight(specs, description)
        if weight is not None:
            if weight <= 1.3:
                return ("Ultraligera", 0)
            if weight <= 1.8:
                return ("Ligera", 1)
            return (f"{weight:.1f} g", 2)
        return ("Portatil", 1)
    if "all-in-one" in tipo:
        return ("Movible", 2)
    return ("Estacionaria", 3)


def _thermal_profile(product: Producto, specs: Dict[str, str], description: str) -> Tuple[str, int]:
    tipo = _norm(product.tipo_producto.nombre_tipo if product.tipo_producto_id else "")
    tdp = _extract_tdp(specs, description)
    if tdp is not None:
        if tdp <= 65:
            return ("Eficiente", 0)
        if tdp <= 105:
            return (f"{int(tdp)} W", 1)
        return (f"{int(tdp)} W", 3)
    if "notebook" in tipo or "laptop" in tipo:
        return ("Perfil dual", 1)
    if "memoria" in tipo or "almacenamiento" in tipo:
        return ("Baja disipacion", 0)
    return ("Requiere flujo", 2)


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
    if avg_rating and review_count:
        return f"Promedio {avg_rating:.1f}/5 con {review_count} opiniones; contrasta con tu flujo antes de decidir."
    if min_price:
        price_display = _format_currency(min_price)
        if price_display:
            return f"Valida compatibilidad con tu equipo antes de invertir {price_display}."
    tipo = (tipo or "").lower()
    if "notebook" in tipo or "laptop" in tipo:
        return "Confirma peso, autonomia y puertos contra tus jornadas reales."
    return "Revisa especificaciones clave y compara alternativas cercanas."


def _build_criteria(product: Producto, specs: Dict[str, str], description: str) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    value_label, value_rank = _value_profile(product.min_price)
    silence_label, silence_rank = _silence_profile(product, specs, description)
    portability_label, portability_rank = _portability_profile(product, specs, description)
    thermal_label, thermal_rank = _thermal_profile(product, specs, description)
    criteria = [
        {"label": "Rend/$$", "value": value_label},
        {"label": "Silencio", "value": silence_label},
        {"label": "Portabilidad", "value": portability_label},
        {"label": "Termales", "value": thermal_label},
    ]
    ranks = {
        "value": value_rank,
        "quiet": silence_rank,
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
        add_metric("TDP", _spec_lookup(specs, "TDP"))
        add_metric("Proceso", _spec_lookup(specs, "Proceso de manufactura"))
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
        add_metric("Almacenamiento", _spec_lookup(specs, "Almacenamiento"))
        add_metric("Peso", _spec_lookup(specs, "Peso"))
        add_metric("SO", _spec_lookup(specs, "Sistema Operativo"))

    elif "tarjeta" in type_norm or "grafica" in type_norm or "gráfica" in type_norm:
        add_highlight(_spec_lookup(specs, "GPU"))
        add_highlight(_spec_lookup(specs, "Memoria"))
        add_highlight(_spec_lookup(specs, "Frecuencias core (base / boost)"))
        add_metric("Bus", _spec_lookup(specs, "Bus"))
        add_metric("Conectores", _spec_lookup(specs, "Conectores de poder"))
        add_metric("Refrigeracion", _spec_lookup(specs, "Refrigeracion"))
        add_metric("Largo", _spec_lookup(specs, "Largo"))

    elif "memoria" in type_norm:
        add_highlight(_spec_lookup(specs, "Capacidad"))
        add_highlight(_spec_lookup(specs, "Velocidad"))
        add_highlight(_spec_lookup(specs, "Latencia Cl (CAS)"))
        add_metric("Tipo", _spec_lookup(specs, "Tipo"))
        add_metric("Voltaje", _spec_lookup(specs, "Voltaje"))
        add_metric("Formato", _spec_lookup(specs, "Formato"))
        add_metric("ECC", _spec_lookup(specs, "Soporte ECC"))

    elif "fuente" in type_norm or "power" in type_norm:
        add_highlight(_spec_lookup(specs, "Potencia"))
        add_highlight(_spec_lookup(specs, "Certificacion"))
        modular = _spec_lookup(specs, "Modular")
        if modular:
            add_highlight(f"Modular: {modular}")
        add_metric("PFC activo", _spec_lookup(specs, "PFC activo"))
        add_metric("Linea 12V", _spec_lookup(specs, "Corriente en la linea de 12 V"))
        add_metric("Conectores", _spec_lookup(specs, "Conectores de energia"))
        add_metric("Tamano", _spec_lookup(specs, "Tamano"))

    elif "placa" in type_norm or "mother" in type_norm:
        socket = _spec_lookup(specs, "Socket")
        chipset = _spec_lookup(specs, "Chipset")
        if socket and chipset:
            add_highlight(f"{socket} · {chipset}")
        else:
            add_highlight(socket or chipset)
        add_highlight(_spec_lookup(specs, "Formato"))
        add_highlight(_spec_lookup(specs, "Soporte RGB"))
        add_metric("Slots RAM", _spec_lookup(specs, "Slots memorias"))
        add_metric("M.2", _spec_lookup(specs, "Conectores"))
        add_metric("Puertos traseros", _spec_lookup(specs, "Puertos"))
        add_metric("Alimentacion", _spec_lookup(specs, "Puertos de energia"))

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
        "rating_display": f"{avg_rating:.1f}/5" if review_count else None,
        "supports_compatibility": _supports_compatibility(type_name),
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
        .order_by("-avg_rating", "-review_count", "min_price")[:16]
    )
    product_cards = []
    products_by_id: Dict[int, Producto] = {}
    for prod in products_qs:
        payload = _product_payload(prod)
        payload["is_favorite"] = payload["id"] in favorite_ids
        _apply_preference_match(payload, preference_context)
        product_cards.append(payload)
        products_by_id[prod.id] = prod
    product_cards.sort(key=lambda p: (p["sort_match"], p["sort_value"]))
    top_recommendations = _select_top_recommendations(product_cards, limit=6, per_type=2)
    compatibility_pairs = _build_home_compatibility_pairs(
        top_recommendations,
        products_by_id,
        favorite_ids,
        preference_context,
    )
    for card in product_cards:
        card.pop("_spec_map", None)

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
    categoria_id = request.GET.get("categoria") or request.GET.get("perfil")
    tipo_id = request.GET.get("tipo")
    presupuesto = request.GET.get("presupuesto")
    search = request.GET.get("q")

    if categoria_id and categoria_id.isdigit():
        categoria_pk = int(categoria_id)
        queryset = queryset.filter(
            Q(categoria_producto_id=categoria_pk) | Q(categorias_extra__id=categoria_pk)
        ).distinct()
    if tipo_id and tipo_id.isdigit():
        queryset = queryset.filter(tipo_producto_id=int(tipo_id))
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
    spec_filters = _extract_spec_filters(request.GET)
    return queryset, spec_filters


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
    parsed_spec_filters: Dict[str, object] = {}
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
        products_qs, parsed_spec_filters = _apply_filters(request, _base_product_queryset())
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
            {"label": "Rend/$$", "value": payload["criteria"][0]["value"]},
            {"label": "Silencio", "value": payload["criteria"][1]["value"]},
            {"label": "Portabilidad", "value": payload["criteria"][2]["value"]},
            {"label": "Termales", "value": payload["criteria"][3]["value"]},
        ]

    selected = {
        "categoria": request.GET.get("categoria") or "",
        "tipo": request.GET.get("tipo") or "",
        "presupuesto": request.GET.get("presupuesto") or "",
        "sort": sort_param,
        "spec": raw_spec_params,
    }
    selected_categoria = None
    selected_tipo = None
    if selected["categoria"]:
        selected_categoria = next((c for c in categorias if str(c.id) == selected["categoria"]), None)
    if selected["tipo"]:
        selected_tipo = next((t for t in tipos if str(t.id) == selected["tipo"]), None)

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
    if raw_spec_params:
        params_for_clear = request.GET.copy()
        for key in SPEC_FILTER_QUERY_KEYS:
            params_for_clear.pop(key, None)
        remaining = params_for_clear.urlencode()
        if remaining:
            clear_spec_filters_url = f"{reverse('reco_explore')}?{remaining}"

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
    payload = _product_payload(product)
    payload["is_favorite"] = product.id in favorite_ids
    specs = payload.pop("_spec_map", specs)
    payload["criteria"] = [
        {"label": "Rend/$$", "value": payload["criteria"][0]["value"]},
        {"label": "Silencio", "value": payload["criteria"][1]["value"]},
        {"label": "Portabilidad", "value": payload["criteria"][2]["value"]},
        {"label": "Termales", "value": payload["criteria"][3]["value"]},
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


def reco_preferences(request):
    categorias = _categories_with_inventory().order_by("nombre_categoria")
    tipos = TipoProducto.objects.annotate(
        prod_count=Count("producto", filter=Q(producto__is_active=True))
    ).filter(prod_count__gt=0).order_by("nombre_tipo")

    selected_categoria = None
    selected_tipo = None
    if request.user.is_authenticated:
        pref = (
            PreferenciaUsuario.objects.filter(usuario=request.user)
            .select_related("categoria", "tipo_producto")
            .first()
        )
        if pref:
            selected_categoria = pref.categoria_id
            selected_tipo = pref.tipo_producto_id

    budget_options = [
        {"label": "Hasta $400.000", "value": "0-400000"},
        {"label": "$400.000 - $800.000", "value": "400000-800000"},
        {"label": "$800.000 - $1.200.000", "value": "800000-1200000"},
        {"label": "$1.200.000 o mas", "value": "1200000-0"},
    ]

    context = {
        "categories": categorias,
        "types": tipos,
        "budget_options": budget_options,
        "selected_categoria": selected_categoria,
        "selected_tipo": selected_tipo,
    }
    return render(request, "lab/reco_preferences.html", context)


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
    product_ids = [fav.producto_id for fav in favoritos]
    products_by_id = {}
    raw_products = {}
    if product_ids:
        products = _base_product_queryset().filter(id__in=product_ids)
        for prod in products:
            raw_products[prod.id] = prod
            products_by_id[prod.id] = _product_payload(prod)

    saved_cards = []
    type_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    match_values: list[int] = []
    price_values: list[float] = []
    price_labels: list[str] = []

    for fav in favoritos:
        payload = products_by_id.get(fav.producto_id)
        if not payload:
            continue
        type_counter[payload.get("type")] += 1
        if payload.get("match") is not None:
            match_values.append(payload["match"])
        if payload.get("min_price_value") is not None:
            price_values.append(payload["min_price_value"])
            price_labels.append(payload.get("min_price_display") or "")
        for cat in payload.get("categories_meta", []):
            label = cat.get("name")
            if label:
                category_counter[label] += 1

        saved_cards.append(
            {
                "favorite_id": fav.id,
                "product": payload,
                "note": "Revisa trade-offs y criterios actualizados antes de decidir.",
            }
        )

    insights = {
        "total": len(saved_cards),
        "avg_match": round(sum(match_values) / len(match_values), 1) if match_values else None,
        "top_type": None,
        "top_category": None,
        "price_range": None,
        "spotlights": [],
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

    context = {
        "saved_cards": saved_cards,
        "saved_total": len(saved_cards),
        "saved_insights": insights,
    }
    return render(request, "lab/reco_saved.html", context)
