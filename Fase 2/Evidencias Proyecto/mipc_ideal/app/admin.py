from django.contrib import admin
from .models import usuario, preferencias, preferencias_usuario, productos_favoritos
from .models import tienda, tipo_servicio, tienda_tipo_servicio, tienda_producto
from .models import producto, marca_producto, especificacion_producto, categoria_producto

# Register your models here.
admin.site.register(usuario)
admin.site.register(preferencias)
admin.site.register(preferencias_usuario)
admin.site.register(productos_favoritos)
admin.site.register(tienda)
admin.site.register(tipo_servicio)
admin.site.register(tienda_tipo_servicio)
admin.site.register(tienda_producto)
admin.site.register(producto)
admin.site.register(marca_producto)
admin.site.register(especificacion_producto)
admin.site.register(categoria_producto)