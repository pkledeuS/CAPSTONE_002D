from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

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
    profile_type = models.CharField(max_length=50,choices=[('usuario', 'Usuario'), ('tienda', 'Tienda')],default='usuario')
    is_active = models.BooleanField(default=True)

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
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre_tienda

class TipoServicio(models.Model):
    nombre_tipo_servicio = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_tipo_servicio
    
class TiendaServicio(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE)
    tipo_servicio = models.ForeignKey(TipoServicio, on_delete=models.CASCADE)

    class Meta:
        unique_together = ['tienda', 'tipo_servicio']

    def __str__(self):
        return f"{self.tienda.nombre_tienda} - {self.tipo_servicio.nombre_tipo_servicio}"

class TiendaCategoria(models.Model):
    tienda = models.ForeignKey('Tienda', on_delete=models.CASCADE)
    categoria = models.ForeignKey('CategoriaProducto', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.tienda} - {self.categoria}"

class TiendaProducto(models.Model):
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)
    tienda = models.ForeignKey('Tienda', on_delete=models.CASCADE)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    url_externa = models.URLField(blank=True, null=True)
    stock = models.PositiveIntegerField(default=0)
    nota_tienda = models.CharField(max_length=200, blank=True)
    class Meta: unique_together = ('tienda','producto')

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
    is_active = models.BooleanField(default=True)

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
    
# MODELO PARA EL CHATBOT
class ChatSession(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"ChatSession #{self.id} ({self.user or 'anon'})"
    
class ChatTurn(models.Model):
    ROLE_CHOICES = (('user', 'User'), ('assistant', 'Assistant'), ('system', 'System'))
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='turns')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    text = models.TextField()
    filtros_aplicados = models.JSONField(default=dict, blank=True)
    productos_sugeridos = models.ManyToManyField(Producto, blank=True)
    tokens_in = models.IntegerField(default=0)
    tokens_out = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.role}] {self.created_at:%Y-%m-%d %H:%M:%S}"
    
# MODELO PARA RESEÑAS DE PRODUCTOS
class ProductReview(models.Model):
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_reviews')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('user', 'producto'),)
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.producto} - {self.user} ({self.rating}★)'
    
class Reporte(models.Model):
    ESTADOS = [
        ('pendiente', 'Pendiente de revisión'),
        ('revision', 'En revisión'),
        ('resuelto', 'Resuelto'),
        ('rechazado', 'Rechazado'),
    ]
    
    ACCIONES = [
        ('info_incorrecta', 'Información incorrecta'),
        ('spam', 'Spam o contenido engañoso'),
        ('duplicado', 'Producto duplicado'),
        ('otro', 'Otro motivo'),
    ]

    target_type = models.CharField(max_length=20, choices=[('producto', 'Producto'), ('tienda', 'Tienda')])
    producto = models.ForeignKey('Producto', null=True, blank=True, on_delete=models.CASCADE)
    tienda = models.ForeignKey('Tienda', null=True, blank=True, on_delete=models.CASCADE)
    reporter = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reportes_creados')
    motivo = models.CharField(max_length=50, choices=ACCIONES)
    detalle = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    
    # Nuevos campos
    accion_admin = models.TextField(blank=True, help_text="Notas/instrucciones del administrador")
    fecha_accion = models.DateTimeField(null=True, blank=True)
    admin_actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reportes_moderados')
    producto_deshabilitado = models.BooleanField(default=False)
    notificacion_leida = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Reporte'
        verbose_name_plural = 'Reportes'

class Notificacion(models.Model):
    TIPOS_NOTIFICACION = [
        ('reporte_producto', 'Reporte de Producto'),
        ('producto_eliminado', 'Producto Eliminado'),
        ('info_incorrecta', 'Información Incorrecta'),
        ('otro', 'Otro'),
    ]
    
    tienda = models.ForeignKey('Tienda', on_delete=models.CASCADE)
    tipo = models.CharField(max_length=50, choices=TIPOS_NOTIFICACION, help_text="Tipo de notificación")
    mensaje = models.TextField()
    producto = models.ForeignKey('Producto', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    leida = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'

# MODELO PARA RESEÑAS DE TIENDAS
class StoreReview(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['tienda', 'user']

    def __str__(self):
        return f"Review de {self.user.username} para {self.tienda.nombre_tienda}"