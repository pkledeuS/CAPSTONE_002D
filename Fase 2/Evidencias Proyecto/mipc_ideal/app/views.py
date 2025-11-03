# app/views.py
from django.utils import timezone
import json
import re
from decimal import Decimal, DecimalException

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q, Min, Sum, Avg, Count, Max
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .forms import RegisterForm, ExistingProductOfferForm, ProductReviewForm, model_key
from .models import (
    Notificacion, Producto, CategoriaProducto, Reporte, TipoProducto,
    TipoServicio, PreferenciaUsuario, TiendaCategoria, Tienda, Profile,
    ChatSession, ChatTurn, EspecificacionProducto, TiendaProducto, MarcaProducto,
    ProductReview,
)
from .services.llm_provider import LLMClient
from .services.recommender import recommend_products, parse_requirements

# =========================
#   CONSTANTES DE CHAT
# =========================
OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_MODEL = "gemma3:4b"
SYSTEM_PROMPT = (
    "Asesor de compras de PC (español, conciso). Usa SOLO el contexto dado."
    " Prioriza: ajuste a lo pedido > rendimiento/precio > precio mín. > reseñas > stock."
    " No inventes modelos, precios ni especificaciones."
    " Usa NOMBRES CANÓNICOS de especificaciones; si falta algo del template, dilo."
    " En 'el mejor' o comparaciones, muestra criterios y pide 1 dato faltante. Máx. 4 oraciones."
)

# =========================
#   SPEC TEMPLATES + CANON
# =========================

# Plantillas de campos (orden deseado en UI) por TIPO de producto
SPEC_TEMPLATES = {
    'Procesador': [
        'Frecuencia', 'Frecuencia turbo máxima', 'Núcleos / hilos', 'Caché',
        'Socket', 'Núcleo', 'Proceso de manufactura', 'TDP', 'Cooler', 'Gráficos integrados'
    ],
    'Memoria RAM': [
        'Capacidad', 'Tipo', 'Velocidad', 'Formato', 'Voltaje',
        'Latencia CI (CAS)', 'Latencia Trcd', 'Latencia Trp', 'Latencia Tras',
        'Soporte ECC', 'Soporte full buffered'
    ],
    'Fuente de poder': [
        'Potencia', 'Certificación', 'Tamaño', 'PFC activo', 'Modular',
        'Corriente en la línea de 12V', 'Corriente en la línea de 5V', 'Corriente en la línea de 3.3V'
    ],
    'Tarjetas Gráficas': [
        'Fabricante', 'GPU', 'Memoria', 'Bus',
        'Frecuencias core (base / boost / OC)', 'Frecuencia memorias',
        'Núcleo', 'Perfil', 'Refrigeración', 'Slots', 'Largo',
        'Iluminación', '¿Backplate?', 'Conectores de poder', 'Puertos de video'
    ],
    'Placas madre': [
        'Socket', 'Chipset', 'Factor de forma', 'Fases VRM',
        'Slots RAM', 'Máx RAM', 'Slots M.2', 'Puertos SATA',
        'Wi-Fi', 'Bluetooth', 'LAN', 'Audio', 'Puertos traseros', 'BIOS/UEFI'
    ],
    'Notebook': [
        'Procesador', 'Núcleos', 'RAM', 'Pantalla', 'Resolución', 'Tasa de refresco',
        'Batería', 'Almacenamiento', 'Tarjeta de Video', 'Puertos',
        'Conectividad', 'Webcam', 'Teclado retroiluminado', 'Peso', 'SO', 'Idioma teclado'
    ],
    'Computador': [
        'Procesador', 'Núcleos', 'RAM', 'Almacenamiento', 'Tarjeta de Video',
        'Fuente de poder', 'Placa madre', 'Gabinete', 'Puertos', 'Conectividad', 'SO'
    ],
    'All-in-One': [
        'Procesador', 'Núcleos', 'RAM', 'Pantalla', 'Resolución',
        'Almacenamiento', 'Tarjeta de Video', 'Puertos', 'Conectividad',
        'Peso', 'SO', 'Periféricos inalámbricos'
    ],
    'Tablet': [
        'Part number', 'Pantalla', 'Resolución', 'Memoria interna', 'RAM',
        'Conectividad celular', 'Sistema operativo', 'Color', 'Peso', 'Dimensiones',
        'Almacenamiento externo', 'Batería', 'Cámara principal', 'Cámara frontal',
        'GPS', 'Bluetooth', 'Salida de audífonos', 'Procesador', 'CPU', 'GPU'
    ],
}

