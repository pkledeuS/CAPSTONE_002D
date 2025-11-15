from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Avg, Count, Min, Max, F, ExpressionWrapper, DecimalField
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import AdminProductForm, ProductReferenceFormSet, ProductSpecFormSet
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
    ProductoVisto,
    ReferenceVisit,
)

User = get_user_model()

SPEC_TEMPLATES = {
    "Procesador": [
        "Frecuencia",
        "Frecuencia turbo máxima",
        "Núcleos / hilos",
        "Caché",
        "Socket",
        "Núcleo",
        "Proceso de manufactura",
        "TDP",
        "Cooler",
        "Gráficos integrados",
    ],
    "Memoria RAM": [
        "Capacidad",
        "Tipo",
        "Velocidad",
        "Formato",
        "Voltaje",
        "Latencia CI (CAS)",
        "Latencia Trcd",
        "Latencia Trp",
        "Latencia Tras",
        "Soporte ECC",
        "Soporte full buffered",
    ],
    "Fuente de poder": [
        "Potencia",
        "Certificación",
        "Tamaño",
        "PFC activo",
        "Modular",
        "Corriente en la línea de 12V",
        "Corriente en la línea de 5V",
        "Corriente en la línea de 3.3V",
    ],
    "Notebook": [
        "Procesador",
        "Núcleos",
        "RAM",
        "Pantalla",
        "Batería",
        "Almacenamiento",
        "Tarjeta de Video",
        "Puertos",
        "Peso",
        "SO",
        "Idioma teclado",
    ],
    "All-in-One": [
        "Procesador",
        "Núcleos",
        "RAM",
        "Pantalla",
        "Almacenamiento",
        "Tarjeta de Video",
        "Puertos",
        "Peso",
        "SO",
        "Periféricos inalámbricos",
    ],
    "Tablet": [
        "Part number",
        "Pantalla",
        "Memoria interna",
        "RAM",
        "Conectividad celular",
        "Sistema operativo",
        "Color",
        "Peso",
        "Dimensiones",
        "Almacenamiento externo",
        "Batería",
        "Cámara principal",
        "Cámara frontal",
        "GPS",
        "Bluetooth",
        "Salida de audífonos",
        "Procesador",
        "CPU",
        "GPU",
    ],
    "Tarjetas Gráficas": [
        "Fabricante",
        "GPU",
        "Memoria",
        "Bus",
        "Frecuencias core (base / boost / OC)",
        "Frecuencia memorias",
        "Núcleo",
        "Perfil",
        "Refrigeración",
        "Slots",
        "Largo",
        "Iluminación",
        "¿Backplate?",
        "Conectores de poder",
        "Puertos de video",
    ],
}

