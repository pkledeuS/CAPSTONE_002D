import re
import unicodedata
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Tuple

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, DecimalField, IntegerField, Max, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import (
    CategoriaProducto,
    EspecificacionProducto,
    Producto,
    ProductReview,
    PreferenciaUsuario,
    ProductosFavoritos,
    TiendaProducto,
    TipoProducto,
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
        "detail_url": card["detail_url"],
        "summary": summary,
        "type_highlights": card["type_profile"]["highlights"][:2],
        "type_id": card["type_id"],
        "category_id": card["category_id"],
        "type": card["type"],
        "compat_points": compat_points or [],
    }


def _build_alternatives_payload(product: Producto, base_signature: Dict[str, str]) -> Dict[str, List[Dict[str, object]]]:
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
        )
        .annotate(
            avg_rating=Avg("reviews__rating"),
            review_count=Count("reviews", distinct=True),
            min_price=Min("tiendaproducto__precio"),
            max_price=Coalesce(
                Max("tiendaproducto__precio"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            stock_total=Coalesce(
                Sum("tiendaproducto__stock"),
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
        "reasons": _product_reasons(product, min_price, avg_rating, review_count),
        "tradeoffs": _product_tradeoffs(min_price, review_count, stock_total),
        "criteria": criteria,
        "min_price_display": _format_currency(min_price),
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


def _build_home_compatibility_pairs(top_cards: List[Dict[str, object]], products_by_id: Dict[int, Producto]) -> List[Dict[str, object]]:
    pairs: List[Dict[str, object]] = []
    for card in top_cards:
        product = products_by_id.get(card["id"])
        if not product:
            continue
        specs = card.get("_spec_map") or _build_spec_map(product)
        partners = _compatibility_partners(product, specs, limit=2)
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
                },
                "partners": partners,
                "focus_points": focus_points,
                "cta": f"{reverse('reco_explore')}?compat_with={card['id']}",
            }
        )
        if len(pairs) >= 3:
            break
    return pairs


def reco_home(request):
    categorias = _categories_with_inventory().order_by("-prod_count", "nombre_categoria")[:6]
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
        product_cards.append(payload)
        products_by_id[prod.id] = prod
    product_cards.sort(key=lambda p: (p["sort_match"], p["sort_value"]))
    top_recommendations = _select_top_recommendations(product_cards, limit=6, per_type=2)
    compatibility_pairs = _build_home_compatibility_pairs(top_recommendations, products_by_id)
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
                queryset = queryset.filter(tiendaproducto__precio__gte=low)
            if high is not None:
                queryset = queryset.filter(tiendaproducto__precio__lte=high)
        except ValueError:
            pass
    if search:
        queryset = queryset.filter(
            Q(nombre_producto__icontains=search) |
            Q(modelo_producto__icontains=search) |
            Q(descripcion_producto__icontains=search)
        )
    return queryset


def reco_explore(request):
    categorias = _categories_with_inventory().order_by("nombre_categoria")
    tipos = TipoProducto.objects.annotate(
        prod_count=Count("producto", filter=Q(producto__is_active=True))
    ).filter(prod_count__gt=0).order_by("nombre_tipo")

    compat_with = request.GET.get("compat_with")
    compat_source = None
    compat_notice = None
    compat_notice_level = "info"
    compat_results = False
    products: List[Dict[str, object]] = []

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
                products = [_product_payload(prod) for prod in compat_products]
                compat_notice = f"Mostrando productos compatibles con {compat_source.nombre_producto}"
                compat_results = True
            else:
                compat_notice = _compatibility_empty_notice(compat_source)
                compat_notice_level = "warning"

    if not products:
        products_qs = _apply_filters(request, _base_product_queryset())
        products = [_product_payload(prod) for prod in products_qs[:50]]

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

    spec_prefetch = Prefetch(
        "especificacionproducto_set",
        queryset=EspecificacionProducto.objects.all(),
        to_attr="prefetched_specs",
    )
    store_prefetch = Prefetch(
        "tiendaproducto_set",
        queryset=TiendaProducto.objects.select_related("tienda"),
        to_attr="prefetched_listings",
    )
    review_prefetch = Prefetch(
        "reviews",
        queryset=ProductReview.objects.select_related("user").order_by("-created_at"),
        to_attr="prefetched_reviews",
    )

    product_qs = (
        Producto.objects.filter(pk=int(product_id), is_active=True)
        .select_related("marca_producto", "categoria_producto", "tipo_producto")
        .prefetch_related(spec_prefetch, store_prefetch, review_prefetch)
        .annotate(
            avg_rating=Avg("reviews__rating"),
            review_count=Count("reviews", distinct=True),
            min_price=Min("tiendaproducto__precio"),
            max_price=Coalesce(
                Max("tiendaproducto__precio"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            stock_total=Coalesce(
                Sum("tiendaproducto__stock"),
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

    listings = getattr(product, "prefetched_listings", [])
    stores = []
    for listing in listings:
        stores.append(
            {
                "name": listing.tienda.nombre_tienda,
                "price": _format_currency(listing.precio),
                "url": listing.url_externa,
                "note": listing.nota_tienda,
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


_GUIDE_BLUEPRINTS = {
    "hogar": {
        "persona": "Usuarios que mezclan tareas de oficina ligera, clases en linea y uso familiar.",
        "themes": ["Consumo energético", "Conectividad doméstica", "Silencio"],
        "checklist": [
            "Prioriza almacenamiento de alta capacidad (1 TB NVMe o NVMe + HDD).",
            "Verifica WiFi 6/6E o ethernet estable y puertos frontales accesibles.",
            "Evalúa ruido total (chasis/ventiladores) si estará en espacios compartidos.",
        ],
        "tradeoffs": [
            "Equipos compactos y AIO limitan opciones de actualización.",
            "HDD ofrece más capacidad pero menor velocidad que NVMe."
        ],
        "filters": ["categoria", "tipo_producto", "presupuesto", "silencio", "almacenamiento"]
    },
    "gamer": {
        "persona": "Jugadores que requieren fps estables y compatibilidad con perifericos competitivos.",
        "themes": ["Rendimiento sostenido", "Refrigeracion", "Espacio en gabinete"],
        "checklist": [
            "Alinea GPU con tu resolución/Hz objetivo (1080p/1440p/4K).",
            "Asegura fuente con potencia y conectores PCIe suficientes.",
            "Verifica airflow del chasis y altura/longitud de la GPU.",
            "En notebooks gamer: revisa TGP real de la dGPU y sistema térmico."
        ],
        "tradeoffs": [
            "Chasis muy estéticos suelen sacrificar airflow.",
            "RAM de alta frecuencia puede implicar latencias mayores si no se ajusta bien."
        ],
        "filters": ["tipo_producto", "rendimiento", "compatibilidad_gpu", "presupuesto", "display_hz"]
    },
    "trabajo": {
        "persona": "Profesionales que alternan software de productividad con videollamadas y edicion ligera.",
        "themes": ["Confiabilidad", "Autonomia", "Conectividad"],
        "checklist": [
            "Prioriza 16-32 GB de RAM y SSD NVMe para respuesta fluida.",
            "Revisa calidad de webcam/mic y conectividad (USB-C/Thunderbolt, HDMI, LAN).",
        ],
        "tradeoffs": [
            "Más portabilidad suele significar menos puertos físicos.",
            "AIO simplifica la mesa pero reduce posibilidades de upgrade."
        ],
        "filters": ["tipo_producto", "ram", "almacenamiento", "puertos", "bateria"]
    },
    "estudio": {
        "persona": "Estudiantes que necesitan autonomia, peso reducido y resistencia.",
        "themes": ["Bateria", "Durabilidad", "Seguridad"],
        "checklist": [
            "Prioriza batería real alta (Wh) y carga por USB-C si es posible.",
            "Confirma 16 GB RAM y 512 GB NVMe mínimo para trabajos y proyectos.",
            "Valora chasis resistente (MIL-STD) y teclado cómodo para escribir."
        ],
        "tradeoffs": [
            "2-en-1 ganan versatilidad pero pierden algunos puertos.",
            "Pantallas táctiles reflejan más en exteriores."
        ],
        "filters": ["peso", "bateria", "puertos", "ram", "almacenamiento"]
    },
    "diseno": {
        "persona": "Ilustradores y creativos que usan tabletas gráficas (con o sin pantalla) y requieren precisión y color fiable.",
        "themes": ["Superficie y precisión", "Conectividad y drivers", "Ergonomía/soporte"],
        "checklist": [
            "Verifica compatibilidad de drivers con tu SO y apps (Adobe/Autodesk/Clip Studio).",
            "Confirma tipo de conexión: USB-C con DP Alt (1 cable) o HDMI+USB (3 en 1) para pen displays.",
            "Prioriza 8192 niveles de presión, buen RPS y soporte de inclinación (tilt).",
            "Si tiene pantalla: pide laminado, bajo parallax y cobertura sRGB/AdobeRGB certificada.",
            "Asegura stand/soporte ajustable o VESA para sesiones largas."
        ],
        "tradeoffs": [
            "Pantallas laminadas y alta cobertura de color aumentan costo.",
            "Superficies con textura tipo papel gastan puntas más rápido.",
            "Pen displays grandes requieren más espacio y potencia/ado de energía."
        ],
        "filters": ["tipo_tableta", "tamano", "resolucion", "cobertura_color", "conexiones", "presupuesto"]
    },
}

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
    return {
        "id": cat.id,
        "title": cat.nombre_categoria,
        "summary": _short_text(cat.descripcion_categoria, 180),
        "persona": blueprint["persona"],
        "themes": blueprint["themes"],
        "checklist": blueprint["checklist"],
        "tradeoffs": blueprint["tradeoffs"],
        "filters": blueprint["filters"],
        "spec_focus": blueprint.get("spec_focus", []),
        "cta_url": f"{reverse('reco_explore')}?categoria={cat.id}",
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
def reco_saved(request):
    favoritos = list(
        ProductosFavoritos.objects.filter(usuario=request.user)
        .select_related("producto")
        .order_by("-id")
    )
    product_ids = [fav.producto_id for fav in favoritos]
    products_by_id = {}
    if product_ids:
        products = _base_product_queryset().filter(id__in=product_ids)
        products_by_id = {prod.id: _product_payload(prod) for prod in products}

    saved_cards = []
    for fav in favoritos:
        payload = products_by_id.get(fav.producto_id)
        if not payload:
            continue
        saved_cards.append(
            {
                "product": payload,
                "note": "Revisa trade-offs y criterios actualizados antes de decidir.",
            }
        )

    context = {
        "saved_cards": saved_cards,
        "saved_total": len(saved_cards),
    }
    return render(request, "lab/reco_saved.html", context)
