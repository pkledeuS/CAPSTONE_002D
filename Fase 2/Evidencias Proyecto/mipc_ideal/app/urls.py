# app/urls.py
from django.urls import path
from . import views
from . import views_admin
from . import views_reco

urlpatterns = [
    path('', views_reco.reco_home, name='reco_home'),
    path('lab/reco-explore/', views_reco.reco_explore, name='reco_explore'),
    path('lab/reco-detail/', views_reco.reco_detail, name='reco_detail'),
    path('lab/reco-guides/', views_reco.reco_guides, name='reco_guides'),
    path('lab/reco-preferences/', views_reco.reco_preferences, name='reco_preferences'),
    path('lab/reco-saved/', views_reco.reco_saved, name='reco_saved'),
    path('lab/reco-favorite/', views_reco.reco_toggle_favorite, name='reco_toggle_favorite'),

    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout, name='logout'),

    path('edit_profile/', views.edit_profile, name='edit_profile'),

    path('products/', views.products, name='products'),
    path('info/', views.info, name='info'),

    path('producto/<int:producto_id>/', views.product_detail, name='product_detail'),
    path('products/categoria/<int:categoria_id>/', views.products_by_category, name='products_by_category'),
    path('products/tipo/<int:tipo_id>/', views.products_by_type, name='products_by_type'),


    path('check_username/', views.check_username, name='check_username'),
    path('check_email/', views.check_email, name='check_email'),
    path('preferencias/', views.preferences_products_view, name='preferences_products_view'),

    # APIs auxiliares para el formulario de productos
    path('api/brands-by-type/', views.api_brands_by_type, name='api_brands_by_type'),
    path('api/products-by-type-brand/', views.api_products_by_type_brand, name='api_products_by_type_brand'),

    path('chat/', views.chat_page, name='chat_page'),
    path('chat/api/', views.chat_api, name='chat_api'),
    path('chat/reset/', views.chat_reset, name='chat_reset'),

    # ----- Admin panel -----
    path('admin-panel/', views_admin.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/analytics/', views_admin.admin_analytics, name='admin_analytics'),

    path('admin-panel/productos/', views_admin.admin_products, name='admin_products'),
    path('admin-panel/productos/<int:pk>/', views_admin.admin_product_detail, name='admin_product_detail'),
    path('admin-panel/productos/<int:pk>/toggle/', views_admin.admin_product_toggle, name='admin_product_toggle'),
    path('admin-panel/productos/<int:pk>/delete/', views_admin.admin_product_delete, name='admin_product_delete'),

    path('admin-panel/usuarios/', views_admin.admin_users, name='admin_users'),
    path('admin-panel/usuarios/<int:pk>/', views_admin.admin_user_detail, name='admin_user_detail'),
    path('admin-panel/usuarios/<int:pk>/toggle/', views_admin.admin_user_toggle, name='admin_user_toggle'),
    path('admin-panel/usuarios/<int:pk>/delete/', views_admin.admin_user_delete, name='admin_user_delete'),

    path('admin-panel/reportes/', views_admin.admin_reports, name='admin_reports'),
    path('admin-panel/reportes/<int:pk>/', views_admin.admin_report_detail, name='admin_report_detail'),
    path('admin-panel/reportes/<int:pk>/<str:action>/', views_admin.admin_report_action, name='admin_report_action'),

    path('reportar/producto/<int:producto_id>/', views.reportar_producto, name='reportar_producto'),

]

