# app/views_admin.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import (
    Q, Count, Avg, FloatField, F, 
    Value, CharField, Max, Min, ExpressionWrapper
)
from django.db.models.functions import Cast, Coalesce
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
import json

from .models import (
    CategoriaProducto, Notificacion, Producto, Reporte, 
    Tienda, TiendaProducto, TipoServicio
)

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

    # Modificamos el queryset para filtrar solo usuarios (no tiendas)
    qs = User.objects.filter(profile__profile_type='usuario').order_by("-date_joined")

    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
    if activo in {"0", "1"}:
        qs = qs.filter(is_active=(activo == "1"))

    # Agregamos select_related para optimizar
    qs = qs.select_related('profile')

    page_obj = _paginate(request, qs, per_page=20)
    context = {
        "page_obj": page_obj, 
        "pagination_html": "",
        "total_users": qs.count()
    }
    return render(request, "admin_panel/users.html", context)


# =========================
#        PRODUCTOS
# =========================
@staff_member_required
def admin_products(request):
    q = (request.GET.get("q") or "").strip()
    categoria_id = request.GET.get("categoria")
    activo = request.GET.get("activo")

    qs = (Producto.objects
          .select_related('categoria_producto')
          .annotate(
              tiendas_count=Count('tiendaproducto', distinct=True),
              precio=Min('tiendaproducto__precio')  # Cambiado a precio para coincidir con el template
          ))

    if q:
        qs = qs.filter(
            Q(nombre_producto__icontains=q) |
            Q(modelo_producto__icontains=q) |
            Q(categoria_producto__nombre_categoria__icontains=q)
        )

    if categoria_id:
        qs = qs.filter(categoria_producto_id=categoria_id)

    if activo in {"0", "1"}:
        qs = qs.filter(is_active=(activo == "1"))

    # Traer solo las categorías que tienen productos
    categorias = CategoriaProducto.objects.filter(
        id__in=Producto.objects.values('categoria_producto_id').distinct()
    ).order_by('nombre_categoria')

    page_obj = _paginate(request, qs.order_by('-id'), per_page=20)

    return render(request, "admin_panel/products.html", {
        'page_obj': page_obj,
        'categorias': categorias,
        'pagination_html': ""
    })


@staff_member_required
def admin_product_detail(request, pk):
    """Vista detallada de un producto para administradores"""
    producto = get_object_or_404(Producto, pk=pk)
    return render(request, 'admin_panel/product_detail.html', {
        'producto': producto
    })

@staff_member_required
def admin_product_toggle(request, pk):
    """Activa/desactiva un producto"""
    try:
        producto = get_object_or_404(Producto, pk=pk)
        estado_anterior = producto.is_active
        producto.is_active = not producto.is_active
        producto.save()
        
        estado = "activado" if producto.is_active else "desactivado"
        messages.success(request, f'Producto {estado} correctamente')
        
    except Exception as e:
        messages.error(request, f'Error al modificar el producto: {str(e)}')
    return redirect('admin_products')

@staff_member_required
def admin_product_delete(request, pk):
    """Elimina un producto"""
    try:
        producto = get_object_or_404(Producto, pk=pk)
        nombre = producto.nombre_producto
        producto.delete()
        messages.success(request, f'Producto "{nombre}" eliminado correctamente')
    except Exception as e:
        messages.error(request, f'Error al eliminar el producto: {str(e)}')
    return redirect('admin_products')


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

# =========================
#         REPORTES (Moderación)
# =========================

