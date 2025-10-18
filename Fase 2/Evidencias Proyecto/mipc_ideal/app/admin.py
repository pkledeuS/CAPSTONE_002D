from django.contrib import admin
from .models import Usuario, Preferencias, PreferenciasUsuario, ProductosFavoritos
from .models import Tienda, TipoServicio, TiendaTipoServicio, TiendaProducto
from .models import Producto, MarcaProducto, EspecificacionProducto, CategoriaProducto

# Register your models here.
admin.site.register(Usuario)
admin.site.register(Preferencias)
admin.site.register(PreferenciasUsuario)
admin.site.register(ProductosFavoritos)
admin.site.register(Tienda)
admin.site.register(TipoServicio)
admin.site.register(TiendaTipoServicio)
admin.site.register(TiendaProducto)
admin.site.register(Producto)
admin.site.register(MarcaProducto)
admin.site.register(EspecificacionProducto)
admin.site.register(CategoriaProducto)