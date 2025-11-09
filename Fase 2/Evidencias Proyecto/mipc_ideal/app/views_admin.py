from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Avg, Count, Min, Max, F, ExpressionWrapper, DecimalField
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import (
    Producto,
    CategoriaProducto,
    TipoProducto,
    MarcaProducto,
    ProductReference,
    Profile,
    Reporte,
    ProductReview,
    PreferenciaUsuario,
)

User = get_user_model()


def _paginate(request, queryset, per_page=20):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)
    return page_obj, _render_pagination(request, page_obj)


def _render_pagination(request, page_obj):
    if page_obj.paginator.num_pages <= 1:
        return ""
    buttons = []
    for num in page_obj.paginator.page_range:
        is_current = "active" if num == page_obj.number else ""
        params = request.GET.copy()
        params["page"] = num
        query = params.urlencode()
        url = f"?{query}" if query else "?"
        buttons.append(
            f"<li class='page-item {is_current}'><a class='page-link' href='{url}'>{num}</a></li>"
        )
    return "<nav><ul class='pagination pagination-sm justify-content-end'>" + "".join(buttons) + "</ul></nav>"


@staff_member_required
def admin_dashboard(request):
    return redirect(reverse("admin_analytics"))


@staff_member_required
def admin_analytics(request):
    top_views = Producto.objects.order_by("-vistas", "-id")[:10]
    top_rated = (
        Producto.objects.annotate(avg_rating=Avg("reviews__rating"), reviews_count=Count("reviews"))
        .filter(reviews_count__gt=0)
        .order_by("-avg_rating")[:10]
    )
    price_spread = (
        Producto.objects.annotate(
            min_price=Min("referencias__precio"),
            max_price=Max("referencias__precio"),
            spread=ExpressionWrapper(
                F("max_price") - F("min_price"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
        .filter(min_price__isnull=False, max_price__isnull=False)
        .order_by("-spread")[:10]
    )
    context = {
        "top_views": top_views,
        "top_rated": top_rated,
        "price_spread": price_spread,
    }
    return render(request, "admin_panel/analytics.html", context)


@staff_member_required
def admin_products(request):
    qs = Producto.objects.select_related("categoria_producto", "tipo_producto", "marca_producto")
    q = (request.GET.get("q") or "").strip()
    categoria_id = request.GET.get("categoria")
    activo = request.GET.get("activo")

    if q:
        qs = qs.filter(
            models.Q(nombre_producto__icontains=q)
            | models.Q(modelo_producto__icontains=q)
            | models.Q(marca_producto__nombre_marca__icontains=q)
        )
    if categoria_id:
        qs = qs.filter(categoria_producto_id=categoria_id)
    if activo == "1":
        qs = qs.filter(is_active=True)
    elif activo == "0":
        qs = qs.filter(is_active=False)

    qs = qs.annotate(
        precio=Min("referencias__precio"),
        tiendas_count=Count("referencias", distinct=True),
    ).order_by("nombre_producto")

    page_obj, pagination_html = _paginate(request, qs)
    context = {
        "page_obj": page_obj,
        "categorias": CategoriaProducto.objects.all(),
        "pagination_html": pagination_html,
    }
    return render(request, "admin_panel/products.html", context)


@staff_member_required
def admin_product_detail(request, pk):
    producto = get_object_or_404(
        Producto.objects.select_related("marca_producto", "categoria_producto", "tipo_producto"), pk=pk
    )
    referencias = ProductReference.objects.filter(producto=producto)
    reviews = ProductReview.objects.filter(producto=producto).select_related("user")
    context = {
        "producto": producto,
        "referencias": referencias,
        "reviews": reviews,
    }
    return render(request, "admin_panel/product_detail.html", context)


@staff_member_required
def admin_product_toggle(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    producto.is_active = not producto.is_active
    producto.save(update_fields=["is_active"])
    messages.success(request, "Estado del producto actualizado.")
    return redirect(reverse("admin_products"))


@staff_member_required
def admin_product_delete(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    producto.delete()
    messages.success(request, "Producto eliminado correctamente.")
    return redirect(reverse("admin_products"))


@staff_member_required
def admin_users(request):
    qs = User.objects.all().select_related("profile")
    q = (request.GET.get("q") or "").strip()
    activo = request.GET.get("activo")
    if q:
        qs = qs.filter(models.Q(username__icontains=q) | models.Q(email__icontains=q))
    if activo == "1":
        qs = qs.filter(is_active=True)
    elif activo == "0":
        qs = qs.filter(is_active=False)

    page_obj, pagination_html = _paginate(request, qs.order_by("username"))
    context = {
        "page_obj": page_obj,
        "pagination_html": pagination_html,
    }
    return render(request, "admin_panel/users.html", context)


@staff_member_required
def admin_user_detail(request, pk):
    user = get_object_or_404(User.objects.select_related("profile"), pk=pk)
    preferencias = PreferenciaUsuario.objects.filter(usuario=user).select_related("categoria", "tipo_producto")
    context = {
        "usuario": user,
        "preferencias": preferencias,
    }
    return render(request, "admin_panel/user_detail.html", context)


@staff_member_required
def admin_user_toggle(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, "Estado del usuario actualizado.")
    return redirect(reverse("admin_users"))


@staff_member_required
def admin_user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.delete()
    messages.success(request, "Usuario eliminado correctamente.")
    return redirect(reverse("admin_users"))


@staff_member_required
def admin_reports(request):
    estado = request.GET.get("estado") or "abiertos"
    qs = Reporte.objects.select_related("producto", "reporter")
    if estado == "pendientes":
        qs = qs.filter(estado="pendiente")
    elif estado == "resueltos":
        qs = qs.filter(estado="resuelto")
    elif estado == "todos":
        pass
    else:
        qs = qs.filter(estado="abierto")

    qs = qs.order_by("-created_at")
    page_obj, pagination_html = _paginate(request, qs)
    report_rows = []
    for r in page_obj:
        report_rows.append((
            r.get_target_type_display(),
            r.producto.nombre_producto if r.producto else "-",
            r.get_motivo_display(),
            (r.detalle or "")[:120],
            r.reporter.username if r.reporter else "Anon",
            timezone.localtime(r.created_at).strftime("%d-%m-%Y %H:%M"),
            r.get_estado_display(),
            r.id,
        ))

    context = {
        "page_obj": page_obj,
        "report_rows": report_rows,
        "pagination_html": pagination_html,
        "estado": estado,
    }
    return render(request, "admin_panel/reports.html", context)


@staff_member_required
def admin_report_detail(request, pk):
    reporte = get_object_or_404(Reporte.objects.select_related("producto", "reporter"), pk=pk)
    context = {
        "reporte": reporte,
    }
    return render(request, "admin_panel/report_detail.html", context)


@staff_member_required
def admin_report_action(request, pk, action):
    reporte = get_object_or_404(Reporte, pk=pk)
    if action == "resolver":
        reporte.estado = "resuelto"
        reporte.accion_admin = request.POST.get("accion_admin", "")
        reporte.admin_actor = request.user
        reporte.fecha_accion = timezone.now()
        reporte.save()
        messages.success(request, "Reporte marcado como resuelto.")
    elif action == "pendiente":
        reporte.estado = "pendiente"
        reporte.admin_actor = request.user
        reporte.fecha_accion = timezone.now()
        reporte.save()
        messages.success(request, "Reporte marcado como pendiente.")
    return redirect(reverse("admin_report_detail", args=[pk]))