# --- Normalizador liviano de claves: minúsculas + sin tildes + espacios compactados
import unicodedata
def _norm_key(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = " ".join(s.split())
    return s

# Mapa de sinónimos -> nombre canónico (usar _norm_key en las claves)
SPEC_CANON = {
    # CPU
    _norm_key("frecuencia"): "Frecuencia",
    _norm_key("clock"): "Frecuencia",
    _norm_key("frecuencia turbo maxima"): "Frecuencia turbo máxima",
    _norm_key("boost"): "Frecuencia turbo máxima",
    _norm_key("núcleos / hilos"): "Núcleos / hilos",
    _norm_key("nucleos / hilos"): "Núcleos / hilos",
    _norm_key("cache"): "Caché",
    _norm_key("socket"): "Socket",
    _norm_key("tdp"): "TDP",
    _norm_key("graficos integrados"): "Gráficos integrados",
    _norm_key("litografia"): "Proceso de manufactura",
    _norm_key("proceso de manufactura"): "Proceso de manufactura",
    _norm_key("nucleo"): "Núcleo",

    # RAM
    _norm_key("capacidad"): "Capacidad",
    _norm_key("tipo"): "Tipo",
    _norm_key("velocidad"): "Velocidad",
    _norm_key("formato"): "Formato",
    _norm_key("voltaje"): "Voltaje",
    _norm_key("latencia cas"): "Latencia CI (CAS)",
    _norm_key("cl"): "Latencia CI (CAS)",
    _norm_key("cas latency"): "Latencia CI (CAS)",

    # PSU
    _norm_key("potencia"): "Potencia",
    _norm_key("certificacion"): "Certificación",
    _norm_key("80 plus"): "Certificación",
    _norm_key("80plus"): "Certificación",
    _norm_key("tamano"): "Tamaño",
    _norm_key("form factor"): "Tamaño",
    _norm_key("pfc activo"): "PFC activo",
    _norm_key("pfc"): "PFC activo",
    _norm_key("modular"): "Modular",
    _norm_key("semi modular"): "Modular",
    _norm_key("full modular"): "Modular",
    _norm_key("corriente 12v"): "Corriente en la línea de 12V",
    _norm_key("corriente 5v"): "Corriente en la línea de 5V",
    _norm_key("corriente 3.3v"): "Corriente en la línea de 3.3V",

    # GPU
    _norm_key("fabricante"): "Fabricante",
    _norm_key("gpu"): "GPU",
    _norm_key("memoria"): "Memoria",
    _norm_key("vram"): "Memoria",
    _norm_key("bus"): "Bus",
    _norm_key("frecuencias core (base / boost / oc)"): "Frecuencias core (base / boost / OC)",
    _norm_key("frecuencia memorias"): "Frecuencia memorias",
    _norm_key("refrigeracion"): "Refrigeración",
    _norm_key("slots"): "Slots",
    _norm_key("largo"): "Largo",
    _norm_key("iluminacion"): "Iluminación",
    _norm_key("backplate"): "¿Backplate?",
    _norm_key("conectores de poder"): "Conectores de poder",
    _norm_key("puertos de video"): "Puertos de video",
    _norm_key("salidas de video"): "Puertos de video",

    # Motherboard
    _norm_key("chipset"): "Chipset",
    _norm_key("factor de forma"): "Factor de forma",
    _norm_key("formato"): "Factor de forma",
    _norm_key("fases vrm"): "Fases VRM",
    _norm_key("etapas vrm"): "Fases VRM",
    _norm_key("slots ram"): "Slots RAM",
    _norm_key("max ram"): "Máx RAM",
    _norm_key("memoria maxima"): "Máx RAM",
    _norm_key("slots m.2"): "Slots M.2",
    _norm_key("puertos sata"): "Puertos SATA",
    _norm_key("wifi"): "Wi-Fi",
    _norm_key("bluetooth"): "Bluetooth",
    _norm_key("lan"): "LAN",
    _norm_key("audio"): "Audio",
    _norm_key("puertos traseros"): "Puertos traseros",
    _norm_key("bios"): "BIOS/UEFI",
    _norm_key("uefi"): "BIOS/UEFI",

    # Notebook / AIO / Computador
    _norm_key("procesador"): "Procesador",
    _norm_key("nucleos"): "Núcleos",
    _norm_key("ram"): "RAM",
    _norm_key("pantalla"): "Pantalla",
    _norm_key("resolucion"): "Resolución",
    _norm_key("tasa de refresco"): "Tasa de refresco",
    _norm_key("hz"): "Tasa de refresco",
    _norm_key("bateria"): "Batería",
    _norm_key("almacenamiento"): "Almacenamiento",
    _norm_key("tarjeta de video"): "Tarjeta de Video",
    _norm_key("gpu dedicada"): "Tarjeta de Video",
    _norm_key("puertos"): "Puertos",
    _norm_key("conectividad"): "Conectividad",
    _norm_key("webcam"): "Webcam",
    _norm_key("teclado retroiluminado"): "Teclado retroiluminado",
    _norm_key("peso"): "Peso",
    _norm_key("so"): "SO",
    _norm_key("idioma teclado"): "Idioma teclado",
    _norm_key("placa madre"): "Placa madre",
    _norm_key("gabinete"): "Gabinete",
    _norm_key("perifericos inalambricos"): "Periféricos inalámbricos",

    # Tablet
    _norm_key("part number"): "Part number",
    _norm_key("memoria interna"): "Memoria interna",
    _norm_key("conectividad celular"): "Conectividad celular",
    _norm_key("sistema operativo"): "Sistema operativo",
    _norm_key("almacenamiento externo"): "Almacenamiento externo",
    _norm_key("camara principal"): "Cámara principal",
    _norm_key("camara frontal"): "Cámara frontal",
    _norm_key("bluetooth"): "Bluetooth",
    _norm_key("gps"): "GPS",
    _norm_key("salida de audifonos"): "Salida de audífonos",
    _norm_key("salida de audífonos"): "Salida de audífonos",
}

def _canonize_spec_name(name: str) -> str:
    """
    Devuelve el nombre canónico de la especificación, si existe.
    - Insensible a mayúsculas y tildes.
    - Compacta espacios.
    - Si no hay mapeo, retorna el texto original (limpio).
    """
    raw = (name or "").strip()
    k = _norm_key(raw)
    return SPEC_CANON.get(k, raw)

def _typed_spec_template(tipo_nombre: str):
    return SPEC_TEMPLATES.get(tipo_nombre or "", [])

def _specs_canon_sorted(prod: Producto):
    """Devuelve (pairs, tipo_nombre) con nombres canónicos y orden del template."""
    tipo = prod.tipo_producto.nombre_tipo if prod.tipo_producto_id else ""
    template = _typed_spec_template(tipo)
    t_index = {n: i for i, n in enumerate(template)}

    raw = EspecificacionProducto.objects.filter(producto=prod)\
        .values_list("nombre_especificacion", "valor_especificacion")

    canon = {}
    for n, v in raw:
        cn = _canonize_spec_name(n)
        if cn not in canon:
            canon[cn] = v

    # Primero lo que está en la plantilla; luego extras (en el orden encontrado)
    ordered = [(n, canon.get(n, "—")) for n in template]
    for n, v in canon.items():
        if n not in t_index:
            ordered.append((n, v))
    return ordered, tipo

def _price_stats(prod: Producto):
    agg = TiendaProducto.objects.filter(producto=prod).aggregate(
        pmin=Min('precio'), pmax=Max('precio'), stock=Sum('stock')
    )
    if agg.get("pmax") is None:
        pvals = list(TiendaProducto.objects.filter(producto=prod).values_list("precio", flat=True))
        agg["pmax"] = max(pvals) if pvals else None
    return agg.get('pmin'), agg.get('pmax'), agg.get('stock') or 0

def _review_stats(prod: Producto):
    agg = prod.reviews.aggregate(ravg=Avg('rating'), rcnt=Count('id'))
    return (agg.get('ravg') or 0.0), (agg.get('rcnt') or 0)

# =========================
#   HELPERS GENERALES
# =========================
def _truncate_history(history, max_turns=8):
    if len(history) <= 1 + max_turns * 2:
        return history
    return [history[0]] + history[-(max_turns * 2):]

def _build_product_context(user_text: str) -> str:
    """Contexto factual (hasta 3 productos) con specs canónicas y ordenadas."""
    qs = Producto.objects.filter(
        models.Q(nombre_producto__icontains=user_text) |
        models.Q(modelo_producto__icontains=user_text)
    )[:3]
    if not qs:
        return ""
    bloques = []
    for p in qs:
        pairs, _ = _specs_canon_sorted(p)
        specs_txt = "; ".join(f"{n}: {v}" for n, v in pairs if v and v != "—") or "Sin especificaciones"
        bloques.append(
            f"- {p.nombre_producto} ({p.modelo_producto}) | "
            f"Marca: {p.marca_producto.nombre_marca if p.marca_producto_id else ''} | "
            f"Categoría: {p.categoria_producto.nombre_categoria if p.categoria_producto_id else ''} | "
            f"Tipo: {p.tipo_producto.nombre_tipo if p.tipo_producto_id else ''} | "
            f"Especificaciones: {specs_txt}"
        )
    return "CATÁLOGO (datos reales, úsalo estrictamente):\n" + "\n".join(bloques)

def _normalize_for_matching(text: str) -> str:
    t = text.lower()
    extra = []
    if any(w in t for w in ["notebook","notebooks","laptop","laptops","portatil","portátil","portatiles","portátiles"]):
        extra.append("Notebook")
    if any(w in t for w in ["procesador","procesadores","cpu","cpus","proce"]):
        extra.append("Procesador")
    if any(w in t for w in ["gamer","gaming","juego","juegos","videojuego","videojuegos"]):
        extra.append("Gamer")
    return text + (" " + " ".join(extra) if extra else "")

def _product_snippets(qs):
    snippets = []
    for p in qs:
        pairs, _ = _specs_canon_sorted(p)
        specs_txt = "; ".join(f"{n}: {v}" for n, v in pairs[:6]) if pairs else "Sin especificaciones"
        marca = p.marca_producto.nombre_marca if p.marca_producto_id else ""
        cat = p.categoria_producto.nombre_categoria if p.categoria_producto_id else ""
        tipo = p.tipo_producto.nombre_tipo if p.tipo_producto_id else ""
        snippets.append(
            f"{p.nombre_producto} ({p.modelo_producto}) — Marca: {marca} | "
            f"Categoría: {cat} | Tipo: {tipo} | {specs_txt}"
        )
    return snippets

def _product_labels(qs, limit=6):
    labels = []
    for p in qs[:limit]:
        if p.modelo_producto and p.modelo_producto.lower() not in (p.nombre_producto or "").lower():
            labels.append(f"{p.nombre_producto} ({p.modelo_producto})")
        else:
            labels.append(p.nombre_producto)
    return labels

def _get_or_create_chat_session(request):
    sid = request.session.get("chat_session_id")
    session = None
    if sid:
        try:
            session = ChatSession.objects.get(id=sid)
        except ChatSession.DoesNotExist:
            session = None
    if not session:
        session = ChatSession.objects.create(user=request.user)
        request.session["chat_session_id"] = session.id
    return session

def _get_sticky_filters(session_obj):
    meta = session_obj.metadata or {}
    sticky = meta.get("sticky_filters", {})
    return (
        sticky.get("categorias") or [],
        sticky.get("tipos") or [],
        sticky.get("budget")
    )

def _set_sticky_filters(session_obj, filtros_ids):
    meta = session_obj.metadata or {}
    meta["sticky_filters"] = {
        "categorias": filtros_ids.get("categorias", []),
        "tipos": filtros_ids.get("tipos", []),
        "budget": filtros_ids.get("budget"),
    }
    session_obj.metadata = meta
    session_obj.save(update_fields=["metadata"])

def _id_categoria(nombre: str):
    return CategoriaProducto.objects.filter(nombre_categoria__iexact=nombre)\
        .values_list("id", flat=True).first()

def _id_tipo(nombre: str):
    return TipoProducto.objects.filter(nombre_tipo__iexact=nombre)\
        .values_list("id", flat=True).first()

def _texto_contiene_gamer(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ["gamer","gaming","juego","juegos","videojuego","videojuegos"])

def _texto_contiene_notebook(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ["notebook","notebooks","laptop","laptops","portatil","portátil","portatiles","portátiles"])

# --- INTENCIONES & COMPARACIÓN ---
def _intent_smalltalk(text: str) -> bool:
    t = (text or "").lower()
    pats = [
        r"\b(hola|buenas|buen día|buenos días|buenas tardes|buenas noches)\b",
        r"\b(gracias|grx|ty|thank)\b",
        r"^ok$|^vale$|^sip$|^aja$|^claro$",
        r"\b(cómo estás|que tal|qué tal|todo bien)\b",
    ]
    return any(re.search(p, t) for p in pats)

def _intent_recommend(text: str) -> bool:
    t = (text or "").lower()
    triggers = [
        "gamer","gaming","trabajo","hogar","estudio","diseño","diseno",
        "notebook","laptop","portatil","portátil","pc","computador","computadora",
        "procesador","cpu","tarjeta","gpu","monitor","mouse","teclado","ssd","disco",
        "recomienda","recomiéndame","recomiendame","busco","quiero","necesito","mejor"
    ]
    return any(tok in t for tok in triggers)

def _normalize(s: str) -> str:
    return (s or "").strip().lower()

def _find_product_by_text(text: str):
    t = (text or "").strip()
    if not t:
        return None
    return Producto.objects.filter(
        Q(nombre_producto__icontains=t) | Q(modelo_producto__icontains=t)
    ).order_by("-vistas", "-fecha_creacion").first()

def _parse_compare_intent(msg: str):
    if not msg:
        return None, None
    quoted = re.findall(r'"([^"]{2,80})"', msg)
    if len(quoted) >= 2:
        return quoted[0], quoted[1]
    seps = [r"\bvs\b", r"\bversus\b", r"\bcontra\b", r"\bcon\b", r"\by\b"]
    for sep in seps:
        parts = re.split(sep, msg, flags=re.IGNORECASE)
        if len(parts) == 2:
            a, b = parts[0].strip(" :,-"), parts[1].strip(" :,-")
            if len(a) >= 2 and len(b) >= 2:
                return a, b
    m2 = re.search(r"entre\s+(.+?)\s+y\s+(.+)", msg, flags=re.IGNORECASE)
    if m2:
        a = m2.group(1).strip(" :,-")
        b = m2.group(2).strip(" :,-")
        if len(a) >= 2 and len(b) >= 2:
            return a, b
    return None, None

def _gather_specs(prod: Producto):
    pairs, tipo = _specs_canon_sorted(prod)
    specs = {n: v for n, v in pairs if v and v != "—"}
    meta = {
        "id": prod.id,
        "nombre": prod.nombre_producto,
        "modelo": prod.modelo_producto,
        "marca": prod.marca_producto.nombre_marca if prod.marca_producto_id else "",
        "categoria": prod.categoria_producto.nombre_categoria if prod.categoria_producto_id else "",
        "tipo": tipo,
    }
    return specs, meta

def _merge_spec_rows(specs_a: dict, specs_b: dict, order_hint: list[str]):
    keys = list(dict.fromkeys(order_hint + list(specs_a.keys()) + list(specs_b.keys())))
    rows = []
    for k in keys:
        rows.append({"name": k, "a": specs_a.get(k, "—"), "b": specs_b.get(k, "—")})
    return rows

def _fmt_money_clp(val):
    try:
        return "$" + f"{int(Decimal(val)):,}".replace(",", ".")
    except Exception:
        return ""

def _make_compare_payload(prod_a: Producto, prod_b: Producto, request):
    specs_a, meta_a = _gather_specs(prod_a)
    specs_b, meta_b = _gather_specs(prod_b)

    template_order = _typed_spec_template(meta_a["tipo"]) or _typed_spec_template(meta_b["tipo"]) or []
    rows_specs = _merge_spec_rows(specs_a, specs_b, template_order)

    pmin_a, pmax_a, stock_a = _price_stats(prod_a)
    pmin_b, pmax_b, stock_b = _price_stats(prod_b)
    ravg_a, rcnt_a = _review_stats(prod_a)
    ravg_b, rcnt_b = _review_stats(prod_b)

    def price_hdr(pmin, pmax):
        if pmin is None:
            return ""
        if pmax and pmax != pmin:
            return f"{_fmt_money_clp(pmin)}–{_fmt_money_clp(pmax)}"
        return _fmt_money_clp(pmin)

    top_rows = [
        {"name": "Precio (rango)", "a": price_hdr(pmin_a, pmax_a), "b": price_hdr(pmin_b, pmax_b)},
        {"name": "Rating (reseñas)", "a": f"{ravg_a:.1f}/5 ({rcnt_a})", "b": f"{ravg_b:.1f}/5 ({rcnt_b})"},
        {"name": "Stock total", "a": stock_a, "b": stock_b},
    ]
    rows = top_rows + rows_specs

    left_title = f'{meta_a["nombre"]} ({meta_a["modelo"]})' if meta_a["modelo"] and meta_a["modelo"].lower() not in (meta_a["nombre"] or "").lower() else meta_a["nombre"]
    right_title = f'{meta_b["nombre"]} ({meta_b["modelo"]})' if meta_b["modelo"] and meta_b["modelo"].lower() not in (meta_b["nombre"] or "").lower() else meta_b["nombre"]

    return {
        "left": {
            "titulo": left_title,
            "meta": " • ".join([x for x in [meta_a["marca"], meta_a["categoria"], meta_a["tipo"]] if x]),
            "url": request.build_absolute_uri(reverse("product_detail", args=[meta_a["id"]]))
        },
        "right": {
            "titulo": right_title,
            "meta": " • ".join([x for x in [meta_b["marca"], meta_b["categoria"], meta_b["tipo"]] if x]),
            "url": request.build_absolute_uri(reverse("product_detail", args=[meta_b["id"]]))
        },
        "rows": rows
    }

def _get_or_create_tienda_for_user(user):
    tienda = Tienda.objects.filter(user=user).first()
    if tienda:
        return tienda
    local = slugify(user.username) or f"user{user.id}"
    placeholder_email = f"{local}@placeholder.local"
    tienda = Tienda.objects.create(
        user=user,
        nombre_tienda=(user.get_full_name() or user.username).strip(),
        email_tienda=placeholder_email,
        descripcion_tienda="",
        direccion_tienda=""
    )
    return tienda

# ===== RERANKING INTELIGENTE =====
_GPU_TIERS = {
    r"rtx\s*4090": 10, r"rtx\s*4080": 9, r"rtx\s*4070": 8,
    r"rtx\s*4060": 7,  r"rtx\s*4050": 6, r"rtx\s*3060": 5,
    r"rtx\s*3050": 4,
    r"rx\s*7700": 7, r"rx\s*7600": 6, r"rx\s*6800": 6,
}
_CPU_TIERS = {
    r"i9-1[3-5]\d{3}": 9, r"i7-1[2-5]\d{3}": 8, r"i5-1[2-5]\d{3}": 6,
    r"i9-10\d{3}": 7, r"i7-10\d{3}": 6, r"i5-10\d{3}": 5,
    r"ryzen\s*9\s*7": 8, r"ryzen\s*7\s*7": 7, r"ryzen\s*5\s*7": 6,
    r"ryzen\s*9\s*5": 7, r"ryzen\s*7\s*5": 6, r"ryzen\s*5\s*5": 5,
}
_HZ_BONUS = [(240, 2.0), (165, 1.5), (144, 1.2)]

def _text_blob_for_product(p):
    parts = [p.nombre_producto or "", p.modelo_producto or ""]
    pairs, _ = _specs_canon_sorted(p)
    if pairs:
        parts.extend([f"{n} {v}" for n, v in pairs[:8]])
    return " ".join(str(x) for x in parts if x).lower()

def _match_weight(text, patterns_map):
    for pat, weight in patterns_map.items():
        if re.search(pat, text, flags=re.IGNORECASE):
            return weight
    return 0

def _hz_score(text):
    for hz, bonus in _HZ_BONUS:
        if re.search(rf"\b{hz}\s*hz\b", text, re.I) or re.search(rf"\b{hz}\b", text, re.I):
            return bonus
    return 0

def _price_range(qs):
    vals = [p.min_price for p in qs if getattr(p, "min_price", None) is not None]
    return (min(vals), max(vals)) if vals else (None, None)

def _rank_notebooks_for_gaming(qs):
    ranked = []
    pmin, pmax = _price_range(qs)
    for p in qs:
        t = _text_blob_for_product(p)
        gpu = _match_weight(t, _GPU_TIERS)
        cpu = _match_weight(t, _CPU_TIERS)
        hz  = _hz_score(t)

        price_boost = 0
        if getattr(p, "min_price", None) is not None and pmin is not None and pmax and pmax > pmin:
            try:
                price_norm = (Decimal(p.min_price) - Decimal(pmin)) / (Decimal(pmax) - Decimal(pmin))
                price_boost = float(1 - price_norm)
            except Exception:
                price_boost = 0

        views = getattr(p, "views_count", 0) or getattr(p, "vistas", 0)
        views_boost = min(views / 1000.0, 0.2)

        score = 0.7 * (gpu + 0.25 * cpu + 0.2 * hz) + 0.3 * price_boost + views_boost

        reasons = []
        if gpu: reasons.append(f"GPU nivel {gpu}")
        if cpu: reasons.append(f"CPU nivel {cpu}")
        if hz:  reasons.append(f"Pantalla {int(hz*100)} Hz")
        if getattr(p, "min_price", None) is not None:
            reasons.append("Precio competitivo")

        badges = []
        if gpu >= 7: badges.append("Rendimiento alto")
        if hz >= 1.2: badges.append("144 Hz+")
        if price_boost >= 0.6: badges.append("Mejor valor")

        ranked.append({"p": p, "score": score, "reasons": reasons, "badges": badges})

    ranked.sort(key=lambda x: (
        -x["score"],
        float(x["p"].min_price) if getattr(x["p"], "min_price", None) is not None else 9e18,
        -(getattr(x["p"], "views_count", 0) or getattr(x["p"], "vistas", 0))
    ))
    return ranked

def _intent_mejor(text: str) -> bool:
    t = text.lower()
    pats = [
        r"\bmejor(es)?\b",
        r"recomiendame uno", r"recomiéndame uno",
        r"\brecomiendame\b", r"\brecomiéndame\b",
        r"\bel más potente\b", r"\bel mas potente\b",
        r"\btop\b", r"\btop\s*1\b",
        r"\bcu[aá]l es mejor\b",
    ]
    return any(re.search(p, t) for p in pats)

# =========================
#   VISTAS CATÁLOGO/UI
# =========================
def home(request):
    productos_vistos = Producto.objects.order_by('-vistas')[:6]
    productos_recientes = Producto.objects.order_by('-fecha_creacion')[:6]
    return render(request, 'home.html', {
        'productos_vistos': productos_vistos,
        'productos_recientes': productos_recientes,
        'tiendas': Tienda.objects.all()
    })

def info(request):
    return render(request, 'info.html')

def products(request):
    q       = (request.GET.get('q') or '').strip()
    tipo_id = request.GET.get('tipo') or ''
    marca_id= request.GET.get('marca') or ''
    pmin    = request.GET.get('pmin') or ''
    pmax    = request.GET.get('pmax') or ''
    order   = request.GET.get('order') or 'recientes'

    productos = (Producto.objects
                 .select_related('marca_producto','categoria_producto','tipo_producto'))

    if q:
        productos = productos.filter(
            Q(nombre_producto__icontains=q) |
            Q(modelo_producto__icontains=q) |
            Q(descripcion_producto__icontains=q) |
            Q(marca_producto__nombre_marca__icontains=q)
        )

    productos = productos.annotate(
        min_price=Min('tiendaproducto__precio'),
        total_stock=Sum('tiendaproducto__stock'),
    )

    if tipo_id:
        productos = productos.filter(tipo_producto_id=tipo_id)
    if marca_id:
        productos = productos.filter(marca_producto_id=marca_id)
    if pmin:
        productos = productos.filter(min_price__gte=pmin)
    if pmax:
        productos = productos.filter(min_price__lte=pmax)

    if order == 'precio':
        productos = productos.order_by('min_price', 'nombre_producto')
    elif order == 'stock':
        productos = productos.order_by('-total_stock', 'nombre_producto')
    else:
        productos = productos.order_by('-fecha_creacion')

    tipos_disponibles = (TipoProducto.objects
                         .filter(id__in=productos.values_list('tipo_producto_id', flat=True))
                         .order_by('nombre_tipo')
                         .distinct())
    marcas_disponibles = (MarcaProducto.objects
                          .filter(id__in=productos.values_list('marca_producto_id', flat=True))
                          .order_by('nombre_marca')
                          .distinct())

    productos = productos.order_by('tipo_producto__nombre_tipo', 'nombre_producto')
    productos_recientes = Producto.objects.order_by('-fecha_creacion')[:6]

    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes,
        'q': q,
        'tipos_disponibles': tipos_disponibles,
        'marcas_disponibles': marcas_disponibles,
        'f': {'tipo': tipo_id, 'marca': marca_id, 'pmin': pmin, 'pmax': pmax, 'order': order}
    })

