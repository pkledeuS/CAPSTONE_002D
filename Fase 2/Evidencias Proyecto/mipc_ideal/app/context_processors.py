from django.shortcuts import render, get_object_or_404
from django.db.models import Count
from .models import CategoriaProducto, Tienda, Producto, TipoProducto, ProductoVisto

def categorias_context(request):
    return {
        'categorias': CategoriaProducto.objects.all(),
        'tiposproductos': TipoProducto.objects.all()
    }

def home(request):
    categorias = CategoriaProducto.objects.all()
    tiendas = Tienda.objects.all()
    productos_vistos = Producto.objects.annotate(total_visitas=Count('productovisto')).order_by('-total_visitas')[:10]

    return render(request, 'home.html', {
        'categorias': categorias, 
        'tiendas': tiendas,
        'productos_vistos': productos_vistos
        })

def products_view(request):
    productos_recientes = Producto.objects.all().order_by('-fecha_creacion')[:10]

    return render(request, 'products-view.html', {
        'productos_recientes': productos_recientes
    })

def detalle_producto(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)

    # Si el usuario está autenticado, registrar la vista del producto
    ProductoVisto.objects.create(
        usuario=request.user if request.user.is_authenticated else None,
        producto=producto
    )

    return render(request, 'product-detail.html', {'producto': producto})



