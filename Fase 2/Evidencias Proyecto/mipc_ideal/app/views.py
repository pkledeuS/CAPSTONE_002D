from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader
from .models import Producto, CategoriaProducto, TipoProducto

# Create your views here.
def home(request):
    return render(request, 'home.html')

def login(request):
    return render(request, 'login.html')

def register(request):
    return render(request, 'register.html')

def edit_user(request):
    return render(request, 'edit-profile-user.html')

def edit_store(request):
    return render(request, 'edit-profile-store.html')

def info(request):
    return render(request, 'info.html')

def products(request):
    productos = Producto.objects.all()
    productos_recientes = Producto.objects.order_by('-fecha_creacion')[:6]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes
    })

def product_detail(request, producto_id):
    producto = Producto.objects.get(id=producto_id)
    return render(request, 'product-detail.html', {'producto': producto})

def products_by_category(request, categoria_id):
    categoria = CategoriaProducto.objects.get(id=categoria_id)
    productos = Producto.objects.filter(categoria_producto=categoria)
    productos_recientes = productos.order_by('-fecha_creacion')[:10]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes,
        'categoria': categoria
    })

def products_by_type(request, tipo_id):
    tipo = TipoProducto.objects.get(id=tipo_id)
    productos = Producto.objects.filter(tipo_producto=tipo)
    productos_recientes = productos.order_by('-fecha_creacion')[:10]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes,
        'tipo': tipo
    })