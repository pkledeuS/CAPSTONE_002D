from django.urls import path
from . import views
from .views import (
    home, products, info,
    product_detail, products_by_category,
    products_by_type, edit_profile,
)

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

    path('tienda/ofertas/', views.store_offers_list, name='store_offers_list'),
    path('tienda/ofertas/nueva/', views.store_offer_new, name='store_offer_new'),
    path('tienda/ofertas/<int:oferta_id>/editar/', views.store_offer_edit, name='store_offer_edit'),
    path('tienda/ofertas/<int:oferta_id>/eliminar/', views.store_offer_delete, name='store_offer_delete'),


    path('check_username/', views.check_username, name='check_username'),
    path('check_email/', views.check_email, name='check_email'),
    path('preferencias/', views.preferences_products_view, name='preferences_products_view'),

    path('chat/', views.chat_page, name='chat_page'),
    path('chat/api/', views.chat_api, name='chat_api'),
    path('chat/reset/', views.chat_reset, name='chat_reset'),
]