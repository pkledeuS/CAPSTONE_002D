# app/views_admin.py
from __future__ import annotations

import json
from typing import Any, Iterable

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg, FloatField, F, Value, CharField, Max, Min, ExpressionWrapper
from django.db.models.functions import Cast, Coalesce
from django.shortcuts import render, redirect
from django.urls import reverse

from .models import Producto, Tienda


# =========================
#     UTILIDADES / INTROS
# =========================
def _paginate(request, queryset, per_page: int = 20):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page") or 1
    return paginator.get_page(page_number)


def _redirect_back(request, fallback_name: str):
    next_url = request.GET.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect(reverse(fallback_name))


def _field_names(model):
    return {f.name for f in model._meta.get_fields()}


# --- Campos detectados dinámicamente en Producto ---
_PROD_FIELDS = _field_names(Producto)

# Nombre visible del producto
NAME_FIELD = (
    "nombre_producto" if "nombre_producto" in _PROD_FIELDS
    else ("nombre" if "nombre" in _PROD_FIELDS else None)
)

# Campo de activo
ACTIVE_FIELD = (
    "is_active" if "is_active" in _PROD_FIELDS
    else ("activo" if "activo" in _PROD_FIELDS else None)
)

# ForeignKey a categoría
CATEGORY_FK = (
    "categoria_producto" if "categoria_producto" in _PROD_FIELDS
    else ("categoria" if "categoria" in _PROD_FIELDS else None)
)

# Métrica numérica para promediar en Analytics
if "precio_minimo" in _PROD_FIELDS:
    NUMERIC_METRIC = "precio_minimo"
elif "vistas" in _PROD_FIELDS:
    NUMERIC_METRIC = "vistas"
else:
    NUMERIC_METRIC = None  # sin métrica numérica; se hará conteo

# Relación reverse a tiendas (según tus choices: 'tiendaproducto')
HAS_REL_TP = "tiendaproducto" in _PROD_FIELDS

# Nombre del campo "nombre" en la categoría relacionada
CategoriaModel = None
CATEGORY_NAME_FIELD = None
if CATEGORY_FK:
    CategoriaModel = Producto._meta.get_field(CATEGORY_FK).remote_field.model
    _CAT_FIELDS = _field_names(CategoriaModel)
    if "nombre_categoria" in _CAT_FIELDS:
        CATEGORY_NAME_FIELD = "nombre_categoria"
    elif "nombre" in _CAT_FIELDS:
        CATEGORY_NAME_FIELD = "nombre"
    else:
        CATEGORY_NAME_FIELD = None


# =========================
#        DASHBOARD
# =========================
@staff_member_required
def admin_dashboard(request):
    """
    No redirige. Renderiza el panel directamente con la plantilla de Analytics,
    manteniendo la URL /admin-panel/ y mostrando el sidebar del admin_base.
    """
    return render(request, "admin_panel/analytics.html")


