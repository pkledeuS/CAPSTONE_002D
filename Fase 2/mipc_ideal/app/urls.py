from django.urls import path
from . import views

urlpatterns = [
    path('home/', views.app_view, name='vista_principal(home)'),
]