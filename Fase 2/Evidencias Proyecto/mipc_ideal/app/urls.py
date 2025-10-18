from django.urls import path
from .views import home, login, register, edit_user, edit_store, products, info, product_detail, products_by_category, products_by_type

urlpatterns = [
    path('', home, name='home'),
    path('login/', login, name='login'),
    path('register/', register, name='register'),
    path('edit_user/', edit_user, name='edit_user'),
    path('edit_store/', edit_store, name='edit_store'),
    path('products/', products, name='products'),
    path('info/', info, name='info'),
    path('producto/<int:producto_id>/', product_detail, name='product_detail'),
    path('products/categoria/<int:categoria_id>/', products_by_category, name='products_by_category'),
    path('products/tipo/<int:tipo_id>/', products_by_type, name='products_by_type'),
]