# =========================
#        ANALYTICS
# =========================
@staff_member_required
def admin_analytics(request):
    """
    Métricas enfocadas a catálogo (no ventas):
      A) Top 10 más vistos (Producto.vistas)
      B) Top 10 mejor valorados (promedio de rating en relación 'reviews')
      C) Top 10 mayor variación de precios entre tiendas (spread max-min en relación 'tiendaproducto')
    """
    # ---------- A) Top más vistos ----------
    top_views_labels, top_views_values = [], []
    if "vistas" in _PROD_FIELDS:
        qs_views = Producto.objects.all().order_by("-vistas", "-id")[:10]
        top_views_labels = [
            getattr(p, NAME_FIELD, str(p.pk)) if NAME_FIELD else str(p.pk) for p in qs_views
        ]
        top_views_values = [int(getattr(p, "vistas", 0)) for p in qs_views]

    # ---------- B) Top mejor valorados ----------
    # Detecta si existe relación reverse 'reviews' y un campo de calificación usable
    top_rated_labels, top_rated_values = [], []
    REV_REL = "reviews" if "reviews" in _PROD_FIELDS else None
    rating_field_name = None

    if REV_REL:
        ReviewModel = Producto._meta.get_field(REV_REL).remote_field.model
        _REV_FIELDS = {f.name for f in ReviewModel._meta.get_fields()}
        # candidatos comunes de rating
        for cand in ("rating", "valoracion", "calificacion", "estrellas", "score", "puntuacion"):
            if cand in _REV_FIELDS:
                rating_field_name = cand
                break

    if REV_REL and rating_field_name:
        qs_rating = (
            Producto.objects
            .annotate(avg_rating=Avg(Cast(F(f"{REV_REL}__{rating_field_name}"), FloatField())))
            .exclude(avg_rating__isnull=True)
            .order_by("-avg_rating", "-id")[:10]
        )
        top_rated_labels = [
            getattr(p, NAME_FIELD, str(p.pk)) if NAME_FIELD else str(p.pk) for p in qs_rating
        ]
        # Redondeo a 2 decimales para mostrar limpio
        top_rated_values = [round(float(getattr(p, "avg_rating") or 0.0), 2) for p in qs_rating]

    # ---------- C) Top mayor variación de precios entre tiendas ----------
    # Usamos spread = max(precio) - min(precio) sobre relación 'tiendaproducto'
    price_spread_labels, price_spread_values = [], []
    if HAS_REL_TP:
        TPModel = Producto._meta.get_field("tiendaproducto").remote_field.model
        _TP_FIELDS = {f.name for f in TPModel._meta.get_fields()}

        # candidatos de precio en la tabla intermedia
        price_field = None
        for cand in ("precio", "precio_actual", "price", "precio_venta", "precio_tienda"):
            if cand in _TP_FIELDS:
                price_field = cand
                break

        if price_field:
            qs_spread = (
                Producto.objects
                .annotate(
                    max_p=Max(Cast(F(f"tiendaproducto__{price_field}"), FloatField())),
                    min_p=Min(Cast(F(f"tiendaproducto__{price_field}"), FloatField())),
                )
                .annotate(
                    spread=ExpressionWrapper(
                        Coalesce(F("max_p"), Value(0.0, output_field=FloatField()))
                        - Coalesce(F("min_p"), Value(0.0, output_field=FloatField())),
                        output_field=FloatField(),
                    )
                )
                .order_by("-spread", "-id")[:10]
            )
            price_spread_labels = [
                getattr(p, NAME_FIELD, str(p.pk)) if NAME_FIELD else str(p.pk) for p in qs_spread
            ]
            price_spread_values = [float(getattr(p, "spread") or 0.0) for p in qs_spread]

    # Empaquetamos contexto para 3 charts
    context = {
        # A) Vistas
        "top_views_labels": json.dumps(top_views_labels, ensure_ascii=False),
        "top_views_values": json.dumps(top_views_values),

        # B) Ratings
        "top_rated_labels": json.dumps(top_rated_labels, ensure_ascii=False),
        "top_rated_values": json.dumps(top_rated_values),

        # C) Spread precios
        "price_spread_labels": json.dumps(price_spread_labels, ensure_ascii=False),
        "price_spread_values": json.dumps(price_spread_values),
    }
    return render(request, "admin_panel/analytics.html", context)


# =========================
#         TIENDAS
# =========================
@staff_member_required
def admin_stores(request):
    q = (request.GET.get("q") or "").strip()
    estado = request.GET.get("estado")

    qs = Tienda.objects.all()

    # Alias para plantilla (tienda.nombre / tienda.activa / tienda.url)
    if TIENDA_NAME_FIELD and TIENDA_NAME_FIELD != "nombre":
        qs = qs.annotate(nombre=F(TIENDA_NAME_FIELD))
    if TIENDA_ACTIVE_FIELD and TIENDA_ACTIVE_FIELD != "activa":
        qs = qs.annotate(activa=F(TIENDA_ACTIVE_FIELD))
    if TIENDA_URL_FIELD:
        # Usa el campo real si existe como 'url'
        pass
    else:
        # No hay URL en el modelo: expone alias vacío para que el template no falle
        qs = qs.annotate(url=Value("", output_field=CharField()))

    # Búsqueda por nombre / email / dirección (ajustado a tus fields reales)
    if q:
        filtro = Q()
        if TIENDA_NAME_FIELD:
            filtro |= Q(**{f"{TIENDA_NAME_FIELD}__icontains": q})
        if "email_tienda" in _STORE_FIELDS:
            filtro |= Q(email_tienda__icontains=q)
        if "direccion_tienda" in _STORE_FIELDS:
            filtro |= Q(direccion_tienda__icontains=q)
        qs = qs.filter(filtro)

    # Filtro por estado (1/0) si existe campo activo
    if estado in {"0", "1"} and TIENDA_ACTIVE_FIELD:
        qs = qs.filter(**{TIENDA_ACTIVE_FIELD: (estado == "1")})

    # Conteo de productos asociados
    if TIENDA_REL_PRODUCTOS:
        qs = qs.annotate(productos_count=Count(TIENDA_REL_PRODUCTOS, distinct=True))
    else:
        qs = qs.annotate(productos_count=Count("id"))  # fallback neutro

    # Orden por nombre si existe, si no por id
    if TIENDA_NAME_FIELD:
        qs = qs.order_by(TIENDA_NAME_FIELD)
    else:
        qs = qs.order_by("id")

    page_obj = _paginate(request, qs, per_page=20)
    context = {
        "page_obj": page_obj,
        "pagination_html": "",
    }
    return render(request, "admin_panel/stores.html", context)

