from django.urls import path
from .views import (
    home, products, info,
    product_detail, products_by_category,
    products_by_type, edit_profile
)
from . import views

urlpatterns = [
    path('', home, name='home'),
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout, name='logout'),

    path('edit_profile/', edit_profile, name='edit_profile'),

    path('products/', products, name='products'),
    path('info/', info, name='info'),

    path('producto/<int:producto_id>/', product_detail, name='product_detail'),
    path('products/categoria/<int:categoria_id>/', products_by_category, name='products_by_category'),
    path('products/tipo/<int:tipo_id>/', products_by_type, name='products_by_type'),

    path('check_username/', views.check_username, name='check_username'),
    path('check_email/', views.check_email, name='check_email'),
    path('preferencias/', views.preferences_products_view, name='preferences_products_view'),
]