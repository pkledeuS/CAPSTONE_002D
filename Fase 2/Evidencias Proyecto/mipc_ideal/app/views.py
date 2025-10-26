# app/views.py
import json
import requests
import re

from decimal import Decimal
from django.db import models
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils.text import slugify
from django.db.models import Q

from .forms import RegisterForm, ExistingProductOfferForm, NewProductAndOfferForm, model_key
from .models import (
    Producto, CategoriaProducto, TipoProducto,
    TipoServicio, PreferenciaUsuario, TiendaCategoria, Tienda, Profile,
    ChatSession, ChatTurn, EspecificacionProducto, TiendaProducto, MarcaProducto,
)
from .services.llm_provider import LLMClient
from .services.recommender import recommend_products, parse_requirements

# =========================
#   CONSTANTES DE CHAT
# =========================
OLLAMA_BASE = "http://127.0.0.1:11434"
SYSTEM_PROMPT = (
    "Eres un asesor de compras de PC con estilo claro y conciso. "
    "Nunca inventes modelos ni precios; si no hay catálogo, no recomiendes marcas/modelos concretos. "
    "Cuando el usuario pida 'el mejor' o 'recomiéndame uno', explica tus criterios y pide 1 dato clave que falte. "
    "Responde en español, breve y directo."
)


# =========================
#   HELPERS GENERALES
# =========================
def _truncate_history(history, max_turns=8):
    """Mantiene historial corto en sesión (system + últimos N turnos)."""
    if len(history) <= 1 + max_turns * 2:
        return history
    return [history[0]] + history[-(max_turns * 2):]


def _build_product_context(user_text: str) -> str:
    """
    Construye un bloque factual con hasta 3 productos que 'contengan' el texto,
    para inyectarlo al modelo cuando haga falta.
    """
    qs = Producto.objects.filter(
        models.Q(nombre_producto__icontains=user_text) |
        models.Q(modelo_producto__icontains=user_text)
    )[:3]
    if not qs:
        return ""
    bloques = []
    for p in qs:
        specs = EspecificacionProducto.objects.filter(producto=p).values_list(
            "nombre_especificacion", "valor_especificacion"
        )
        specs_txt = "; ".join(f"{n}: {v}" for n, v in specs) if specs else "Sin especificaciones"
        bloques.append(
            f"- {p.nombre_producto} ({p.modelo_producto}) | "
            f"Marca: {p.marca_producto.nombre_marca if p.marca_producto_id else ''} | "
            f"Categoría: {p.categoria_producto.nombre_categoria if p.categoria_producto_id else ''} | "
            f"Tipo: {p.tipo_producto.nombre_tipo if p.tipo_producto_id else ''} | "
            f"Especificaciones: {specs_txt}"
        )
    return "CATÁLOGO (datos reales, úsalo estrictamente):\n" + "\n".join(bloques)


def _normalize_for_matching(text: str) -> str:
    """
    Añade sinónimos útiles sin forzar categorías genéricas:
    - notebook(s)/laptop(s)/portátil(es) -> Notebook
    - gamer/gaming/juego(s)/videojuego(s) -> Gamer
    """
    t = text.lower()
    extra = []

    # Tipo: Notebook (variantes)
    if any(w in t for w in [
        "notebook", "notebooks", "laptop", "laptops",
        "portatil", "portátil", "portatiles", "portátiles"
    ]):
        extra.append("Notebook")

    # Categoría: Gamer (variantes)
    if any(w in t for w in [
        "gamer", "gaming", "juego", "juegos",
        "videojuego", "videojuegos"
    ]):
        extra.append("Gamer")

    return text + (" " + " ".join(extra) if extra else "")