def product_detail(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    session_key = f'viewed_product_{producto_id}'

    if not request.session.get(session_key, False):
        producto.vistas += 1
        producto.save(update_fields=['vistas'])
        request.session[session_key] = True

    ofertas = TiendaProducto.objects.filter(producto=producto)\
        .select_related('tienda').order_by('precio')

    agg = producto.reviews.aggregate(avg=Avg('rating'), total=Count('id'))
    avg_rating = agg['avg'] or 0
    total_reviews = agg['total'] or 0
    reviews = producto.reviews.select_related('user')
    avg_int = int(avg_rating)

    if request.method == 'POST' and request.user.is_authenticated:
        form = ProductReviewForm(request.POST)
        if form.is_valid():
            rating = form.cleaned_data['rating']
            comment = form.cleaned_data['comment']

            ProductReview.objects.update_or_create(
                producto=producto,
                user=request.user,
                defaults={'rating': rating, 'comment': comment}
            )
            messages.success(request, '¡Tu reseña fue guardada!')
            return redirect(reverse('product_detail', args=[producto.id]) + '#reviews')
    else:
        initial = {}
        if request.user.is_authenticated:
            my = ProductReview.objects.filter(producto=producto, user=request.user).first()
            if my:
                initial = {'rating': my.rating, 'comment': my.comment}
        form = ProductReviewForm(initial=initial)

    return render(request, 'product-detail.html', {
        'producto': producto,
        'ofertas': ofertas,
        'avg_rating': avg_rating,
        'avg_int': avg_int,
        'total_reviews': total_reviews,
        'reviews': reviews,
        'form_review': form,
    })

@login_required
@require_POST
def reportar_producto(request, producto_id):
    """Maneja el POST del formulario de reporte de producto"""
    producto = get_object_or_404(Producto, pk=producto_id)
    
    try:
        Reporte.objects.create(
            target_type='producto',
            producto=producto,
            reporter=request.user,
            motivo=request.POST.get('motivo'),
            detalle=request.POST.get('detalle')
        )
        messages.success(request, 'Reporte enviado correctamente')
    except Exception as e:
        messages.error(request, 'Error al enviar el reporte')
        
    return redirect('product_detail', producto_id=producto_id)

@login_required
@require_POST
def reportar_tienda(request, tienda_id):
    motivo = (request.POST.get('motivo') or '').strip()
    detalle= (request.POST.get('detalle') or '').strip()
    t = get_object_or_404(Tienda, id=tienda_id)
    Reporte.objects.create(
        target_type='tienda', tienda=t,
        reporter=request.user, motivo=motivo, detalle=detalle
    )
    messages.success(request, "Gracias, tu reporte fue enviado.")
    return redirect('store_public_detail', tienda_id=tienda_id)

def products_by_category(request, categoria_id):
    categoria = get_object_or_404(CategoriaProducto, id=categoria_id)
    tipo_id = request.GET.get('tipo') or ''
    marca_id= request.GET.get('marca') or ''
    pmin    = request.GET.get('pmin') or ''
    pmax    = request.GET.get('pmax') or ''
    order   = request.GET.get('order') or 'recientes'

    productos = (Producto.objects
                 .filter(categoria_producto=categoria)
                 .select_related('marca_producto','categoria_producto','tipo_producto')
                 .annotate(min_price=Min('tiendaproducto__precio'),
                           total_stock=Sum('tiendaproducto__stock')))

    if tipo_id:
        productos = productos.filter(tipo_producto_id=tipo_id)
    if marca_id:
        productos = productos.filter(marca_producto_id=marca_id)
    if pmin:
        productos = productos.filter(min_price__gte=pmin)
    if pmax:
        productos = productos.filter(min_price__lte=pmax)

    if order == 'precio':
        productos = productos.order_by('min_price', 'nombre_producto')
    elif order == 'stock':
        productos = productos.order_by('-total_stock', 'nombre_producto')
    else:
        productos = productos.order_by('-fecha_creacion')

    tipos_disponibles = (TipoProducto.objects
                         .filter(id__in=productos.values_list('tipo_producto_id', flat=True))
                         .order_by('nombre_tipo').distinct())
    marcas_disponibles = (MarcaProducto.objects
                          .filter(id__in=productos.values_list('marca_producto_id', flat=True))
                          .order_by('nombre_marca').distinct())

    productos = productos.order_by('tipo_producto__nombre_tipo', 'nombre_producto')
    productos_recientes = Producto.objects.order_by('-fecha_creacion')[:6]
    return render(request, 'products-view.html', {
        'categoria': categoria,
        'productos': productos,
        'productos_recientes': productos_recientes,
        'tipos_disponibles': tipos_disponibles,
        'marcas_disponibles': marcas_disponibles,
        'f': {'tipo': tipo_id, 'marca': marca_id, 'pmin': pmin, 'pmax': pmax, 'order': order}
    })

def products_by_type(request, tipo_id):
    tipo = get_object_or_404(TipoProducto, id=tipo_id)

    marca_id= request.GET.get('marca') or ''
    pmin    = request.GET.get('pmin') or ''
    pmax    = request.GET.get('pmax') or ''
    order   = request.GET.get('order') or 'recientes'
    q       = (request.GET.get('q') or '').strip()

    productos = (Producto.objects
                 .filter(tipo_producto=tipo)
                 .select_related('marca_producto','categoria_producto','tipo_producto')
                 .annotate(min_price=Min('tiendaproducto__precio'),
                           total_stock=Sum('tiendaproducto__stock')))

    if q:
        productos = productos.filter(
            Q(nombre_producto__icontains=q) |
            Q(modelo_producto__icontains=q) |
            Q(descripcion_producto__icontains=q) |
            Q(marca_producto__nombre_marca__icontains=q)
        )

    if marca_id:
        productos = productos.filter(marca_producto_id=marca_id)
    if pmin:
        productos = productos.filter(min_price__gte=pmin)
    if pmax:
        productos = productos.filter(min_price__lte=pmax)

    if order == 'precio':
        productos = productos.order_by('min_price', 'nombre_producto')
    elif order == 'stock':
        productos = productos.order_by('-total_stock', 'nombre_producto')
    else:
        productos = productos.order_by('-fecha_creacion')

    marcas_disponibles = (MarcaProducto.objects
                          .filter(id__in=productos.values_list('marca_producto_id', flat=True))
                          .order_by('nombre_marca').distinct())
    categorias_disponibles = (CategoriaProducto.objects
                              .filter(id__in=productos.values_list('categoria_producto_id', flat=True))
                              .order_by('nombre_categoria').distinct())

    productos = productos.order_by('categoria_producto__nombre_categoria', 'nombre_producto')
    productos_recientes = Producto.objects.order_by('-fecha_creacion')[:6]

    return render(request, 'products-view.html', {
        'tipo': tipo,
        'productos': productos,
        'productos_recientes': productos_recientes,
        'marcas_disponibles': marcas_disponibles,
        'categorias_disponibles': categorias_disponibles,
        'q': q,
        'f': {'marca': marca_id, 'pmin': pmin, 'pmax': pmax, 'order': order}
    })

# =========================
#   AUTH + PERFIL
# =========================
def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Cuenta creada correctamente.")

            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                auth_login(request, user)

            try:
                profile = Profile.objects.get(user=user)
                if profile.profile_type == 'tienda':
                    tienda = _get_or_create_tienda_for_user(user)
                    nombre_tienda      = (request.POST.get('nombre_tienda') or "").strip()
                    descripcion_tienda = (request.POST.get('descripcion_tienda') or "").strip()
                    direccion_tienda   = (request.POST.get('direccion_tienda') or "").strip()
                    img                = request.FILES.get('image_tienda')
                    if nombre_tienda:
                        tienda.nombre_tienda = nombre_tienda
                    if descripcion_tienda is not None:
                        tienda.descripcion_tienda = descripcion_tienda
                    if direccion_tienda is not None:
                        tienda.direccion_tienda = direccion_tienda
                    if img:
                        tienda.image_tienda = img
                    tienda.save()
            except Exception as e:
                messages.warning(request, f"Cuenta creada, pero hubo un detalle al configurar la tienda: {e}")

            return redirect('edit_profile')
    else:
        form = RegisterForm()

    return render(request, 'registration/register.html', {'form': form})

def login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            messages.success(request, f'Bienvenido {user.username}')
            if user.is_staff or user.is_superuser:
                return redirect('admin_dashboard')
            return redirect('home')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
            return render(request, 'registration/login.html')
    return render(request, 'registration/login.html')

def logout(request):
    auth_logout(request)
    return redirect('home')

@login_required
def edit_profile(request):
    user = request.user
    profile = Profile.objects.get(user=user)
    context = {'user': user, 'profile_type': profile.profile_type}

    # --- PERFIL USUARIO ---
    if profile.profile_type == 'usuario':
        categorias = CategoriaProducto.objects.all()
        tipos = TipoProducto.objects.all()

        if request.method == 'POST':
            username = request.POST.get('username')
            new_email = request.POST.get('new_email')
            new_password = request.POST.get('new_password')

            if username:
                user.username = username
            if new_email:
                user.email = new_email
            if new_password:
                user.set_password(new_password)
            user.save()

            PreferenciaUsuario.objects.filter(usuario=user).delete()
            seleccion_categorias = request.POST.getlist('categorias')
            seleccion_tipos = request.POST.getlist('tipos')

            for categoria_id in seleccion_categorias:
                PreferenciaUsuario.objects.create(usuario=user, categoria_id=categoria_id)
            for tipo_id in seleccion_tipos:
                PreferenciaUsuario.objects.create(usuario=user, tipo_producto_id=tipo_id)

            messages.success(request, "Cambios guardados correctamente.")
            return redirect('edit_profile')
        else:
            seleccionadas = PreferenciaUsuario.objects.filter(usuario=user)

        context.update({
            'categorias': categorias,
            'tipos': tipos,
            'seleccionadas_categorias': list(seleccionadas.values_list('categoria_id', flat=True)),
            'seleccionadas_tipos': list(seleccionadas.values_list('tipo_producto_id', flat=True))
        })

    # --- PERFIL TIENDA ---
    elif profile.profile_type == 'tienda':
        servicios = TipoServicio.objects.all()
        categorias = CategoriaProducto.objects.all()
        tienda = Tienda.objects.filter(user=user).first()

        if request.method == 'POST':
            username = request.POST.get('username')
            new_email = request.POST.get('new_email')
            new_password = request.POST.get('new_password')
            if username: user.username = username
            if new_email: user.email = new_email
            if new_password: user.set_password(new_password)
            user.save()

            TiendaCategoria.objects.filter(tienda=tienda).delete()
            seleccion_categorias = request.POST.getlist('categorias')
            seleccion_servicios = request.POST.getlist('servicios')
            for categoria_id in seleccion_categorias:
                TiendaCategoria.objects.create(tienda=tienda, categoria_id=categoria_id)
            if hasattr(tienda, 'servicios'):
                tienda.servicios.clear()
                for servicio_id in seleccion_servicios:
                    tienda.servicios.add(servicio_id)

            nombre_tienda      = (request.POST.get('nombre_tienda') or '').strip()
            descripcion_tienda = (request.POST.get('descripcion_tienda') or '').strip()
            direccion_tienda   = (request.POST.get('direccion_tienda') or '').strip()
            img                = request.FILES.get('image_tienda')

            if nombre_tienda:
                tienda.nombre_tienda = nombre_tienda
            tienda.descripcion_tienda = descripcion_tienda
            tienda.direccion_tienda   = direccion_tienda
            if img:
                tienda.image_tienda = img

            tienda.save()

            messages.success(request, "Cambios de tienda guardados correctamente.")
            return redirect('edit_profile')
        else:
            seleccionadas_categorias = TiendaCategoria.objects.filter(tienda=tienda).values_list('categoria_id', flat=True)
            seleccionados_servicios = []
            if hasattr(tienda, 'servicios'):
                seleccionados_servicios = tienda.servicios.values_list('id', flat=True)

        context.update({
            'servicios': servicios,
            'categorias': categorias,
            'seleccionadas_categorias': list(seleccionadas_categorias),
            'seleccionados_servicios': list(seleccionados_servicios),
            'tienda': tienda,
        })

    return render(request, 'edit-profile.html', context)

def _require_store_profile(request):
    profile = Profile.objects.get(user=request.user)
    if profile.profile_type != 'tienda':
        messages.error(request, "Debes tener perfil de tienda para acceder.")
        return None
    return profile

@login_required
def store_offers_list(request):
    """Vista de listado de productos de la tienda"""
    profile = _require_store_profile(request)
    if not profile:
        return redirect('home')
        
    tienda = get_object_or_404(Tienda, user=request.user)
    
    # Obtener ofertas con notificaciones pendientes
    ofertas = TiendaProducto.objects.filter(tienda=tienda).select_related('producto')
    
    # Obtener notificaciones no leídas y agruparlas por tipo
    notificaciones = (Notificacion.objects
        .filter(tienda=tienda, leida=False)
        .order_by('-created_at'))
    
    # Agrupar notificaciones por producto y por tipo
    notif_por_producto = {}
    for notif in notificaciones:
        if notif.producto:
            if notif.producto.id not in notif_por_producto:
                notif_por_producto[notif.producto.id] = []
            notif_por_producto[notif.producto.id].append({
                'id': notif.id,
                'tipo': notif.get_tipo_display(),
                'mensaje': notif.mensaje,
                'fecha': notif.created_at,
                'leida': notif.leida
            })
    
    return render(request, 'store/offers_list.html', {
        'ofertas': ofertas,
        'notificaciones': notificaciones,
        'notif_por_producto': notif_por_producto,
    })

@login_required
def store_offer_new(request):
    profile = _require_store_profile(request)
    if not profile:
        return redirect('home')

    tienda = _get_or_create_tienda_for_user(request.user)

    if request.method == 'POST':
        mode = request.POST.get('mode', 'existing')  # 'existing' | 'new'

        # ---- EXISTENTE
        if mode == 'existing':
            form_existing = ExistingProductOfferForm(request.POST)
            form_new = NewProductAndOfferForm()  # vacío
            if form_existing.is_valid():
                producto = form_existing.cleaned_data['producto']
                precio = form_existing.cleaned_data['precio']
                url_externa = form_existing.cleaned_data.get('url_externa') or None
                stock = form_existing.cleaned_data.get('stock') or 0
                nota = form_existing.cleaned_data.get('nota_tienda') or ""

                oferta, created = TiendaProducto.objects.get_or_create(
                    tienda=tienda, producto=producto,
                    defaults={'precio': precio, 'url_externa': url_externa, 'stock': stock, 'nota_tienda': nota}
                )
                if not created:
                    oferta.precio = precio
                    oferta.url_externa = url_externa
                    oferta.stock = stock
                    oferta.nota_tienda = nota
                    oferta.save()

                messages.success(request, "Oferta guardada correctamente.")
                return redirect('store_offers_list')

        # ---- NUEVO + OFERTA
        else:
            form_existing = ExistingProductOfferForm()
            form_new = NewProductAndOfferForm(request.POST, request.FILES)
            if form_new.is_valid():
                marca = form_new.cleaned_data['marca_producto']
                categoria = form_new.cleaned_data['categoria_producto']
                tipo = form_new.cleaned_data['tipo_producto']

                modelo_disp   = (form_new.cleaned_data.get('modelo_producto') or "").strip()
                nombre_manual = (form_new.cleaned_data.get('nombre_producto') or "").strip()
                descripcion   = form_new.cleaned_data.get('descripcion_producto') or ""
                imagen        = form_new.cleaned_data.get('imagen_producto')

                modelo_key_val = getattr(form_new, "_modelo_key", None)
                modelo_display = getattr(form_new, "_modelo_display", None)
                nombre_autogen = getattr(form_new, "_nombre_autogen", None)

                if not modelo_disp and modelo_display:
                    modelo_disp = modelo_display

                if nombre_manual:
                    nombre_final = nombre_manual
                elif nombre_autogen:
                    nombre_final = nombre_autogen
                else:
                    nombre_final = f"{marca.nombre_marca} {modelo_disp}".strip()

                precio = form_new.cleaned_data['precio']
                url_externa = form_new.cleaned_data.get('url_externa') or None
                stock = form_new.cleaned_data.get('stock') or 0
                nota = form_new.cleaned_data.get('nota_tienda') or ""

                candidatos = Producto.objects.filter(marca_producto=marca)
                producto = None
                if modelo_key_val:
                    from .forms import model_key as _model_key
                    for p in candidatos:
                        try:
                            if _model_key(p.modelo_producto) == modelo_key_val:
                                producto = p
                                break
                        except Exception:
                            continue
                if not producto and modelo_disp:
                    producto = candidatos.filter(modelo_producto__iexact=modelo_disp).first()

                if not producto:
                    producto = Producto.objects.create(
                        nombre_producto=nombre_final,
                        modelo_producto=modelo_disp,
                        descripcion_producto=descripcion,
                        imagen_producto=imagen,
                        marca_producto=marca,
                        categoria_producto=categoria,
                        tipo_producto=tipo
                    )

                oferta, created = TiendaProducto.objects.get_or_create(
                    tienda=tienda, producto=producto,
                    defaults={'precio': precio, 'url_externa': url_externa, 'stock': stock, 'nota_tienda': nota}
                )
                if not created:
                    oferta.precio = precio
                    oferta.url_externa = url_externa
                    oferta.stock = stock
                    oferta.nota_tienda = nota
                    oferta.save()

                names = request.POST.getlist('spec_name[]')
                vals  = request.POST.getlist('spec_value[]')
                if names and vals:
                    for n, v in zip(names, vals):
                        n = _canonize_spec_name((n or '').strip())
                        v = (v or '').strip()
                        if n and v:
                            EspecificacionProducto.objects.create(
                                producto=producto,
                                nombre_especificacion=n,
                                valor_especificacion=v
                            )

                messages.success(request, "Producto y oferta guardados correctamente.")
                return redirect('store_offers_list')

        # Si algo no valida, re-render con errores
        return render(request, 'store/offer_form.html', {
            'form_existing': form_existing,
            'form_new': form_new,
            'tienda': tienda,
            'tiposproductos': TipoProducto.objects.all(),
        })

    # GET
    form_existing = ExistingProductOfferForm()
    form_new = NewProductAndOfferForm()
    return render(request, 'store/offer_form.html', {
        'form_existing': form_existing,
        'form_new': form_new,
        'tienda': tienda,
        'tiposproductos': TipoProducto.objects.all(),
    })

@login_required
def store_offer_edit(request, oferta_id):
    profile = _require_store_profile(request)
    if not profile:
        return redirect('home')

    tienda = Tienda.objects.filter(user=request.user).first()
    oferta = get_object_or_404(TiendaProducto, id=oferta_id, tienda=tienda)

    if request.method == 'POST':
        try:
            precio = request.POST.get('precio')
            stock = request.POST.get('stock', 0)
            url_externa = request.POST.get('url_externa', '')
            nota_tienda = request.POST.get('nota_tienda', '')
            
            oferta.precio = precio
            oferta.stock = stock
            oferta.url_externa = url_externa
            oferta.nota_tienda = nota_tienda
            oferta.save()
            
            messages.success(request, "Oferta actualizada correctamente")
            return redirect('store_offers_list')
        except Exception as e:
            messages.error(request, f"No se pudo actualizar la oferta: {str(e)}")

    return render(request, 'store/offer_edit.html', {'oferta': oferta})

@login_required
def store_offer_delete(request, oferta_id):
    profile = _require_store_profile(request)
    if not profile:
        return redirect('home')

    tienda = Tienda.objects.filter(user=request.user).first()
    oferta = get_object_or_404(TiendaProducto, id=oferta_id, tienda=tienda)

    if request.method == 'POST':
        oferta.delete()
        messages.success(request, "Oferta eliminada.")
        return redirect('store_offers_list')

    return render(request, 'store/offer_delete_confirm.html', {'oferta': oferta})

@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """Marca una notificación como leída"""
    notification = get_object_or_404(
        Notificacion, 
        id=notification_id,
        tienda__user=request.user
    )
    notification.leida = True
    notification.save()
    
    # Redireccionar a la página anterior
    next_url = request.POST.get('next', 'store_notifications')
    return redirect(next_url)

# === Form local: NewProductAndOfferForm (evita choque con import) ===
class NewProductAndOfferForm(forms.ModelForm):
    # Oferta
    precio = forms.DecimalField(
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "749990",
            "inputmode": "numeric",
            "step": "1"
        })
    )
    url_externa = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            "class": "form-control",
            "placeholder": "https://tu-tienda.cl/producto/...",
        })
    )
    stock = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "10",
            "inputmode": "numeric"
        })
    )
    nota_tienda = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Ej. Entrega 24h | Garantía 12m",
        })
    )
    # Producto
    modelo_producto = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Ej. Lenovo LOQ 15IRH8"
        })
    )
    descripcion_producto = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": 'Ej. Laptop gamer 15.6" 144 Hz, i5-13420H + RTX 4060, 16 GB RAM, 512 GB SSD'
        })
    )
    imagen_producto = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"})
    )

    class Meta:
        model = Producto
        fields = (
            "modelo_producto", "descripcion_producto", "imagen_producto",
            "marca_producto", "tipo_producto", "categoria_producto",
        )
        widgets = {
            "marca_producto":    forms.Select(attrs={"class": "form-select"}),
            "tipo_producto":     forms.Select(attrs={"class": "form-select"}),
            "categoria_producto":forms.Select(attrs={"class": "form-select"}),
        }

