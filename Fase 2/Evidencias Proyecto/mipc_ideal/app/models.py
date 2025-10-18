from django.utils import timezone
from django.db import models

# Create your models here.
# En Django, los datos se crean en objetos, llamados Modelos, y en realidad son tablas en una base de datos.
# Para migrar las nuevas tablas a la base de datos, se usa el comando: python manage.py makemigrations 'nombre_app'
# Luego, para aplicar los cambios a la base de datos, se usa el comando: python manage.py migrate

# ==============================
#     USUARIO Y PREFERENCIAS
# ==============================
class Usuario(models.Model):
    """
    Representa a un usuario del sistema.
    Este puede tener preferencias y agregar productos favoritos.
    """
    nombre_usuario = models.CharField(max_length=50, unique=True)
    email_usuario = models.EmailField(unique=True)

    def __str__(self):
        return f"{self.nombre_usuario} ({self.email_usuario})"

class Preferencias(models.Model):
    """
    Define las preferencias que un usuario puede tener(ej. Gamer, Trabajo, Estudio, Hogar).
    """
    nombre_preferencia = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_preferencia

class PreferenciasUsuario(models.Model):
    """
    Relacion muchos a muchos entre Usuario y Preferencias.
    Un usuario puede tener varias preferencias y una preferencia puede pertenecer a varios usuarios.
    """
    usuario = models.ForeignKey('Usuario', on_delete=models.CASCADE)
    preferencia = models.ForeignKey('Preferencias', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.usuario} - {self.preferencia}"

class ProductosFavoritos(models.Model):
    """
    Lista de productos favoritos de un usuario.
    Un usuario puede tener varios productos favoritos y un producto puede ser favorito de varios usuarios.
    """
    usuario = models.ForeignKey('Usuario', on_delete=models.CASCADE)
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.usuario} - {self.producto}"
#--------------------------------

# ==============================
#    TIENDA Y TIPO DE SERVICIO
# ==============================
class Tienda(models.Model):
    """
    Representa una tienda del sistema.
    Esta puede ofrecer varios tipos de servicios.
    """
    nombre_tienda = models.CharField(max_length=100)
    email_tienda = models.EmailField(unique=True)
    descripcion_tienda = models.TextField()
    image_tienda = models.ImageField(upload_to='tiendas/', null=True, blank=True)
    direccion_tienda = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.nombre_tienda} ({self.email_tienda})"

class TipoServicio(models.Model):
    """
    Define los tipos de servicios que una tienda puede ofrecer (ej. Mantención, Reparación, Instalación, Limpieza).
    """
    nombre_tipo_servicio = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_tipo_servicio

class TiendaTipoServicio(models.Model):
    """
    Relacion muchos a muchos entre Tienda y TipoServicio.
    Una tienda puede ofrecer varios tipos de servicios y un tipo de servicio puede ser ofrecido por varias tiendas.
    """
    tienda = models.ForeignKey('Tienda', on_delete=models.CASCADE)
    tipo_servicio = models.ForeignKey('TipoServicio', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.tienda} - {self.tipo_servicio}"

class TiendaProducto(models.Model):
    """
    Relacion muchos a muchos entre Tienda y Producto.
    Una tienda puede vender varios productos y un producto puede ser vendido en varias tiendas.
    """
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)
    tienda = models.ForeignKey('Tienda', on_delete=models.CASCADE)
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.producto} - {self.tienda}"
#--------------------------------

# ==============================
#     PRODUCTOS Y CATEGORÍAS
# ==============================
class MarcaProducto(models.Model):
    """
    Define las marcas de los productos (ej. HP, ASUS, AMD).
    """
    nombre_marca = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_marca

class CategoriaProducto(models.Model):
    """
    Define las categorías de los productos (ej. Gamer, Oficina, Hogar).
    """
    nombre_categoria = models.CharField(max_length=100)
    descripcion_categoria = models.TextField()
    imagen_categoria = models.ImageField(upload_to='categorias/', null=True, blank=True)
    banner_categoria = models.ImageField(upload_to='banners/', null=True, blank=True)

    def __str__(self):
        return self.nombre_categoria

class Producto(models.Model):
    """
    Representa un producto en el sistema.
    Se asocia una marca y una categoría.
    """
    nombre_producto = models.CharField(max_length=100)
    descripcion_producto = models.TextField()
    modelo_producto = models.CharField(max_length=100)
    imagen_producto = models.ImageField(upload_to='productos/')
    fecha_creacion = models.DateTimeField(default=timezone.now)
    marca_producto = models.ForeignKey('MarcaProducto', on_delete=models.PROTECT)
    categoria_producto = models.ForeignKey('CategoriaProducto', on_delete=models.PROTECT)
    tipo_producto = models.ForeignKey('TipoProducto', on_delete=models.PROTECT)

    def __str__(self):
        return self.nombre_producto

class EspecificacionProducto(models.Model):
    """
    Define las especificaciones técnicas de un producto (ej. RAM, Procesador, Almacenamiento).
    """
    nombre_especificacion = models.CharField(max_length=100)
    valor_especificacion = models.CharField(max_length=200)
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)

    def __str__(self):
        return self.nombre_especificacion

class ProductoVisto(models.Model):
    usuario = models.ForeignKey('Usuario', on_delete=models.SET_NULL, null=True, blank=True)
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)
    fecha_visto = models.DateTimeField(auto_now_add=True)

class TipoProducto(models.Model):
    """
    Define los tipos de productos (ej. Laptop, Desktop, Monitor).
    """
    nombre_tipo = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_tipo