def _product_snippets(qs):
    """
    Devuelve snippets 100% basados en BD (para LLMClient.answer y evitar alucinación).
    """
    snippets = []
    for p in qs:
        specs = EspecificacionProducto.objects.filter(producto=p) \
            .values_list("nombre_especificacion", "valor_especificacion")[:6]
        specs_txt = "; ".join(f"{n}: {v}" for n, v in specs) if specs else "Sin especificaciones"
        marca = p.marca_producto.nombre_marca if p.marca_producto_id else ""
        cat = p.categoria_producto.nombre_categoria if p.categoria_producto_id else ""
        tipo = p.tipo_producto.nombre_tipo if p.tipo_producto_id else ""
        snippets.append(
            f"{p.nombre_producto} ({p.modelo_producto}) — Marca: {marca} | "
            f"Categoría: {cat} | Tipo: {tipo} | {specs_txt}"
        )
    return snippets

def _product_labels(qs, limit=6):
    """
    Devuelve solo etiquetas legibles para un primer mensaje (sin specs).
    Ej: "Lenovo LOQ 15IRH8 (RTX 4060)", "ASUS TUF Gaming A15 (FA507NU)".
    """
    labels = []
    for p in qs[:limit]:
        # Nombre ya suele incluir modelo; si no, agregamos entre paréntesis.
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
    return any(w in t for w in ["gamer", "gaming", "juego", "juegos", "videojuego", "videojuegos"])

def _texto_contiene_notebook(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in [
        "notebook", "notebooks", "laptop", "laptops",
        "portatil", "portátil", "portatiles", "portátiles"
    ])

# --- INTENCIONES & COMPARACIÓN (añadir) ---
def _intent_smalltalk(text: str) -> bool:
    t = (text or "").lower()
    # saludos/agradecimientos/palabras sueltas sin intención de compra
    pats = [
        r"\b(hola|buenas|buen día|buenos días|buenas tardes|buenas noches)\b",
        r"\b(gracias|grx|ty|thank)\b",
        r"^ok$|^vale$|^sip$|^aja$|^claro$",
        r"\b(cómo estás|que tal|qué tal|todo bien)\b",
    ]
    return any(re.search(p, t) for p in pats)

def _intent_recommend(text: str) -> bool:
    t = (text or "").lower()
    # si menciona categorías, tipos o verbos de intención
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
    """
    Busca un producto por nombre o modelo. Heurística estable.
    """
    t = (text or "").strip()
    if not t:
        return None
    return Producto.objects.filter(
        Q(nombre_producto__icontains=t) | Q(modelo_producto__icontains=t)
    ).order_by("-vistas", "-fecha_creacion").first()

def _parse_compare_intent(msg: str):
    """
    Detecta: 'compara A con B', 'A vs B', 'entre A y B', comillas "A" vs "B".
    Devuelve (name_a, name_b) o (None, None).
    """
    if not msg:
        return None, None
    m = msg.lower()

    # comillas
    quoted = re.findall(r'"([^"]{2,80})"', msg)
    if len(quoted) >= 2:
        return quoted[0], quoted[1]

    # separadores comunes
    seps = [r"\bvs\b", r"\bversus\b", r"\bcontra\b", r"\bcon\b", r"\by\b"]
    for sep in seps:
        parts = re.split(sep, msg, flags=re.IGNORECASE)
        if len(parts) == 2:
            a, b = parts[0].strip(" :,-"), parts[1].strip(" :,-")
            if len(a) >= 2 and len(b) >= 2:
                return a, b

    # 'entre A y B'
    m2 = re.search(r"entre\s+(.+?)\s+y\s+(.+)", msg, flags=re.IGNORECASE)
    if m2:
        a = m2.group(1).strip(" :,-")
        b = m2.group(2).strip(" :,-")
        if len(a) >= 2 and len(b) >= 2:
            return a, b

    # si no dijo 'comparar' ni 'vs', no obligamos
    if not (re.search(r"\bcompar", m) or re.search(r"\bvs\b|\bversus\b", m)):
        return None, None

    return None, None

def _gather_specs(prod: Producto):
    specs = dict(EspecificacionProducto.objects.filter(producto=prod).values_list(
        "nombre_especificacion", "valor_especificacion"
    ))
    meta = {
        "id": prod.id,
        "nombre": prod.nombre_producto,
        "modelo": prod.modelo_producto,
        "marca": prod.marca_producto.nombre_marca if prod.marca_producto_id else "",
        "categoria": prod.categoria_producto.nombre_categoria if prod.categoria_producto_id else "",
        "tipo": prod.tipo_producto.nombre_tipo if prod.tipo_producto_id else "",
    }
    return specs, meta