@staff_member_required
def admin_reports(request):
    """Vista del listado de reportes con filtros"""
    target = request.GET.get("target", "todos")
    estado = request.GET.get("estado", "abiertos")
    
    qs = Reporte.objects.all().select_related('producto', 'tienda', 'reporter')
    
    # Filtrar por objetivo
    if target == "productos":
        qs = qs.filter(target_type="producto")
    elif target == "tiendas":
        qs = qs.filter(target_type="tienda")
        
    # Filtrar por estado
    if estado == "abiertos":
        qs = qs.filter(estado='abierto')
    elif estado == "pendientes":
        qs = qs.filter(estado='pendiente')
    elif estado == "resueltos":
        qs = qs.filter(estado='resuelto')
    
    qs = qs.order_by("-created_at")
    
    report_rows = []
    for r in qs:
        # Determinar estado y clase visual
        if r.estado == "resuelto":
            estado_txt = "Resuelto"
            estado_class = "success"
        elif r.estado == "pendiente":
            estado_txt = "Pendiente de tienda"
            estado_class = "warning"
        else:
            estado_txt = "Nuevo"
            estado_class = "info"
            
        # Determinar objetivo
        if r.target_type == "producto" and r.producto:
            objetivo = r.producto.nombre_producto
        elif r.target_type == "tienda" and r.tienda:
            objetivo = r.tienda.nombre_tienda
        else:
            objetivo = "—"
            
        report_rows.append([
            r.get_target_type_display(),
            objetivo,
            r.get_motivo_display(),
            r.detalle[:160],
            r.reporter.username if r.reporter else "—",
            r.created_at.strftime("%Y-%m-%d %H:%M"),
            estado_txt,  # Cambiado para que coincida con el template
            r.pk
        ])
    
    context = {
        "report_columns": ["Tipo", "Objetivo", "Motivo", "Detalle", "Usuario", "Fecha", "Estado", "Acciones"],
        "report_rows": report_rows,
    }
    return render(request, "admin_panel/reports.html", context)

@staff_member_required
def admin_report_detail(request, pk):
    reporte = get_object_or_404(Reporte, pk=pk)
    
    if request.method == 'POST':
        accion = request.POST.get('accion')
        mensaje = request.POST.get('mensaje')
        deshabilitar = request.POST.get('deshabilitar') == 'on'
        
        # Cambiar estado a pendiente cuando se toma acción
        reporte.estado = 'pendiente'
        
        # Notificar según el tipo de reporte
        if reporte.target_type == 'producto':
            _handle_product_report(reporte, accion, mensaje, deshabilitar)
        else:  # tienda
            _handle_store_report(reporte, accion, mensaje)
            
        reporte.accion_admin = mensaje
        reporte.fecha_accion = timezone.now()
        reporte.admin_actor = request.user
        reporte.save()
        
        messages.success(request, 'Reporte procesado correctamente')
        return redirect('admin_reports')
        
    return render(request, 'admin_panel/report_detail.html', {
        'reporte': reporte
    })

def _handle_product_report(reporte, accion, mensaje, deshabilitar):
    """Maneja reportes de productos"""
    if not reporte.producto:
        return
    
    # Cambiar estado del producto según acción
    if accion == 'info_incorrecta':
        reporte.producto.is_active = not deshabilitar  # activa si NO es deshabilitar
        reporte.producto.save()
        
    elif accion == 'spam_delete':
        # Almacenar el ID antes de eliminar
        producto_id = reporte.producto.id
        reporte.producto = None  # Desvinculamos el producto antes de eliminarlo
        reporte.save()
        
        # Ahora sí eliminamos el producto
        Producto.objects.filter(id=producto_id).delete()
        
    elif accion == 'duplicado_merge':
        # Aquí podrías implementar la lógica para manejar duplicados,
        # como fusionar productos o marcar como duplicado.
        pass
    
    # Crear notificación para el producto
    Notificacion.objects.create(
        producto=reporte.producto,
        tipo=accion,
        mensaje=f"""
        Se ha reportado un problema con el producto:
        
        Motivo del reporte: {reporte.get_motivo_display()}
        Detalle: {reporte.detalle}
        
        Acción requerida: {mensaje}
        
        Por favor, tome las medidas necesarias y responda a este reporte.
        """,
    )

