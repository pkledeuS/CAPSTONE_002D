# app/views_admin.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
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
    Tienda, TiendaProducto
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

    qs = (Producto.objects
          .select_related('categoria_producto')
          .annotate(
              tiendas_count=Count('tiendaproducto', distinct=True),
              precio_minimo=Min('tiendaproducto__precio')
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

    categorias = CategoriaProducto.objects.all()
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
    
    # Consultar reportes
    qs = Reporte.objects.all().select_related('producto', 'tienda', 'reporter')
    
    # Aplicar filtros
    if target == "productos":
        qs = qs.filter(target_type="producto")
    elif target == "tiendas":
        qs = qs.filter(target_type="tienda")
        
    # Corregir filtrado por estado
    if estado == "abiertos":
        qs = qs.filter(Q(estado='pendiente') | Q(estado='abierto'))
    elif estado == "resueltos":
        qs = qs.filter(estado='resuelto')
    # Si es "todos" no aplicamos filtro
    
    # Ordenar por fecha descendente
    qs = qs.order_by("-created_at")
    
    # Preparar filas para la tabla
    report_rows = []
    for r in qs:
        # Determinar estado y clase visual
        if r.estado == "resuelto":
            if hasattr(r, 'notificacion_leida') and r.notificacion_leida:
                estado_txt = "Resuelto - Actualizado"
                estado_class = "success"
            else:
                estado_txt = "Resuelto - Pendiente"
                estado_class = "info"
        else:
            estado_txt = "Abierto"
            estado_class = "warning"
            
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
    """Vista detallada de un reporte"""
    reporte = get_object_or_404(Reporte, pk=pk)
    
    if request.method == 'POST':
        accion = request.POST.get('accion')
        mensaje = request.POST.get('mensaje')
        deshabilitar = request.POST.get('deshabilitar') == 'on'
        
        # Obtener tiendas afectadas
        tiendas_afectadas = []
        if reporte.producto:
            tiendas_afectadas = TiendaProducto.objects.filter(producto=reporte.producto)
            
            # Manejar estado del producto
            producto = reporte.producto
            if deshabilitar:
                producto.is_active = False
                producto.save()
                # Registrar en el reporte que se deshabilitó
                reporte.producto_deshabilitado = True
            else:
                producto.is_active = True
                producto.save()
                reporte.producto_deshabilitado = False
        
        if accion == 'info_incorrecta':
            if reporte.producto:
                for tp in tiendas_afectadas:
                    Notificacion.objects.create(
                        tienda=tp.tienda,
                        tipo='info_incorrecta',
                        producto=reporte.producto,
                        mensaje=f"""
                        Se ha reportado información incorrecta en: {reporte.producto.nombre_producto}
                        
                        Motivo del reporte: {reporte.detalle}
                        Acción requerida: {mensaje}
                        Estado: {'Deshabilitado temporalmente' if deshabilitar else 'Activo'}
                        
                        Por favor, revise y actualice la información del producto.
                        """
                    )
                    
        elif accion == 'spam_delete':
            if reporte.producto:
                # Notificar antes de eliminar
                for tp in tiendas_afectadas:
                    Notificacion.objects.create(
                        tienda=tp.tienda,
                        tipo='producto_eliminado',
                        mensaje=f"""
                        El producto "{reporte.producto.nombre_producto}" ha sido eliminado.
                        
                        Motivo: Contenido inapropiado/spam
                        Detalles: {mensaje}
                        
                        Este producto ha sido eliminado de su catálogo.
                        """
                    )
                
                # Almacenar el ID antes de eliminar
                producto_id = reporte.producto.id
                reporte.producto = None  # Desvinculamos el producto antes de eliminarlo
                reporte.save()
                
                # Ahora sí eliminamos el producto
                Producto.objects.filter(id=producto_id).delete()
                
        elif accion == 'duplicado_merge':
            if reporte.producto:
                # Notificar duplicado
                for tp in tiendas_afectadas:
                    Notificacion.objects.create(
                        tienda=tp.tienda,
                        tipo='producto_duplicado',
                        producto=reporte.producto,
                        mensaje=f"""
                        El producto {reporte.producto.nombre_producto} ha sido marcado como duplicado.
                        
                        Por favor revise: {mensaje}
                        """
                    )
                    
        # Actualizar reporte
        reporte.estado = 'resuelto'
        reporte.accion_admin = mensaje
        reporte.fecha_accion = timezone.now()
        reporte.admin_actor = request.user
        reporte.save()

        return redirect('admin_reports')
        
    return render(request, 'admin_panel/report_detail.html', {
        'reporte': reporte
    })

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