def _merge_spec_rows(specs_a: dict, specs_b: dict):
    keys = set(specs_a.keys()) | set(specs_b.keys())
    preferred = [
        "Arquitectura","Núcleos/Hilos","Frecuencia","Frecuencia máx.",
        "Socket","TDP","Caché","Cache L3","iGPU","Litografía","Soporte RAM",
        "Pantalla","GPU","CPU","Almacenamiento","Memoria"
    ]
    def key_order(k):
        k_norm = _normalize(k)
        for i, pref in enumerate(preferred):
            if _normalize(pref) == k_norm:
                return (0, i, k)
        return (1, 999, k.lower())

    rows = []
    for k in sorted(keys, key=key_order):
        rows.append({"name": k, "a": specs_a.get(k, "—"), "b": specs_b.get(k, "—")})
    return rows

def _make_compare_payload(prod_a: Producto, prod_b: Producto, request):
    specs_a, meta_a = _gather_specs(prod_a)
    specs_b, meta_b = _gather_specs(prod_b)
    rows = _merge_spec_rows(specs_a, specs_b)
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
    """
    Garantiza que exista una Tienda para el usuario actual.
    Crea un placeholder si no existe (email único y seguro).
    """
    from .models import Tienda
    tienda = Tienda.objects.filter(user=user).first()
    if tienda:
        return tienda

    # Email único “placeholder” (no se usa para contacto real)
    local = slugify(user.username) or f"user{user.id}"
    placeholder_email = f"{local}@placeholder.local"

    tienda = Tienda.objects.create(
        user=user,
        nombre_tienda=f"Tienda de {user.username}",
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
    specs = EspecificacionProducto.objects.filter(producto=p).values_list(
        "nombre_especificacion", "valor_especificacion"
    )[:8]
    if specs:
        parts.extend([f"{n} {v}" for n, v in specs])
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
                price_boost = float(1 - price_norm)  # más barato → mayor puntaje
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

def _fmt_money_clp(val):
    try:
        return "$" + f"{int(Decimal(val)):,}".replace(",", ".")
    except Exception:
        return ""

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
        'productos_recientes': productos_recientes
    })


def info(request):
    return render(request, 'info.html')


def products(request):
    q = (request.GET.get('q') or '').strip()

    productos = Producto.objects.all()
    if q:
        productos = productos.filter(
            Q(nombre_producto__icontains=q) |
            Q(modelo_producto__icontains=q) |
            Q(descripcion_producto__icontains=q) |
            Q(marca_producto__nombre_marca__icontains=q) |
            Q(categoria_producto__nombre_categoria__icontains=q) |
            Q(tipo_producto__nombre_tipo__icontains=q)
        ).distinct()

    productos_recientes = Producto.objects.order_by('-fecha_creacion')[:6]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes,
        'q': q,
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

    return render(request, 'product-detail.html', {'producto': producto, 'ofertas': ofertas})


def products_by_category(request, categoria_id):
    categoria = get_object_or_404(CategoriaProducto, id=categoria_id)
    productos = Producto.objects.filter(categoria_producto=categoria)
    productos_recientes = productos.order_by('-fecha_creacion')[:6]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes,
        'categoria': categoria
    })


def products_by_type(request, tipo_id):
    tipo = get_object_or_404(TipoProducto, id=tipo_id)
    productos = Producto.objects.filter(tipo_producto=tipo)
    productos_recientes = productos.order_by('-fecha_creacion')[:6]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes,
        'tipo': tipo
    })


