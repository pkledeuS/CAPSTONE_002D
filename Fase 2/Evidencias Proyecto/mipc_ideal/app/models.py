from django.db import models

# Create your models here.
# En Django, los datos se crean en objetos, llamados Modelos, y en realidad son tablas en una base de datos.
# Para migrar las nuevas tablas a la base de datos, se usa el comando: python manage.py makemigrations 'nombre_app'
# Luego, para aplicar los cambios a la base de datos, se usa el comando: python manage.py migrate

#USUARIO Y PREFERENCIAS
class usuario(models.Model):
    #id_usuario = models.AutoField(primary_key=True)
    nombre_usuario = models.CharField(max_length=50, unique=True)
    email_usuario = models.EmailField(unique=True)

    def __str__(self):
        return self.nombre_usuario

class preferencias(models.Model):
    nombre_preferencia = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_preferencia

class preferencias_usuario(models.Model):
    usuario = models.ForeignKey('usuario', on_delete=models.CASCADE)
    preferencia = models.ForeignKey('preferencias', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.usuario} - {self.preferencia}"

class productos_favoritos(models.Model):
    usuario = models.ForeignKey('usuario', on_delete=models.CASCADE)
    producto = models.ForeignKey('producto', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.usuario} - {self.producto}"
#--------------------------------

#TIENDA Y TIPO DE SERVICIO
class tienda(models.Model):
    nombre_tienda = models.CharField(max_length=100)
    email_tienda = models.EmailField(unique=True)
    direccion_tienda = models.CharField(max_length=200)

    def __str__(self):
        return self.nombre_tienda

class tipo_servicio(models.Model):
    nombre_tipo_servicio = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_tipo_servicio

class tienda_tipo_servicio(models.Model):
    tienda = models.ForeignKey('tienda', on_delete=models.CASCADE)
    tipo_servicio = models.ForeignKey('tipo_servicio', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.tienda} - {self.tipo_servicio}"

class tienda_producto(models.Model):
    producto = models.ForeignKey('producto', on_delete=models.CASCADE)
    tienda = models.ForeignKey('tienda', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.producto} - {self.tienda}"
#--------------------------------

#PRODUCTO
class producto(models.Model):
    nombre_producto = models.CharField(max_length=100)
    descripcion_producto = models.TextField()
    modelo_producto = models.CharField(max_length=100)
    imagen_producto = models.ImageField(upload_to='productos/')
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    marca_producto = models.ForeignKey('marca_producto', on_delete=models.PROTECT)
    categoria_producto = models.ForeignKey('categoria_producto', on_delete=models.PROTECT)

    def __str__(self):
        return self.nombre_producto

class marca_producto(models.Model):
    nombre_marca = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_marca

class especificacion_producto(models.Model):
    nombre_especificacion = models.CharField(max_length=100)
    valor_especificacion = models.CharField(max_length=200)
    producto = models.ForeignKey('producto', on_delete=models.CASCADE)

    def __str__(self):
        return self.nombre_especificacion

class categoria_producto(models.Model):
    nombre_categoria = models.CharField(max_length=100)
    descripcion_categoria = models.TextField()

    def __str__(self):
        return self.nombre_categoria