# =========================
#   CHECKS / PREFERENCIAS
# =========================
def check_username(request):
    username = request.GET.get('username', None)
    exists = User.objects.filter(username__iexact=username).exists()
    return JsonResponse({'exists': exists})

def check_email(request):
    email = request.GET.get('email', None)
    exists = User.objects.filter(email__iexact=email).exists()
    return JsonResponse({'exists': exists})

@login_required
def preferences_products_view(request):
    user = request.user
    preferencias = PreferenciaUsuario.objects.filter(usuario=user)

    categorias_ids = list(preferencias.values_list('categoria_id', flat=True))
    tipos_ids = list(preferencias.values_list('tipo_producto_id', flat=True))

    if categorias_ids and tipos_ids:
        productos = Producto.objects.filter(
            categoria_producto__in=categorias_ids,
            tipo_producto__in=tipos_ids
        ).distinct()
    elif categorias_ids:
        productos = Producto.objects.filter(categoria_producto__in=categorias_ids).distinct()
    elif tipos_ids:
        productos = Producto.objects.filter(tipo_producto__in=tipos_ids).distinct()
    else:
        productos = Producto.objects.none()

    return render(request, 'preferences-products-view.html', {'productos': productos})

# =========================
#   CHAT (página + API)
# =========================
@login_required
def chat_page(request):
    if "chat_history" not in request.session:
        request.session["chat_history"] = [{"role": "system", "content": SYSTEM_PROMPT}]
        request.session.modified = True
    return render(request, "chat.html")