# =========================
#   AUTH + PERFIL
# =========================
def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Cuenta creada correctamente.")

            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                auth_login(request, user)

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
            return redirect('home')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos. Por favor, inténtalo de nuevo.')
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

            # Actualizar preferencias
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

            if username:
                user.username = username
            if new_email:
                user.email = new_email
            if new_password:
                user.set_password(new_password)
            user.save()

            # Actualizar servicios y categorías de la tienda
            TiendaCategoria.objects.filter(tienda=tienda).delete()
            seleccion_categorias = request.POST.getlist('categorias')
            seleccion_servicios = request.POST.getlist('servicios')

            for categoria_id in seleccion_categorias:
                TiendaCategoria.objects.create(tienda=tienda, categoria_id=categoria_id)

            if hasattr(tienda, 'servicios'):
                tienda.servicios.clear()
                for servicio_id in seleccion_servicios:
                    tienda.servicios.add(servicio_id)

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
            'seleccionados_servicios': list(seleccionados_servicios)
        })

    return render(request, 'edit-profile.html', context)

def _require_store_profile(request):
    from .models import Profile
    profile = Profile.objects.get(user=request.user)
    if profile.profile_type != 'tienda':
        messages.error(request, "Debes tener perfil de tienda para acceder.")
        return None
    return profile

@login_required
def store_offers_list(request):
    profile = _require_store_profile(request)
    if not profile:
        return redirect('home')

    tienda = _get_or_create_tienda_for_user(request.user)
    ofertas = TiendaProducto.objects.filter(tienda=tienda)\
        .select_related('producto').order_by('producto__nombre_producto')

    return render(request, 'store/offers_list.html', {
        'ofertas': ofertas,
        'tienda': tienda,
    })

