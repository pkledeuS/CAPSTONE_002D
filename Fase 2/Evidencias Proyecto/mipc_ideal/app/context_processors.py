from django.shortcuts import render, get_object_or_404
from django.db.models import Count
from .models import (
    CategoriaProducto,
    Producto,
    TipoProducto,
    ProductoVisto,
    Profile,
)

# Context Processors Globales
def categorias_context(request):
    """
    Provee acceso global a categorías y tipos de productos.
    Usado en la navegación principal y filtros.
    """
    return {
        'categorias': CategoriaProducto.objects.all(),
        'tiposproductos': TipoProducto.objects.all()
    }

def perfil_context(request):
    """
    Provee acceso global al perfil del usuario actual.
    Útil para mostrar información personalizada en el layout.
    """
    perfil = None
    if request.user.is_authenticated:
        try:
            perfil = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            pass
    return {'perfil': perfil}

def user_profile_type(request):
    """
    Provee acceso global al tipo de perfil del usuario.
    Usado para control de acceso y personalización de UI.
    """
    if request.user.is_authenticated:
        profile = Profile.objects.filter(user=request.user).first()
        if profile:
            return {'profile_type': profile.profile_type}
    return {}

# Vistas Normales (Deberían moverse a views.py)
def home(request):
    """
    Vista de la página principal.
    Muestra categorías, tiendas y productos más vistos.
    NOTA: Debería moverse a views.py
    """
    return render(request, 'home.html', {
        'categorias': CategoriaProducto.objects.all(),
        'productos_vistos': (Producto.objects
            .annotate(total_visitas=Count('productovisto'))
            .order_by('-total_visitas')[:6])
    })

def products_view(request):
    """
    Vista del catálogo de productos.
    Muestra los productos más recientes.
    NOTA: Debería moverse a views.py
    """
    productos_recientes = Producto.objects.all().order_by('-fecha_creacion')[:6]
    return render(request, 'products-view.html', {
        'productos_recientes': productos_recientes
    })

def detalle_producto(request, producto_id):
    """
    Vista detallada de un producto.
    Registra la vista del producto si el usuario está autenticado.
    NOTA: Debería moverse a views.py
    """
    producto = get_object_or_404(Producto, id=producto_id)

    if request.user.is_authenticated:
        ProductoVisto.objects.create(
            usuario=request.user,
            producto=producto
        )

    return render(request, 'product-detail.html', {
        'producto': producto
    })