# --- Campos detectados dinámicamente en Tienda ---
def _store_field_names(model):
    return {f.name for f in model._meta.get_fields()}

_STORE_FIELDS = _store_field_names(Tienda)

TIENDA_NAME_FIELD = (
    "nombre_tienda" if "nombre_tienda" in _STORE_FIELDS
    else ("nombre" if "nombre" in _STORE_FIELDS else None)
)

TIENDA_ACTIVE_FIELD = (
    "is_active" if "is_active" in _STORE_FIELDS
    else ("activa" if "activa" in _STORE_FIELDS else None)
)

# Campo URL si existe; en tu modelo no aparece, así que será None y pondremos alias vacío
TIENDA_URL_FIELD = "url" if "url" in _STORE_FIELDS else None

# Relación reverse a productos desde Tienda (según tus choices: 'tiendaproducto')
TIENDA_REL_PRODUCTOS = "tiendaproducto" if "tiendaproducto" in _STORE_FIELDS else None

# =========================
#         USUARIOS
# =========================
@staff_member_required
def admin_users(request):
    User = get_user_model()
    q = (request.GET.get("q") or "").strip()
    activo = request.GET.get("activo")

    qs = User.objects.all().order_by("-date_joined")
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
    if activo in {"0", "1"}:
        qs = qs.filter(is_active=(activo == "1"))

    page_obj = _paginate(request, qs, per_page=20)
    context = {"page_obj": page_obj, "pagination_html": ""}
    return render(request, "admin_panel/users.html", context)


# =========================
#        PRODUCTOS
# =========================
@staff_member_required
def admin_products(request):
    q = (request.GET.get("q") or "").strip()
    categoria_id = request.GET.get("categoria")
    activo = request.GET.get("activo")

    qs = Producto.objects.all()

    # Alias para plantilla (p.nombre / p.activo)
    if NAME_FIELD and NAME_FIELD != "nombre":
        qs = qs.annotate(nombre=F(NAME_FIELD))
    if ACTIVE_FIELD and ACTIVE_FIELD != "activo":
        qs = qs.annotate(activo=F(ACTIVE_FIELD))

    # Conteo de tiendas
    if HAS_REL_TP:
        qs = qs.annotate(tiendas_count=Count("tiendaproducto", distinct=True))
    else:
        qs = qs.annotate(tiendas_count=Count("id"))  # fallback neutro

    if CATEGORY_FK:
        qs = qs.select_related(CATEGORY_FK)

    # Filtro texto
    if q:
        or_filter = Q(**{f"{NAME_FIELD or 'id'}__icontains": q}) if NAME_FIELD else Q(pk__icontains=q)
        if CATEGORY_FK and CATEGORY_NAME_FIELD:
            or_filter |= Q(**{f"{CATEGORY_FK}__{CATEGORY_NAME_FIELD}__icontains": q})
        qs = qs.filter(or_filter)

    # Filtro categoría
    if CATEGORY_FK and categoria_id:
        qs = qs.filter(**{f"{CATEGORY_FK}_id": categoria_id})

    # Filtro activo
    if activo in {"0", "1"} and ACTIVE_FIELD:
        qs = qs.filter(**{ACTIVE_FIELD: (activo == "1")})

    page_obj = _paginate(request, qs.order_by("-id"), per_page=20)

    # Categorías para el <select>
    if CATEGORY_FK and CategoriaModel and CATEGORY_NAME_FIELD:
        categorias_qs = CategoriaModel.objects.only("id", CATEGORY_NAME_FIELD).order_by(CATEGORY_NAME_FIELD)
        # Anota alias 'nombre' para plantilla ({{ c.nombre }})
        categorias = categorias_qs.annotate(nombre=F(CATEGORY_NAME_FIELD))
    else:
        categorias = []

    context = {
        "page_obj": page_obj,
        "categorias": categorias,
        "pagination_html": "",
    }
    return render(request, "admin_panel/products.html", context)


