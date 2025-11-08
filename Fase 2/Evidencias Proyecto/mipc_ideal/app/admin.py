from django.contrib import admin
from django.db.models import Count
from .models import (
    Profile, PreferenciaUsuario, ProductosFavoritos,
    Tienda, TipoServicio, TiendaCategoria, TiendaProducto,
    Producto, CategoriaProducto, MarcaProducto, TipoProducto,
    EspecificacionProducto, ProductoVisto,
    # Si quieres administrar el chat también:
    # ChatSession, ChatTurn,
)

class EspecificacionProductoInline(admin.TabularInline):
    model = EspecificacionProducto
    extra = 20  # muestra 3 filas vacías por defecto
    fields = ("nombre_especificacion", "valor_especificacion")

class TiendaProductoInline(admin.TabularInline):
    model = TiendaProducto
    extra = 1
    fields = ("tienda", "precio")
    autocomplete_fields = ("tienda",)

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre_producto", "categoria_producto", "tipo_producto", "marca_producto")
    list_select_related = ("categoria_producto", "tipo_producto", "marca_producto")
    search_fields = ("nombre_producto", "modelo_producto")
    list_filter = ("categoria_producto", "tipo_producto", "marca_producto")
    list_per_page = 20
    inlines = [EspecificacionProductoInline, TiendaProductoInline]
    autocomplete_fields = ("marca_producto", "categoria_producto", "tipo_producto")

@admin.register(MarcaProducto)
class MarcaProductoAdmin(admin.ModelAdmin):
    search_fields = ("nombre_marca",)

@admin.register(CategoriaProducto)
class CategoriaProductoAdmin(admin.ModelAdmin):
    search_fields = ("nombre_categoria",)

@admin.register(TipoProducto)
class TipoProductoAdmin(admin.ModelAdmin):
    search_fields = ("nombre_tipo",)

@admin.register(ProductoVisto)
class ProductoVistoAdmin(admin.ModelAdmin):
    list_display = ("producto", "usuario", "fecha_visto")
    list_filter = ("fecha_visto", "producto__categoria_producto", "producto__tipo_producto")
    date_hierarchy = "fecha_visto"
    search_fields = ("producto__nombre_producto", "usuario__username")

@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    search_fields = ("nombre_tienda",)  # ajusta según el nombre del campo en tu modelo
    list_display = ("nombre_tienda",)

# OJO: evita registrar dos veces el mismo modelo
admin.site.register(Profile)
admin.site.register(PreferenciaUsuario)
admin.site.register(ProductosFavoritos)
admin.site.register(TipoServicio)
admin.site.register(TiendaCategoria)