@login_required
@require_POST
def chat_api(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body.decode("utf-8"))
            msg = (body.get("message") or "").strip()
        except Exception:
            return JsonResponse({"error": "JSON inválido."}, status=400)
    else:
        msg = (request.POST.get("message") or "").strip()

    if not msg:
        return JsonResponse({"error": "Mensaje vacío."}, status=400)

    msg_norm = _normalize_for_matching(msg)

    # Comparación directa
    name_a, name_b = _parse_compare_intent(msg_norm)
    if name_a and name_b:
        prod_a = _find_product_by_text(name_a)
        prod_b = _find_product_by_text(name_b)
        if prod_a and prod_b:
            comp = _make_compare_payload(prod_a, prod_b, request)
            reply = (
                "Comparativa rápida (según nuestro catálogo):\n\n"
                f"• {comp['left']['titulo']}\n"
                f"• {comp['right']['titulo']}\n\n"
                "Te dejo la tabla de especificaciones. ¿Resumir diferencias clave según tu uso?"
            )
            history = request.session.get("chat_history", [{"role": "system", "content": SYSTEM_PROMPT}])
            history = _truncate_history(history)
            history.append({"role": "user", "content": msg})
            history.append({"role": "assistant", "content": reply})
            request.session["chat_history"] = history
            request.session.modified = True
            return JsonResponse({"reply": reply, "comparacion": comp, "productos": [], "filtros_aplicados": []})

    # Sin intención de compra clara
    if not _intent_recommend(msg_norm):
        if _intent_smalltalk(msg_norm):
            reply = ("¡Hola! ¿Qué estás buscando hoy? "
                     "Puedo sugerirte por **categoría** (Gamer, Trabajo, Estudio, Diseño, Hogar) "
                     "y **tipo** (Notebook, Procesador, etc.). "
                     "Si me dices un **presupuesto**, afino la recomendación.")
        else:
            reply = ("Para ayudarte mejor, dime al menos la **categoría** (p. ej., Gamer) "
                     "y/o el **tipo de producto** (Notebook, Procesador) y, si puedes, tu **presupuesto**.")
        history = request.session.get("chat_history", [{"role": "system", "content": SYSTEM_PROMPT}])
        history = _truncate_history(history)
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": reply})
        request.session["chat_history"] = history
        request.session.modified = True
        return JsonResponse({"reply": reply, "productos": [], "filtros_aplicados": []})

    # Recomendación
    session = _get_or_create_chat_session(request)
    sticky_cats, sticky_types, sticky_budget = _get_sticky_filters(session)

    parsed_now = parse_requirements(request.user, msg_norm)
    cats_from_text = list(parsed_now["cat_text"])
    types_from_text = list(parsed_now["type_text"])

    if not cats_from_text and _texto_contiene_gamer(msg):
        cid = _id_categoria("Gamer")
        if cid:
            cats_from_text = [cid]
    if not types_from_text and _texto_contiene_notebook(msg):
        tid = _id_tipo("Notebook")
        if tid:
            types_from_text = [tid]

    sticky_cats_turn = None if cats_from_text else sticky_cats
    sticky_types_turn = None if types_from_text else sticky_types

    if cats_from_text:
        msg_norm += " " + " ".join(["Gamer"] * len(cats_from_text))
    if types_from_text:
        msg_norm += " " + " ".join(["Notebook"] * len(types_from_text))

    qs, filtros_ids = recommend_products(
        request.user,
        msg_norm,
        limit=6,
        sticky_cats=sticky_cats_turn,
        sticky_types=sticky_types_turn,
        sticky_budget=sticky_budget,
    )

    # Marcas a evitar explícitamente
    lower = msg.lower()
    marcas_evitar = []
    for m in ["acer","huawei","apple","msi","asus","lenovo","hp","dell","samsung","xiaomi"]:
        if m in lower and any(kw in lower for kw in [" no ", "evit", "mala", "no quiero", "descarta", "odio"]):
            marcas_evitar.append(m)
    if marcas_evitar:
        qs = qs.exclude(marca_producto__nombre_marca__iregex="|".join(marcas_evitar))

    if qs.exists():
        _set_sticky_filters(session, filtros_ids)

        intent_mejor = _intent_mejor(msg)
        is_gamer = any(
            (s or "").lower() == "gamer"
            for s in CategoriaProducto.objects.filter(id__in=filtros_ids.get("categorias", []))
                                              .values_list("nombre_categoria", flat=True)
        )
        is_notebook = any(
            (s or "").lower() == "notebook"
            for s in TipoProducto.objects.filter(id__in=filtros_ids.get("tipos", []))
                                         .values_list("nombre_tipo", flat=True)
        )

        if intent_mejor and is_gamer and is_notebook:
            ranked = _rank_notebooks_for_gaming(qs)
            pick = ranked[0]
            alts = ranked[1:3]

            p = pick["p"]
            precio_txt = _fmt_money_clp(getattr(p, "min_price", None)) if getattr(p, "min_price", None) is not None else ""
            razones = "; ".join(pick["reasons"]) if pick["reasons"] else "equilibrio general"

            assistant = (
                f"Para juegos pesados, mi **recomendación principal** es **{p.nombre_producto}** "
                f"({p.modelo_producto}). Motivos: {razones}"
                + (f". Precio de referencia: {precio_txt}." if precio_txt else ".")
            )

            if alts:
                bullets = []
                for alt in alts:
                    pa = alt["p"]
                    pt = _fmt_money_clp(getattr(pa, "min_price", None)) if getattr(pa, "min_price", None) is not None else ""
                    r = "; ".join(alt["reasons"]) if alt["reasons"] else "buena alternativa"
                    bullets.append(f"- **{pa.nombre_producto}** ({pa.modelo_producto}): {r}" + (f". {pt}" if pt else ""))
                assistant += "\n\n**Alternativas**:\n" + "\n".join(bullets)

            assistant += "\n\n¿Quieres priorizar tasa de refresco, peso o precio?"

            ordered = [pick["p"]] + [x["p"] for x in alts] + [x["p"] for x in ranked[3:]]
            meta = {x["p"].id: {"badges": x["badges"], "nota": "; ".join(x["reasons"])} for x in ranked}

            items = [{
                "id": prod.id,
                "nombre": prod.nombre_producto,
                "imagen": request.build_absolute_uri(prod.imagen_producto.url) if getattr(prod, "imagen_producto", None) else "",
                "marca": prod.marca_producto.nombre_marca if prod.marca_producto_id else "",
                "categoria": prod.categoria_producto.nombre_categoria if prod.categoria_producto_id else "",
                "tipo": prod.tipo_producto.nombre_tipo if prod.tipo_producto_id else "",
                "url": reverse("product_detail", args=[prod.id]),
                "badges": meta.get(prod.id, {}).get("badges", []),
                "nota": meta.get(prod.id, {}).get("nota", ""),
            } for prod in ordered]
        else:
            labels = _product_labels(qs)
            llm = LLMClient()
            assistant = llm.answer(msg, labels)

            items = [{
                "id": p.id,
                "nombre": p.nombre_producto,
                "imagen": request.build_absolute_uri(p.imagen_producto.url) if getattr(p, "imagen_producto", None) else "",
                "marca": p.marca_producto.nombre_marca if p.marca_producto_id else "",
                "categoria": p.categoria_producto.nombre_categoria if p.categoria_producto_id else "",
                "tipo": p.tipo_producto.nombre_tipo if p.tipo_producto_id else "",
                "url": reverse("product_detail", args=[p.id]),
            } for p in qs]

        cat_labels = list(CategoriaProducto.objects.filter(id__in=filtros_ids.get("categorias", []))
                          .values_list("nombre_categoria", flat=True))
        type_labels = list(TipoProducto.objects.filter(id__in=filtros_ids.get("tipos", []))
                           .values_list("nombre_tipo", flat=True))
        chips = []
        if cat_labels: chips.append("categorías: " + ", ".join(cat_labels))
        if type_labels: chips.append("tipos: " + ", ".join(type_labels))
        if filtros_ids.get("budget"):
            chips.append("presupuesto ≤ ${:,}".format(filtros_ids["budget"]).replace(",", "."))
        if marcas_evitar:
            chips.append("evitar: " + ", ".join(s.capitalize() for s in marcas_evitar))

        history = request.session.get("chat_history", [{"role": "system", "content": SYSTEM_PROMPT}])
        history = _truncate_history(history)
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": assistant})
        request.session["chat_history"] = history
        request.session.modified = True

        return JsonResponse({"reply": assistant, "productos": items, "filtros_aplicados": chips})

    reply = ("No encontré coincidencias en el catálogo con ese criterio. "
             "¿Te parece si me indicas **categoría** (Gamer/Trabajo/Estudio/Diseño/Hogar), "
             "**tipo** (Notebook/Procesador/…) y un **presupuesto** aproximado?")
    history = request.session.get("chat_history", [{"role": "system", "content": SYSTEM_PROMPT}])
    history = _truncate_history(history)
    history.append({"role": "user", "content": msg})
    history.append({"role": "assistant", "content": reply})
    request.session["chat_history"] = history
    request.session.modified = True
    return JsonResponse({"reply": reply, "productos": [], "filtros_aplicados": []})