@staff_member_required
def admin_products_toggle(request, pk: int):
    try:
        p = Producto.objects.get(pk=pk)
        # Determina el campo booleano a cambiar
        field_name = ACTIVE_FIELD or ("activo" if hasattr(p, "activo") else "is_active")
        current = bool(getattr(p, field_name))
        setattr(p, field_name, not current)
        p.save(update_fields=[field_name])
    except Producto.DoesNotExist:
        pass
    return _redirect_back(request, "admin_products")


@staff_member_required
def admin_products_delete(request, pk: int):
    try:
        Producto.objects.filter(pk=pk).delete()
    except Exception:
        pass
    return _redirect_back(request, "admin_products")


# =========================
#         REPORTES (Moderación)
# =========================
from django.utils.timezone import localtime

def _get_reverse_model(base_model, reverse_name_candidates):
    """Dado un modelo base (Producto/Tienda), intenta resolver un related_name de reportes y retorna el modelo Reporte."""
    for rel in base_model._meta.get_fields():
        if not getattr(rel, "is_relation", False):
            continue
        if not getattr(rel, "one_to_many", False):  # buscamos ManyToOneRel (FK desde Reporte a Producto/Tienda)
            continue
        if getattr(rel, "related_name", None) in reverse_name_candidates or getattr(rel, "name", None) in reverse_name_candidates:
            return rel.related_model
    return None

def _pick_attr(obj, candidates, default=None):
    for c in candidates:
        if hasattr(obj, c):
            val = getattr(obj, c)
            return val() if callable(val) else val
    return default

def _datefmt(dt):
    try:
        return localtime(dt).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt) if dt is not None else "—"

