from django.contrib import admin
from .models import (
    Profile,
    PreferenciaUsuario,
    ProductosFavoritos,
    Tienda,
    TipoServicio,
    TiendaCategoria,
    TiendaProducto,
    Producto,
    CategoriaProducto,
    MarcaProducto,
    TipoProducto,
    EspecificacionProducto,
    ProductoVisto,
)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('nombre_producto', 'descripcion_producto', 'modelo_producto', 'imagen_producto', 'fecha_creacion', 'marca_producto', 'categoria_producto', 'tipo_producto')
    search_fields = ('nombre_producto', 'modelo_producto')
    list_filter = ('marca_producto', 'categoria_producto', 'tipo_producto')
    list_per_page = 10

# Register your models here.
admin.site.register(Profile)
admin.site.register(PreferenciaUsuario)
admin.site.register(ProductosFavoritos)
admin.site.register(Tienda)
admin.site.register(TipoServicio)
admin.site.register(TiendaCategoria)
admin.site.register(TiendaProducto)
admin.site.register(Producto)
admin.site.register(CategoriaProducto)
admin.site.register(MarcaProducto)
admin.site.register(TipoProducto)
admin.site.register(EspecificacionProducto)
admin.site.register(ProductoVisto)