SPEC_PLACEHOLDERS = {
    "Frecuencia": "3600 MHz",
    "Frecuencia turbo máxima": "4200 MHz",
    "Núcleos / hilos": "6 núcleos / 12 hilos",
    "Caché": "6 x 512KB L2 / 16MB L3",
    "Socket": "AM4",
    "Núcleo": "AMD Cezanne (Zen 3)",
    "Proceso de manufactura": "7 nm",
    "TDP": "65 W",
    "Cooler": "Wraith Stealth",
    "Gráficos integrados": "Radeon Vega 8",
    "Capacidad": "1 x 16 GB",
    "Tipo": "DDR4",
    "Velocidad": "3200 MT/s",
    "Formato": "DIMM",
    "Voltaje": "1.35 V",
    "Latencia CI (CAS)": "16",
    "Latencia Trcd": "18",
    "Latencia Trp": "18",
    "Latencia Tras": "32",
    "Soporte ECC": "No",
    "Soporte full buffered": "No",
    "Potencia": "650 W",
    "Certificación": "80 PLUS Gold",
    "Tamaño": "ATX",
    "PFC activo": "Sí",
    "Modular": "Sí",
    "Corriente en la línea de 12V": "54 A",
    "Corriente en la línea de 5V": "15 A",
    "Corriente en la línea de 3.3V": "15 A",
    "Procesador": "AMD Ryzen 5 5600H",
    "Núcleos": "6 núcleos / 12 hilos",
    "RAM": "16 GB DDR4 (3200 MHz)",
    "Pantalla": "LED 15.6\" FHD (1920x1080) / 144 Hz",
    "Batería": "60000 mWh",
    "Almacenamiento": "SSD 512 GB",
    "Tarjeta de Video": "NVIDIA GeForce GTX 1650",
    "Puertos": "USB-C, USB-A, HDMI, Jack 3.5mm",
    "Peso": "2389 g",
    "SO": "Windows 11 Home",
    "Idioma teclado": "Español",
    "Procesador (AIO)": "AMD Ryzen 7 7730U",
    "RAM (AIO)": "16 GB",
    "Pantalla (AIO)": "LED 27.0\" FullHD (1920x1080)",
    "Almacenamiento (AIO)": "SSD 512 GB",
    "Tarjeta de Video (AIO)": "AMD Radeon RX Vega 8",
    "Puertos (AIO)": "1x RJ-45, 2x USB 2.0, 3x USB 5Gbps",
    "Peso (AIO)": "6720 g",
    "SO (AIO)": "Windows 11 Home",
    "Periféricos inalámbricos": "Sí",
    "Part number": "MUWD3LL/A",
    "Memoria interna": "128 GB",
    "Conectividad celular": "No",
    "Sistema operativo": "iPadOS 17.4",
    "Color": "Starlight",
    "Peso": "462 g",
    "Dimensiones": "248 x 179 x 6 mm",
    "Almacenamiento externo": "No posee",
    "Batería": "28.6 Wh",
    "Cámara principal": "12.0 MP",
    "Cámara frontal": "12.0 MP",
    "GPS": "No",
    "Bluetooth": "Sí",
    "Salida de audífonos": "No",
    "CPU": "Apple P Cluster (Quad core / 3500 MHz) + Apple E Cluster (Quad core / 2400 MHz)",
    "GPU": "NVIDIA GeForce RTX 5060",
    "Fabricante": "MSI",
    "Memoria": "8 GB GDDR7 (128 bit)",
    "Bus": "PCI Express 5.0 x8",
    "Frecuencias core (base / boost / OC)": "2280 / 2497 / 2535 MHz",
    "Frecuencia memorias": "875 MHz",
    "Núcleo": "NVIDIA Blackwell 2.0 GB206-250",
    "Perfil": "Normal",
    "Refrigeración": "Ventilador",
    "Slots": "Dual slot",
    "Largo": "197 mm",
    "Iluminación": "No posee",
    "¿Backplate?": "Sí",
    "Conectores de poder": "1x 8 pines",
    "Puertos de video": "3x DisplayPort 2.1, 1x HDMI 2.1b",
}

# ===========================
# Helpers privados
# ===========================

REPORT_STATUS_FLOW = [
    ("abierto", "Nuevo", 1),
    ("pendiente", "En revision", 2),
    ("resuelto", "Resuelto", 3),
]
REPORT_STATUS_LABEL = {code: label for code, label, _ in REPORT_STATUS_FLOW}
REPORT_STATUS_ORDER = {code: order for code, _, order in REPORT_STATUS_FLOW}


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


def _set_report_state(reporte, estado, user, note=None):
    reporte.estado = estado
    reporte.admin_actor = user
    reporte.fecha_accion = timezone.now()
    fields = ["estado", "admin_actor", "fecha_accion"]
    if note is not None:
        reporte.accion_admin = note
        fields.append("accion_admin")
    reporte.save(update_fields=fields)


@staff_member_required
# ===========================
# Dashboard / Analytics
# ===========================
def admin_dashboard(request):
    return redirect(reverse("admin_analytics"))


@staff_member_required
def admin_analytics(request):
    tipos = TipoProducto.objects.order_by("nombre_tipo")
    selected_type_id = request.GET.get("type") or (str(tipos[0].id) if tipos else None)
    selected_type = None
    brand_labels = []
    brand_values = []
    if selected_type_id and tipos:
        try:
            selected_type = tipos.get(id=int(selected_type_id))
        except (TipoProducto.DoesNotExist, ValueError):
            selected_type = tipos.first()
            selected_type_id = str(selected_type.id) if selected_type else None
        if selected_type:
            brand_stats = (
                ProductoVisto.objects.filter(producto__tipo_producto_id=selected_type.id)
                .values("producto__marca_producto__nombre_marca")
                .annotate(total=Count("id"))
                .order_by("-total", "producto__marca_producto__nombre_marca")[:8]
            )
            for entry in brand_stats:
                label = entry["producto__marca_producto__nombre_marca"] or "Sin marca"
                brand_labels.append(label)
                brand_values.append(entry["total"])

    store_stats = (
        ReferenceVisit.objects.values("referencia__nombre_fuente")
        .annotate(total=Count("id"))
        .order_by("-total", "referencia__nombre_fuente")[:8]
    )
    store_labels = [entry["referencia__nombre_fuente"] or "Sin nombre" for entry in store_stats]
    store_values = [entry["total"] for entry in store_stats]

    funnel_views = 0
    funnel_clicks = 0
    if selected_type:
        funnel_views = ProductoVisto.objects.filter(producto__tipo_producto_id=selected_type.id).count()
        funnel_clicks = ReferenceVisit.objects.filter(
            referencia__producto__tipo_producto_id=selected_type.id
        ).count()

    funnel_labels = ["Vistas de producto", "Clicks externos"]
    funnel_values = [funnel_views, funnel_clicks]
    conversion_rate = round((funnel_clicks * 100 / funnel_views), 1) if funnel_views else None

    brand_table = list(zip(brand_labels, brand_values))
    store_table = list(zip(store_labels, store_values))

    context = {
        "type_options": tipos,
        "selected_type_id": selected_type_id,
        "brand_labels": brand_labels,
        "brand_values": brand_values,
        "brand_table": brand_table,
        "store_labels": store_labels,
        "store_values": store_values,
        "store_table": store_table,
        "funnel_labels": funnel_labels,
        "funnel_values": funnel_values,
        "conversion_rate": conversion_rate,
    }
    return render(request, "admin_panel/analytics.html", context)