def _handle_store_report(reporte, accion, mensaje):
    """Maneja reportes de tiendas"""
    if not reporte.tienda:
        return
        
    # Crear notificación para la tienda
    Notificacion.objects.create(
        tienda=reporte.tienda,
        tipo=accion,
        mensaje=f"""
        Se ha reportado un problema con su tienda:
        
        Motivo del reporte: {reporte.get_motivo_display()}
        Detalle: {reporte.detalle}
        
        Acción requerida: {mensaje}
        
        Por favor, tome las medidas necesarias y responda a este reporte.
        """,
    )
    
    # Si es un reporte grave, podemos desactivar la tienda
    if accion in ['estafa', 'incumplimiento']:
        reporte.tienda.is_active = False
        reporte.tienda.save()

@staff_member_required
def admin_report_action(request, pk, action):
    """Acciones rápidas sobre reportes desde el listado"""
    reporte = get_object_or_404(Reporte, pk=pk)
    
    if action == 'resolve':
        reporte.estado = 'resuelto'
        reporte.save()
        messages.success(request, 'Reporte marcado como resuelto')
        
    elif action == 'open':
        reporte.estado = 'pendiente'
        reporte.save()
        messages.success(request, 'Reporte reabierto')
        
    elif action == 'delete':
        reporte.delete()
        messages.success(request, 'Reporte eliminado')
    
    return _redirect_back(request, 'admin_reports')

@staff_member_required
def admin_store_toggle(request, pk):
    """Activa/desactiva una tienda"""
    try:
        tienda = get_object_or_404(Tienda, pk=pk)
        estado_anterior = tienda.is_active
        tienda.is_active = not tienda.is_active
        tienda.save()
        
        estado = "activada" if tienda.is_active else "desactivada"
        messages.success(request, f'Tienda {estado} correctamente')
        
    except Exception as e:
        messages.error(request, f'Error al modificar la tienda: {str(e)}')
    return redirect('admin_stores')

@staff_member_required
def admin_store_delete(request, pk):
    """Elimina una tienda"""
    try:
        tienda = get_object_or_404(Tienda, pk=pk)
        nombre = tienda.nombre_tienda
        tienda.delete()
        messages.success(request, f'Tienda "{nombre}" eliminada correctamente')
    except Exception as e:
        messages.error(request, f'Error al eliminar la tienda: {str(e)}')
    return redirect('admin_stores')

@staff_member_required
def admin_store_detail(request, pk):
    """Vista detallada de una tienda"""
    tienda = get_object_or_404(Tienda, pk=pk)
    servicios = TipoServicio.objects.filter(tiendaservicio__tienda=tienda)
    categorias = CategoriaProducto.objects.filter(tiendacategoria__tienda=tienda)
    return render(request, 'admin_panel/store_detail.html', {
        'tienda': tienda,
        'servicios': servicios,
        'categorias': categorias
    })

@staff_member_required
def admin_user_toggle(request, pk):
    """Activa/desactiva un usuario"""
    try:
        user = get_object_or_404(User, pk=pk)
        estado_anterior = user.is_active
        user.is_active = not user.is_active
        user.save()
        
        estado = "activado" if user.is_active else "desactivado"
        messages.success(request, f'Usuario {estado} correctamente')
        
    except Exception as e:
        messages.error(request, f'Error al modificar el usuario: {str(e)}')
    return redirect('admin_users')

@staff_member_required
def admin_user_delete(request, pk):
    """Elimina un usuario"""
    try:
        user = get_object_or_404(User, pk=pk)
        if user.profile.profile_type != 'usuario':
            messages.error(request, 'Solo se pueden eliminar perfiles de usuario')
            return redirect('admin_users')
            
        username = user.username
        user.delete()
        messages.success(request, f'Usuario "{username}" eliminado correctamente')
    except Exception as e:
        messages.error(request, f'Error al eliminar el usuario: {str(e)}')
    return redirect('admin_users')

@staff_member_required
def admin_user_detail(request, pk):
    """Vista detallada de un usuario"""
    user = get_object_or_404(User, pk=pk)
    if user.profile.profile_type != 'usuario':
        messages.error(request, 'Solo se pueden ver perfiles de usuario')
        return redirect('admin_users')
        
    preferencias = user.preferenciausuario_set.all()
    
    return render(request, 'admin_panel/user_detail.html', {
        'user_detail': user,
        'preferencias': preferencias,
    })