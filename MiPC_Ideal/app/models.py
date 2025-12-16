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
    ROLE_CHOICES = [
        ('usuario', 'Usuario'),
        ('admin', 'Admin'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_type = models.CharField(max_length=50, choices=ROLE_CHOICES, default='usuario')
    is_active = models.BooleanField(default=True)
    preferred_budget_min = models.PositiveIntegerField(null=True, blank=True)
    preferred_budget_max = models.PositiveIntegerField(null=True, blank=True)
    preference_notes = models.TextField(blank=True)
    preferred_budget_manual = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.profile_type}"

# ==============================
#     FAVORITOS
# ==============================
class ProductosFavoritos(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.usuario.username} - {self.producto}"

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
    categorias_extra = models.ManyToManyField(
        'CategoriaProducto',
        blank=True,
        related_name='productos_extra',
        verbose_name='Categorias adicionales',
        help_text='Categorias secundarias para este producto sin duplicarlo.',
    )
    vistas = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre_producto


class ProductReference(models.Model):
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE, related_name='referencias')
    nombre_fuente = models.CharField(max_length=120)
    url_fuente = models.URLField(max_length=300, blank=True)
    precio = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    nota = models.CharField(max_length=200, blank=True)
    actualizado = models.DateTimeField(auto_now=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre_fuente', 'precio']
        verbose_name = "Referencia de producto"
        verbose_name_plural = "Referencias de producto"

    def __str__(self):
        return f"{self.nombre_fuente} - {self.producto} (${self.precio})"


class ReferenceVisit(models.Model):
    referencia = models.ForeignKey(ProductReference, on_delete=models.CASCADE, related_name="visitas")
    usuario = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    clicked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-clicked_at"]

    def __str__(self):
        usuario = self.usuario.username if self.usuario else "Anon"
        return f"{usuario} -> {self.referencia.nombre_fuente} ({self.clicked_at:%Y-%m-%d %H:%M})"

class EspecificacionProducto(models.Model):
    nombre_especificacion = models.CharField(max_length=100)
    valor_especificacion = models.CharField(max_length=200)
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)

    def __str__(self):
        return self.nombre_especificacion

# ==============================
#     SEGUIMIENTO / STATS
# ==============================
class ProductoVisto(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    producto = models.ForeignKey('Producto', on_delete=models.CASCADE)
    fecha_visto = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario} vio {self.producto}"


class UserViewStat(models.Model):
    METRIC_BRAND = "brand"
    METRIC_CATEGORY = "category"
    METRIC_TYPE = "type"
    METRIC_PRICE = "price_band"
    METRIC_CHOICES = [
        (METRIC_BRAND, "Marca"),
        (METRIC_CATEGORY, "Categoria"),
        (METRIC_TYPE, "Tipo de producto"),
        (METRIC_PRICE, "Rango de precio"),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="view_stats")
    metric = models.CharField(max_length=20, choices=METRIC_CHOICES)
    key = models.CharField(max_length=120)
    count = models.PositiveIntegerField(default=0)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("usuario", "metric", "key")
        verbose_name = "Estadistica de vista"
        verbose_name_plural = "Estadisticas de vistas"

    def __str__(self):
        return f"{self.usuario} - {self.metric}:{self.key} ({self.count})"
    
# ==============================
#     RESEÑAS Y REPORTES
# ==============================
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
        ('abierto', 'Nuevo'),
        ('pendiente', 'En revision'),
        ('resuelto', 'Resuelto'),
    ]

    ACCIONES = [
        ('info_incorrecta', 'Informacion incorrecta'),
        ('spam', 'Spam o contenido enganoso'),
        ('duplicado', 'Producto duplicado'),
        ('otro', 'Otro motivo'),
    ]

    target_type = models.CharField(max_length=20, choices=[('producto', 'Producto')], default='producto')
    producto = models.ForeignKey('Producto', null=True, blank=True, on_delete=models.CASCADE)
    reporter = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reportes_creados')
    motivo = models.CharField(max_length=50, choices=ACCIONES)
    detalle = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='abierto')

    accion_admin = models.TextField(blank=True, help_text="Notas/instrucciones del administrador")
    fecha_accion = models.DateTimeField(null=True, blank=True)
    admin_actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reportes_moderados')
    producto_deshabilitado = models.BooleanField(default=False)
    notificacion_leida = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Reporte'
        verbose_name_plural = 'Reportes'

# MODELO PARA RESEÑAS DE TIENDAS