@login_required
def store_offer_new(request):
    profile = _require_store_profile(request)
    if not profile:
        return redirect('home')

    tienda = _get_or_create_tienda_for_user(request.user)

    if request.method == 'POST':
        mode = request.POST.get('mode', 'existing')  # 'existing' | 'new'
        if mode == 'existing':
            form_existing = ExistingProductOfferForm(request.POST)
            form_new = NewProductAndOfferForm()
            if form_existing.is_valid():
                producto = form_existing.cleaned_data['producto']
                precio = form_existing.cleaned_data['precio']
                url_externa = form_existing.cleaned_data.get('url_externa') or None
                stock = form_existing.cleaned_data.get('stock') or 0
                nota = form_existing.cleaned_data.get('nota_tienda') or ""

                oferta, created = TiendaProducto.objects.get_or_create(
                    tienda=tienda, producto=producto,
                    defaults={
                        'precio': precio,
                        'url_externa': url_externa,
                        'stock': stock,
                        'nota_tienda': nota,
                    }
                )
                if not created:
                    oferta.precio = precio
                    oferta.url_externa = url_externa
                    oferta.stock = stock
                    oferta.nota_tienda = nota
                    oferta.save()

                messages.success(request, "Oferta guardada correctamente.")
                return redirect('store_offers_list')

        else:
            form_existing = ExistingProductOfferForm()
            form_new = NewProductAndOfferForm(request.POST, request.FILES)
            if form_new.is_valid():
                nombre = form_new.cleaned_data['nombre_producto'].strip()
                modelo = form_new.cleaned_data['modelo_producto'].strip()
                descripcion = form_new.cleaned_data['descripcion_producto']
                imagen = form_new.cleaned_data.get('imagen_producto')
                marca = form_new.cleaned_data['marca_producto']
                categoria = form_new.cleaned_data['categoria_producto']
                tipo = form_new.cleaned_data['tipo_producto']

                precio = form_new.cleaned_data['precio']
                url_externa = form_new.cleaned_data.get('url_externa') or None
                stock = form_new.cleaned_data.get('stock') or 0
                nota = form_new.cleaned_data.get('nota_tienda') or ""

                # Anti-duplicado: marca + modelo (case-insensitive)
                producto = Producto.objects.filter(
                    marca_producto=marca,
                    modelo_producto__iexact=modelo
                ).first()
                if not producto:
                    producto = Producto.objects.create(
                        nombre_producto=nombre,
                        modelo_producto=modelo,
                        descripcion_producto=descripcion or "",
                        imagen_producto=imagen,
                        marca_producto=marca,
                        categoria_producto=categoria,
                        tipo_producto=tipo
                    )

                oferta, created = TiendaProducto.objects.get_or_create(
                    tienda=tienda, producto=producto,
                    defaults={
                        'precio': precio,
                        'url_externa': url_externa,
                        'stock': stock,
                        'nota_tienda': nota,
                    }
                )
                if not created:
                    oferta.precio = precio
                    oferta.url_externa = url_externa
                    oferta.stock = stock
                    oferta.nota_tienda = nota
                    oferta.save()

                messages.success(request, "Producto y oferta guardados correctamente.")
                return redirect('store_offers_list')
    else:
        form_existing = ExistingProductOfferForm()
    form_new = NewProductAndOfferForm(request.POST, request.FILES)
    if form_new.is_valid():
        modelo_disp = form_new._modelo_display          # p.ej. "Ryzen 5 5500"
        modelo_key  = form_new._modelo_key              # p.ej. "ryzen55500" -> (con regla, quedará "ryzen5500")
        nombre_auto = form_new._nombre_autogen          # p.ej. "AMD Ryzen 5 5500"

        descripcion = form_new.cleaned_data['descripcion_producto']
        imagen = form_new.cleaned_data.get('imagen_producto')
        marca = form_new.cleaned_data['marca_producto']
        categoria = form_new.cleaned_data['categoria_producto']
        tipo = form_new.cleaned_data['tipo_producto']

        precio = form_new.cleaned_data['precio']
        url_externa = form_new.cleaned_data.get('url_externa') or None
        stock = form_new.cleaned_data.get('stock') or 0
        nota = form_new.cleaned_data.get('nota_tienda') or ""

        # Buscar candidatos por marca, luego comparar con llave canónica
        candidatos = Producto.objects.filter(marca_producto=marca)
        producto = None
        for p in candidatos:
            if model_key(p.modelo_producto) == modelo_key:
                producto = p
                break

        if not producto:
            # crear producto nuevo con nombre autogenerado y modelo normalizado
            producto = Producto.objects.create(
                nombre_producto=nombre_auto,
                modelo_producto=modelo_disp,
                descripcion_producto=descripcion or "",
                imagen_producto=imagen,
                marca_producto=marca,
                categoria_producto=categoria,
                tipo_producto=tipo
            )

        oferta, created = TiendaProducto.objects.get_or_create(
            tienda=tienda, producto=producto,
            defaults={
                'precio': precio,
                'url_externa': url_externa,
                'stock': stock,
                'nota_tienda': nota,
            }
        )
        if not created:
            oferta.precio = precio
            oferta.url_externa = url_externa
            oferta.stock = stock
            oferta.nota_tienda = nota
            oferta.save()

        messages.success(request, "Producto y oferta guardados correctamente.")
        return redirect('store_offers_list')

    return render(request, 'store/offer_form.html', {
        'form_existing': form_existing,
        'form_new': form_new,
        'tienda': tienda,
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
            oferta.precio = precio
            oferta.save(update_fields=['precio'])
            messages.success(request, "Oferta actualizada.")
            return redirect('store_offers_list')
        except Exception:
            messages.error(request, "No se pudo actualizar el precio.")

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
    """Página standalone (útil para pruebas). El widget se incluye en base.html."""
    if "chat_history" not in request.session:
        request.session["chat_history"] = [{"role": "system", "content": SYSTEM_PROMPT}]
        request.session.modified = True
    return render(request, "chat.html")


@login_required
@require_POST
def chat_api(request):
    # Soporta JSON o form-data
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

    # Normalización ligera (sinónimos útiles)
    msg_norm = _normalize_for_matching(msg)

    # 0) INTENCIÓN: comparar
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
                "Te dejo la tabla de especificaciones. ¿Quieres que resuma las diferencias clave según tu uso?"
            )
            # Historial mínimo
            history = request.session.get("chat_history", [{"role": "system", "content": SYSTEM_PROMPT}])
            history = _truncate_history(history)
            history.append({"role": "user", "content": msg})
            history.append({"role": "assistant", "content": reply})
            request.session["chat_history"] = history
            request.session.modified = True
            return JsonResponse({"reply": reply, "comparacion": comp, "productos": [], "filtros_aplicados": []})
        # si no se encuentra alguno, dejamos seguir al flujo normal

    # 1) INTENCIÓN: ¿es saludo/charla ligera o no hay señales de compra?
    if not _intent_recommend(msg_norm):
        if _intent_smalltalk(msg_norm):
            reply = ("¡Hola! ¿Qué estás buscando hoy? "
                     "Puedo sugerirte por **categoría** (Gamer, Trabajo, Estudio, Diseño, Hogar) "
                     "y **tipo** (Notebook, Procesador, etc.). "
                     "Si me dices un **presupuesto**, afino la recomendación.")
        else:
            reply = ("Para ayudarte mejor, dime al menos la **categoría** (p. ej., Gamer) "
                     "y/o el **tipo de producto** (Notebook, Procesador) y, si puedes, tu **presupuesto**.")
        # historial
        history = request.session.get("chat_history", [{"role": "system", "content": SYSTEM_PROMPT}])
        history = _truncate_history(history)
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": reply})
        request.session["chat_history"] = history
        request.session.modified = True
        return JsonResponse({"reply": reply, "productos": [], "filtros_aplicados": []})

    # 2) Sticky de la sesión actual
    session = _get_or_create_chat_session(request)
    sticky_cats, sticky_types, sticky_budget = _get_sticky_filters(session)

    # 3) ¿El usuario mencionó explícitamente categoría/tipo?
    parsed_now = parse_requirements(request.user, msg_norm)
    cats_from_text = list(parsed_now["cat_text"])
    types_from_text = list(parsed_now["type_text"])

    # 4) Inferencia por sinónimos (respaldos)
    if not cats_from_text and _texto_contiene_gamer(msg):
        cid = _id_categoria("Gamer")
        if cid:
            cats_from_text = [cid]
    if not types_from_text and _texto_contiene_notebook(msg):
        tid = _id_tipo("Notebook")
        if tid:
            types_from_text = [tid]

    # 5) Sticky sólo si NO hubo mención/inferecia en este turno
    sticky_cats_turn = None if cats_from_text else sticky_cats
    sticky_types_turn = None if types_from_text else sticky_types

    # 6) Ajustamos msg_norm para consistencia con recommend_products
    if cats_from_text:
        msg_norm += " " + " ".join(["Gamer"] * len(cats_from_text))
    if types_from_text:
        msg_norm += " " + " ".join(["Notebook"] * len(types_from_text))

    # 7) Recomendación principal
    qs, filtros_ids = recommend_products(
        request.user,
        msg_norm,
        limit=6,
        sticky_cats=sticky_cats_turn,
        sticky_types=sticky_types_turn,
        sticky_budget=sticky_budget,
    )

    # 8) Heurística: evitar marca si el usuario la rechaza explícitamente
    lower = msg.lower()
    marcas_evitar = []
    for m in ["acer","huawei","apple","msi","asus","lenovo","hp","dell","samsung","xiaomi"]:
        if m in lower and any(kw in lower for kw in [" no ", "evit", "mala", "no quiero", "descarta", "odio"]):
            marcas_evitar.append(m)
    if marcas_evitar:
        qs = qs.exclude(marca_producto__nombre_marca__iregex="|".join(marcas_evitar))

    if qs.exists():
        # Guardar sticky
        _set_sticky_filters(session, filtros_ids)

        # ¿pide “el mejor”? + ¿estamos en Gamer+Notebook?
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

        # Chips legibles
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

        # Historial
        history = request.session.get("chat_history", [{"role": "system", "content": SYSTEM_PROMPT}])
        history = _truncate_history(history)
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": assistant})
        request.session["chat_history"] = history
        request.session.modified = True

        return JsonResponse({"reply": assistant, "productos": items, "filtros_aplicados": chips})

    # 9) Sin catálogo → pedir datos útiles
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
    # Resetea sólo el historial del chat.
    request.session["chat_history"] = [{"role": "system", "content": SYSTEM_PROMPT}]
    request.session.modified = True
    return JsonResponse({"ok": True})