@staff_member_required
# ===========================
# Gestión de productos
# ===========================
def admin_products(request):
    qs = Producto.objects.select_related("categoria_producto", "tipo_producto", "marca_producto")
    q = (request.GET.get("q") or "").strip()
    categoria_id = request.GET.get("categoria")
    tipo_id = request.GET.get("tipo")
    activo = request.GET.get("activo")

    if q:
        qs = qs.filter(
            models.Q(nombre_producto__icontains=q)
            | models.Q(modelo_producto__icontains=q)
            | models.Q(marca_producto__nombre_marca__icontains=q)
        )
    if categoria_id:
        qs = qs.filter(categoria_producto_id=categoria_id)
    if tipo_id:
        qs = qs.filter(tipo_producto_id=tipo_id)
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
        "tipos": TipoProducto.objects.all(),
        "pagination_html": pagination_html,
    }
    return render(request, "admin_panel/products.html", context)


def _has_valid_reference(ref_formset):
    for form in ref_formset.forms:
        if not hasattr(form, "cleaned_data"):
            continue
        data = form.cleaned_data
        if not data or data.get("DELETE"):
            continue
        if data.get("nombre_fuente") and data.get("precio") is not None:
            return True
    return False


@staff_member_required
def admin_product_create(request):
    producto = Producto()
    if request.method == "POST":
        form = AdminProductForm(request.POST, request.FILES, instance=producto)
        ref_formset = ProductReferenceFormSet(request.POST, prefix="ref", instance=producto)
        spec_formset = ProductSpecFormSet(request.POST, prefix="spec", instance=producto)
        is_valid = form.is_valid() and ref_formset.is_valid() and spec_formset.is_valid()
        if is_valid and not _has_valid_reference(ref_formset):
            ref_formset._non_form_errors = ref_formset.error_class(
                ["Agrega al menos una referencia con nombre y precio."]
            )
            is_valid = False
        if is_valid:
            with transaction.atomic():
                producto = form.save()
                ref_formset.instance = producto
                spec_formset.instance = producto
                ref_formset.save()
                spec_formset.save()
            messages.success(request, "Producto creado correctamente.")
            return redirect(reverse("admin_product_detail", args=[producto.pk]))
    else:
        form = AdminProductForm(instance=producto)
        ref_formset = ProductReferenceFormSet(prefix="ref", instance=producto)
        spec_formset = ProductSpecFormSet(prefix="spec", instance=producto)

    context = {
        "form": form,
        "ref_formset": ref_formset,
        "spec_formset": spec_formset,
        "is_edit": False,
        "spec_templates": SPEC_TEMPLATES,
        "spec_placeholders": SPEC_PLACEHOLDERS,
    }
    return render(request, "admin_panel/product_form.html", context)


