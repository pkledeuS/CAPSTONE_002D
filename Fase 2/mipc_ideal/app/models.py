from django.db import models

# Create your models here.
# En Django, los datos se crean en objetos, llamados Modelos, y en realidad son tablas en una base de datos.
# Para migrar las nuevas tablas a la base de datos, se usa el comando: python manage.py makemigrations 'nombre_app'
# Luego, para aplicar los cambios a la base de datos, se usa el comando: python manage.py migrate
class Persona(models.Model):
    nombre = models.CharField(max_length=255)
    apellido = models.CharField(max_length=255)