@login_required
@require_POST
def chat_reset(request):
    request.session["chat_history"] = [{"role": "system", "content": SYSTEM_PROMPT}]
    request.session.modified = True
    return JsonResponse({"ok": True})

# =========================
#   APIs auxiliares
# =========================
@login_required
def api_brands_by_type(request):
    tipo_id = request.GET.get('tipo_id')
    qs = MarcaProducto.objects.filter(producto__tipo_producto_id=tipo_id)\
                            .distinct().values('id', 'nombre_marca')
    brands = [{'id': b['id'], 'nombre': b['nombre_marca']} for b in qs]
    return JsonResponse({'brands': brands})

@login_required
def api_products_by_type_brand(request):
    tipo_id = request.GET.get('tipo_id')
    marca_id = request.GET.get('marca_id')
    qs = Producto.objects.filter(tipo_producto_id=tipo_id,
                                marca_producto_id=marca_id)\
                            .order_by('nombre_producto')\
                            .values('id', 'nombre_producto', 'modelo_producto')
    products = []
    for p in qs:
        name = p['nombre_producto']
        if p['modelo_producto']:
            name = f"{name} ({p['modelo_producto']})"
        products.append({'id': p['id'], 'name': name})
    return JsonResponse({'products': products})

@login_required
def store_notifications(request):
    """Vista de notificaciones para tiendas"""
    profile = _require_store_profile(request)
    if not profile:
        return redirect('home')
        
    tienda = get_object_or_404(Tienda, user=request.user)
    
    # Determinar qué notificaciones mostrar
    show_read = request.GET.get('filter') == 'all'
    
    # Consultar notificaciones según el filtro
    notifications = Notificacion.objects.filter(tienda=tienda)
    if not show_read:
        notifications = notifications.filter(leida=False)
    
    # Ordenar por fecha descendente
    notifications = notifications.order_by('-created_at')
    
    # Contar no leídas para el badge
    unread_count = notifications.filter(leida=False).count()
    
    return render(request, 'store/notifications.html', {
        'notifications': notifications,
        'show_read': show_read,
        'unread_count': unread_count,
    })