@staff_member_required
def admin_product_edit(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        form = AdminProductForm(request.POST, request.FILES, instance=producto)
        ref_formset = ProductReferenceFormSet(request.POST, prefix="ref", instance=producto)
        spec_formset = ProductSpecFormSet(request.POST, prefix="spec", instance=producto)
        is_valid = form.is_valid() and ref_formset.is_valid() and spec_formset.is_valid()
        if is_valid and not _has_valid_reference(ref_formset):
            ref_formset._non_form_errors = ref_formset.error_class(
                ["El producto debe tener al menos una referencia activa."]
            )
            is_valid = False
        if is_valid:
            with transaction.atomic():
                producto = form.save()
                ref_formset.instance = producto
                spec_formset.instance = producto
                ref_formset.save()
                spec_formset.save()
            messages.success(request, "Producto actualizado correctamente.")
            return redirect(reverse("admin_product_detail", args=[producto.pk]))
    else:
        form = AdminProductForm(instance=producto)
        ref_formset = ProductReferenceFormSet(prefix="ref", instance=producto)
        spec_formset = ProductSpecFormSet(prefix="spec", instance=producto)

    context = {
        "form": form,
        "ref_formset": ref_formset,
        "spec_formset": spec_formset,
        "is_edit": True,
        "producto": producto,
        "spec_templates": SPEC_TEMPLATES,
        "spec_placeholders": SPEC_PLACEHOLDERS,
    }
    return render(request, "admin_panel/product_form.html", context)


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
# ===========================
# Gestión de usuarios
# ===========================
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
    favoritos = (
        user.productosfavoritos_set.select_related("producto", "producto__marca_producto", "producto__categoria_producto")
        .order_by("-id")
    )
    context = {
        "usuario": user,
        "preferencias": preferencias,
        "favoritos": favoritos,
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
# ===========================
# Gestión de reportes
# ===========================
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

    status_summary = {code: 0 for code, _, _ in REPORT_STATUS_FLOW}
    for row in Reporte.objects.values("estado").annotate(total=Count("id")):
        status_summary[row["estado"]] = row["total"]

    context = {
        "page_obj": page_obj,
        "pagination_html": pagination_html,
        "estado": estado,
        "status_summary": status_summary,
    }
    return render(request, "admin_panel/reports.html", context)


@staff_member_required
def admin_report_detail(request, pk):
    reporte = get_object_or_404(Reporte.objects.select_related("producto", "reporter"), pk=pk)
    if request.method == "POST":
        desired_state = request.POST.get("action") or reporte.estado
        valid_states = {code for code, _, _ in REPORT_STATUS_FLOW}
        if desired_state not in valid_states:
            messages.error(request, "Selecciona un estado valido.")
            return redirect(request.path)
        note = (request.POST.get("admin_note") or "").strip()
        disable_flag = request.POST.get("disable_product") == "on"

        fields_to_update = []
        if desired_state != reporte.estado:
            reporte.estado = desired_state
            reporte.admin_actor = request.user
            reporte.fecha_accion = timezone.now()
            fields_to_update.extend(["estado", "admin_actor", "fecha_accion"])

        current_note = (reporte.accion_admin or "").strip()
        if note != current_note:
            reporte.accion_admin = note
            fields_to_update.append("accion_admin")

        product = reporte.producto
        if product:
            if disable_flag and not reporte.producto_deshabilitado:
                if product.is_active:
                    product.is_active = False
                    product.save(update_fields=["is_active"])
                reporte.producto_deshabilitado = True
                fields_to_update.append("producto_deshabilitado")
            elif not disable_flag and reporte.producto_deshabilitado:
                if not product.is_active:
                    product.is_active = True
                    product.save(update_fields=["is_active"])
                reporte.producto_deshabilitado = False
                fields_to_update.append("producto_deshabilitado")

        if fields_to_update:
            reporte.save(update_fields=list(set(fields_to_update)))
            label = REPORT_STATUS_LABEL.get(reporte.estado, reporte.estado.title())
            messages.success(request, f"Reporte actualizado. Estado actual: {label}.")
        else:
            messages.info(request, "No se registraron cambios.")
        return redirect(request.path)

    context = {
        "reporte": reporte,
        "status_flow": REPORT_STATUS_FLOW,
        "current_step": REPORT_STATUS_ORDER.get(reporte.estado, 1),
    }
    return render(request, "admin_panel/report_detail.html", context)


@staff_member_required
def admin_report_action(request, pk, action):
    reporte = get_object_or_404(Reporte, pk=pk)
    next_url = request.GET.get("next") or reverse("admin_reports")
    if action == "take":
        _set_report_state(reporte, "pendiente", request.user)
        messages.success(request, "Reporte marcado como En revision.")
    elif action == "resolve":
        _set_report_state(reporte, "resuelto", request.user)
        messages.success(request, "Reporte marcado como resuelto.")
    elif action == "open":
        _set_report_state(reporte, "abierto", request.user)
        messages.success(request, "Reporte reabierto.")
    elif action == "delete":
        reporte.delete()
        messages.success(request, "Reporte eliminado.")
        return redirect(next_url)
    else:
        messages.error(request, "Accion no valida.")
    return redirect(next_url)
