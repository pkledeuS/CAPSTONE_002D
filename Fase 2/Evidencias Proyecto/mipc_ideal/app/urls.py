# app/urls.py
from django.urls import path
from . import views
from . import views_admin as av

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout, name='logout'),

    path('edit_profile/', views.edit_profile, name='edit_profile'),

    path('products/', views.products, name='products'),
    path('info/', views.info, name='info'),

    path('producto/<int:producto_id>/', views.product_detail, name='product_detail'),
    path('products/categoria/<int:categoria_id>/', views.products_by_category, name='products_by_category'),
    path('products/tipo/<int:tipo_id>/', views.products_by_type, name='products_by_type'),

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

    # ----- Admin panel -----
    path('admin-panel/', av.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/analytics/', av.admin_analytics, name='admin_analytics'),

    path('admin-panel/tiendas/', av.admin_stores, name='admin_stores'),
    path('admin-panel/usuarios/', av.admin_users, name='admin_users'),
    path('admin-panel/productos/', av.admin_products, name='admin_products'),
    path('admin-panel/reportes/', av.admin_reports, name='admin_reports'),

    # acciones de producto:
    path('admin-panel/reportes/mark/<int:pk>/<str:action>/', av.admin_reports_mark, name='admin_reports_mark'),
    path('admin-panel/productos/<int:pk>/toggle/', av.admin_products_toggle, name='admin_products_toggle'),
    path('admin-panel/productos/<int:pk>/delete/', av.admin_products_delete, name='admin_products_delete'),
]