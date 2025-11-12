from django.contrib import admin
from .models import (
    Profile,
    PreferenciaUsuario,
    ProductosFavoritos,
    Producto,
    CategoriaProducto,
    MarcaProducto,
    TipoProducto,
    EspecificacionProducto,
    ProductoVisto,
    ProductReference,
)


class EspecificacionProductoInline(admin.TabularInline):
    model = EspecificacionProducto
    extra = 20
    fields = ("nombre_especificacion", "valor_especificacion")


class ProductReferenceInline(admin.TabularInline):
    model = ProductReference
    extra = 1
    fields = ("nombre_fuente", "precio", "stock", "url_fuente", "nota")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre_producto", "categoria_producto", "tipo_producto", "marca_producto")
    list_select_related = ("categoria_producto", "tipo_producto", "marca_producto")
    search_fields = ("nombre_producto", "modelo_producto")
    list_filter = ("categoria_producto", "tipo_producto", "marca_producto")
    list_per_page = 20
    inlines = [EspecificacionProductoInline, ProductReferenceInline]
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


admin.site.register(Profile)
admin.site.register(PreferenciaUsuario)
admin.site.register(ProductosFavoritos)
