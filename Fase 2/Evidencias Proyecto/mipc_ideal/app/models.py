from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User

# Create your models here.
# En Django, los datos se crean en objetos, llamados Modelos, y en realidad son tablas en una base de datos.
# Para migrar las nuevas tablas a la base de datos, se usa el comando: python manage.py makemigrations 'nombre_app'
# Luego, para aplicar los cambios a la base de datos, se usa el comando: python manage.py migrate

# ==============================
#     PERFIL DE USUARIO
# ==============================
class PreferenciaUsuario(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    categoria = models.ForeignKey('CategoriaProducto', on_delete=models.CASCADE, null=True, blank=True)
    tipo_producto = models.ForeignKey('TipoProducto', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.categoria or self.tipo_producto}"
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_type = models.CharField(
        max_length=50,
        choices=[('usuario', 'Usuario'), ('tienda', 'Tienda')],
        default='usuario'
    )

    def __str__(self):
        return f"{self.user.username} - {self.profile_type}"

# ==============================
#     PREFERENCIAS DE USUARIO
# ==============================
class ProductosFavoritos(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.usuario.username} - {self.producto}"

# ==============================
#     TIENDAS Y SERVICIOS
# ==============================
class Tienda(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nombre_tienda = models.CharField(max_length=100)
    email_tienda = models.EmailField(unique=True)
    descripcion_tienda = models.TextField()
    image_tienda = models.ImageField(upload_to='tiendas/', null=True, blank=True)
    direccion_tienda = models.CharField(max_length=200)

    def __str__(self):
        return self.nombre_tienda

class TipoServicio(models.Model):
    nombre_tipo_servicio = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_tipo_servicio

class TiendaCategoria(models.Model):
    tienda = models.ForeignKey('Tienda', on_delete=models.CASCADE)
    categoria = models.ForeignKey('CategoriaProducto', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.tienda} - {self.categoria}"

class TiendaProducto(models.Model):
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)
    tienda = models.ForeignKey('Tienda', on_delete=models.CASCADE)
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.producto} - {self.tienda}"

# ==============================
#     PRODUCTOS Y CATEGORÍAS
# ==============================
class MarcaProducto(models.Model):
    nombre_marca = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_marca

class CategoriaProducto(models.Model):
    nombre_categoria = models.CharField(max_length=100)
    descripcion_categoria = models.TextField()
    imagen_categoria = models.ImageField(upload_to='categorias/', null=True, blank=True)
    banner_categoria = models.ImageField(upload_to='banners/', null=True, blank=True)

    def __str__(self):
        return self.nombre_categoria

class TipoProducto(models.Model):
    nombre_tipo = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_tipo

class Producto(models.Model):
    nombre_producto = models.CharField(max_length=100)
    descripcion_producto = models.TextField()
    modelo_producto = models.CharField(max_length=100)
    imagen_producto = models.ImageField(upload_to='productos/')
    fecha_creacion = models.DateTimeField(default=timezone.now)
    marca_producto = models.ForeignKey('MarcaProducto', on_delete=models.PROTECT)
    categoria_producto = models.ForeignKey('CategoriaProducto', on_delete=models.PROTECT)
    tipo_producto = models.ForeignKey('TipoProducto', on_delete=models.PROTECT)
    vistas = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.nombre_producto

class EspecificacionProducto(models.Model):
    nombre_especificacion = models.CharField(max_length=100)
    valor_especificacion = models.CharField(max_length=200)
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)

    def __str__(self):
        return self.nombre_especificacion

class ProductoVisto(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)
    fecha_visto = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario} vio {self.producto}"