@login_required
@require_POST
def store_offer_quick_edit(request, oferta_id):
    """Vista para edición rápida desde notificaciones"""
    profile = _require_store_profile(request)
    if not profile:
        return redirect('home')
        
    tienda = get_object_or_404(Tienda, user=request.user)
    oferta = get_object_or_404(TiendaProducto, id=oferta_id, tienda=tienda)
    
    # Actualizar información del producto
    producto = oferta.producto
    producto.nombre_producto = request.POST.get('nombre', '').strip()
    producto.modelo_producto = request.POST.get('modelo', '').strip()
    producto.descripcion_producto = request.POST.get('descripcion', '').strip()
    producto.save()
    
    # Actualizar precio si cambió
    try:
        nuevo_precio = float(request.POST.get('precio', '0'))
        if nuevo_precio > 0:
            oferta.precio = nuevo_precio
            oferta.save()
    except (ValueError, TypeError):
        pass

    # Marcar notificaciones como leídas
    Notificacion.objects.filter(
        tienda=tienda,
        producto=producto,
        leida=False
    ).update(leida=True)

    # Buscar y actualizar el reporte asociado
    reporte = Reporte.objects.filter(
        producto=producto,
        estado='resuelto',
        notificacion_leida=False
    ).order_by('-fecha_accion').first()

    if reporte:
        # Registrar que la tienda atendió el reporte
        reporte.notificacion_leida = True
        reporte.fecha_actualizacion = timezone.now()
        reporte.save()

    messages.success(request, 'Información actualizada correctamente')
    return redirect('store_offers_list')