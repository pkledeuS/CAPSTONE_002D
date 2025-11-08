# app/urls.py
from django.urls import path
from . import views
from . import views_admin
from . import views_reco

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

    path('tienda/<int:tienda_id>/', views.store_detail, name='store_detail'),
    path('tienda/ofertas/', views.store_offers_list, name='store_offers_list'),
    path('tienda/ofertas/nueva/', views.store_offer_new, name='store_offer_new'),
    path('tienda/ofertas/<int:oferta_id>/editar/', views.store_offer_edit, name='store_offer_edit'),
    path('tienda/ofertas/<int:oferta_id>/eliminar/', views.store_offer_delete, name='store_offer_delete'),
    path('tienda/ofertas/<int:oferta_id>/quick-edit/', views.store_offer_quick_edit, name='store_offer_quick_edit'),

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

    path('admin-panel/tiendas/', views_admin.admin_stores, name='admin_stores'),
    path('admin-panel/usuarios/', views_admin.admin_users, name='admin_users'),
    path('admin-panel/productos/', views_admin.admin_products, name='admin_products'),
    path('admin-panel/reportes/', views_admin.admin_reports, name='admin_reports'),

    # acciones de producto:
    path('reportar/producto/<int:producto_id>/', views.reportar_producto, name='reportar_producto'),

    # URLs para reportes (admin)
    path('admin-panel/reports/', views_admin.admin_reports, name='admin_reports'),
    path('admin-panel/reports/<int:pk>/', views_admin.admin_report_detail, name='admin_report_detail'),
    path('admin-panel/reports/<int:pk>/<str:action>/', views_admin.admin_report_action, name='admin_report_action'),
    
    # URLs para notificaciones (tienda)
    path('store/notifications/', views.store_notifications, name='store_notifications'),
    path('notifications/<int:notification_id>/mark-read/', views.mark_notification_read, name='mark_notification_read'),

    # URLs de administración de productos
    path('admin-panel/products/', views_admin.admin_products, name='admin_products'),
    path('admin-panel/products/<int:pk>/', views_admin.admin_product_detail, name='admin_product_detail'),
    path('admin-panel/productos/<int:pk>/toggle/', views_admin.admin_product_toggle, name='admin_product_toggle'),
    path('admin-panel/productos/<int:pk>/delete/', views_admin.admin_product_delete, name='admin_product_delete'),
    
    # URL para reportar tiendas
    path('reportar/tienda/<int:tienda_id>/', views.reportar_tienda, name='reportar_tienda'),
    # URLs para administración de tiendas
    path('admin-panel/tiendas/<int:pk>/toggle/', views_admin.admin_store_toggle, name='admin_store_toggle'),
    path('admin-panel/tiendas/<int:pk>/delete/', views_admin.admin_store_delete, name='admin_store_delete'),
    path('admin-panel/tiendas/<int:pk>/', views_admin.admin_store_detail, name='admin_store_detail'),

    # URLs para administración de usuarios
    path('admin-panel/usuarios/<int:pk>/', views_admin.admin_user_detail, name='admin_user_detail'),
    path('admin-panel/usuarios/<int:pk>/toggle/', views_admin.admin_user_toggle, name='admin_user_toggle'),
    path('admin-panel/usuarios/<int:pk>/delete/', views_admin.admin_user_delete, name='admin_user_delete'),





    path('lab/reco-home/', views_reco.reco_home, name='reco_home'),

    path('lab/reco-explore/', views_reco.reco_explore, name='reco_explore'),

    path('lab/reco-detail/', views_reco.reco_detail, name='reco_detail'),

    path('lab/reco-guides/', views_reco.reco_guides, name='reco_guides'),

    path('lab/reco-preferences/', views_reco.reco_preferences, name='reco_preferences'),

    path('lab/reco-saved/', views_reco.reco_saved, name='reco_saved'),

]
