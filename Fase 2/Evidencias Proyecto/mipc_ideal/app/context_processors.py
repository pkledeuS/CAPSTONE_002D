from .models import CategoriaProducto

def categorias_context(request):
    return {
        'categorias': CategoriaProducto.objects.all()
    }