@staff_member_required
def admin_reports(request):
    """
    Moderación de reportes enviados por usuarios sobre Productos o Tiendas.
    - target: productos | tiendas | todos
    - estado: abiertos | resueltos | todos
    Muestra columnas: Tipo, Objetivo, Motivo, Detalle, Usuario, Fecha, Estado, Acciones.
    """
    target = (request.GET.get("target") or "todos").lower()
    estado = (request.GET.get("estado") or "abiertos").lower()

    filas = []

    # Detecta modelos de reporte (reverse) tanto en Producto como en Tienda
    product_report_model = _get_reverse_model(Producto, {"reporte", "reportes", "reports"})
    store_report_model   = _get_reverse_model(Tienda,   {"reporte", "reportes", "reports"})

    # Helper para procesar un queryset de reportes homogéneo
    def collect_rows(qs, tipo):
        rows = []
        for r in qs[:1000]:
            # Descubrir campos comunes en el modelo de reporte
            motivo   = _pick_attr(r, ["motivo", "razon", "reason", "asunto"], default="—")
            detalle  = _pick_attr(r, ["detalle", "descripcion", "comentario", "observacion", "notes"], default="—")
            usuario  = _pick_attr(r, ["user", "usuario", "reporter", "autor", "creator"], default=None)
            fecha    = _pick_attr(r, ["created_at", "fecha", "fecha_creacion", "created", "timestamp"], default=None)

            # Estado/resuelto
            is_resolved = None
            if hasattr(r, "is_resolved"):
                is_resolved = bool(getattr(r, "is_resolved"))
            elif hasattr(r, "resuelto"):
                is_resolved = bool(getattr(r, "resuelto"))
            elif hasattr(r, "estado"):
                # intenta mapear strings tipo "resuelto"/"abierto"
                val = str(getattr(r, "estado") or "").lower()
                if val in {"resuelto", "cerrado", "solucionado"}:
                    is_resolved = True
                elif val in {"abierto", "pendiente"}:
                    is_resolved = False

            estado_txt = "Resuelto" if is_resolved else "Abierto"

            # Obtener objeto objetivo y su nombre
            target_obj = None
            target_name = "—"
            if tipo == "Producto":
                target_obj = _pick_attr(r, ["producto", "product"], default=None)
                if target_obj:
                    nm = getattr(target_obj, (NAME_FIELD or ""), None)
                    target_name = nm if nm else f"Producto #{getattr(target_obj, 'pk', '—')}"
            else:
                target_obj = _pick_attr(r, ["tienda", "store"], default=None)
                if target_obj:
                    nm = getattr(target_obj, (TIENDA_NAME_FIELD or ""), None)
                    target_name = nm if nm else f"Tienda #{getattr(target_obj, 'pk', '—')}"

            rows.append([
                tipo,
                target_name,
                str(motivo)[:120],
                str(detalle)[:160],
                getattr(usuario, "username", str(usuario)) if usuario else "—",
                _datefmt(fecha),
                estado_txt,
                # Acción: construimos URLs en plantilla con pk y acción
                r.pk,
            ])
        return rows

    # Construir querysets según filtros
    if target in {"productos", "todos"} and product_report_model:
        qs_p = product_report_model.objects.all()
        # Filtros por estado
        if estado in {"abiertos", "resueltos"}:
            # intenta filtrado por booleans convencionales
            if "is_resolved" in {f.name for f in product_report_model._meta.get_fields()}:
                qs_p = qs_p.filter(is_resolved=(estado == "resueltos"))
            elif "resuelto" in {f.name for f in product_report_model._meta.get_fields()}:
                qs_p = qs_p.filter(resuelto=(estado == "resueltos"))
            elif "estado" in {f.name for f in product_report_model._meta.get_fields()}:
                # textual
                if estado == "resueltos":
                    qs_p = qs_p.filter(estado__in=["resuelto", "cerrado", "solucionado"])
                else:
                    qs_p = qs_p.filter(estado__in=["abierto", "pendiente"])
        qs_p = qs_p.order_by("-id")
        filas += collect_rows(qs_p, "Producto")

    if target in {"tiendas", "todos"} and store_report_model:
        qs_t = store_report_model.objects.all()
        if estado in {"abiertos", "resueltos"}:
            if "is_resolved" in {f.name for f in store_report_model._meta.get_fields()}:
                qs_t = qs_t.filter(is_resolved=(estado == "resueltos"))
            elif "resuelto" in {f.name for f in store_report_model._meta.get_fields()}:
                qs_t = qs_t.filter(resuelto=(estado == "resueltos"))
            elif "estado" in {f.name for f in store_report_model._meta.get_fields()}:
                if estado == "resueltos":
                    qs_t = qs_t.filter(estado__in=["resuelto", "cerrado", "solucionado"])
                else:
                    qs_t = qs_t.filter(estado__in=["abierto", "pendiente"])
        qs_t = qs_t.order_by("-id")
        filas += collect_rows(qs_t, "Tienda")

    # Orden final por “fecha/ID” descendente (las filas son listas; última col es pk, penúltima es estado, antepenúltima fecha formateada)
    # Ya ordenamos por id desc en cada qs; mantener tal cual.
    report_columns = ["Tipo", "Objetivo", "Motivo", "Detalle", "Usuario", "Fecha", "Estado", "Acciones"]
    report_rows = filas

    context = {
        "report_columns": report_columns,
        "report_rows": report_rows,
        "download_url": None,
    }
    return render(request, "admin_panel/reports.html", context)


@staff_member_required
def admin_reports_mark(request, pk: int, action: str):
    """
    Marca/gestiona un reporte:
      - action = resolve | open | delete
    Busca en ambos modelos de reportes (producto/tienda) y aplica el cambio si corresponde.
    """
    # Detectar modelos de reporte
    product_report_model = _get_reverse_model(Producto, {"reporte", "reportes", "reports"})
    store_report_model   = _get_reverse_model(Tienda,   {"reporte", "reportes", "reports"})

    def act_on(model):
        if not model:
            return False
        obj = model.objects.filter(pk=pk).first()
        if not obj:
            return False

        if action == "delete":
            obj.delete()
            return True

        # toggles/estado
        if hasattr(obj, "is_resolved"):
            obj.is_resolved = (action == "resolve")
            obj.save(update_fields=["is_resolved"])
            return True
        if hasattr(obj, "resuelto"):
            obj.resuelto = (action == "resolve")
            obj.save(update_fields=["resuelto"])
            return True
        if hasattr(obj, "estado"):
            obj.estado = "resuelto" if action == "resolve" else "abierto"
            obj.save(update_fields=["estado"])
            return True
        return False

    # Intenta en ambos modelos
    changed = act_on(product_report_model) or act_on(store_report_model)
    return _redirect_back(request, "admin_reports")