from django.urls import path
from .views import home, login, register, edit_user, edit_store, products, info

urlpatterns = [
    path('', home, name='home'),
    path('login/', login, name='login'),
    path('register/', register, name='register'),
    path('edit_user/', edit_user, name='edit_user'),
    path('edit_store/', edit_store, name='edit_store'),
    path('products/', products, name='products'),
    path('info/', info, name='info'),
]