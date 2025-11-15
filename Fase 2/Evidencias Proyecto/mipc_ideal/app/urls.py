# app/urls.py
from django.urls import path
from . import views
from . import views_admin
from . import views_reco

urlpatterns = [
    # =======================
    # Rutas públicas / Lab
    # =======================
    path('', views_reco.reco_home, name='reco_home'),
    path('lab/reco-explore/', views_reco.reco_explore, name='reco_explore'),
    path('lab/reco-detail/', views_reco.reco_detail, name='reco_detail'),
    path('lab/reco-guides/', views_reco.reco_guides, name='reco_guides'),
    path('lab/reco-preferences/', views_reco.reco_preferences, name='reco_preferences'),
    path('lab/reco-checklist/', views_reco.reco_update_checklist, name='reco_update_checklist'),
    path('lab/reco-radar/', views_reco.reco_radar, name='reco_radar'),
    path('lab/reco-saved/', views_reco.reco_saved, name='reco_saved'),
    path('lab/reco-favorite/', views_reco.reco_toggle_favorite, name='reco_toggle_favorite'),

    # =======================
    # Auth / páginas públicas
    # =======================
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout, name='logout'),
    path('edit_profile/', views.edit_profile, name='edit_profile'),
    path('info/', views.info, name='info'),

    # =======================
    # Utilidades API
    # =======================
    path('referencia/<int:reference_id>/', views.reference_redirect, name='reference_redirect'),
    path('check_username/', views.check_username, name='check_username'),
    path('check_email/', views.check_email, name='check_email'),
    path('reportar/producto/<int:producto_id>/', views.reportar_producto, name='reportar_producto'),

    # =======================
    # Panel admin
    # =======================
    path('admin-panel/', views_admin.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/analytics/', views_admin.admin_analytics, name='admin_analytics'),

    path('admin-panel/productos/', views_admin.admin_products, name='admin_products'),
    path('admin-panel/productos/nuevo/', views_admin.admin_product_create, name='admin_product_create'),
    path('admin-panel/productos/<int:pk>/', views_admin.admin_product_detail, name='admin_product_detail'),
    path('admin-panel/productos/<int:pk>/editar/', views_admin.admin_product_edit, name='admin_product_edit'),
    path('admin-panel/productos/<int:pk>/toggle/', views_admin.admin_product_toggle, name='admin_product_toggle'),
    path('admin-panel/productos/<int:pk>/delete/', views_admin.admin_product_delete, name='admin_product_delete'),

    path('admin-panel/usuarios/', views_admin.admin_users, name='admin_users'),
    path('admin-panel/usuarios/<int:pk>/', views_admin.admin_user_detail, name='admin_user_detail'),
    path('admin-panel/usuarios/<int:pk>/toggle/', views_admin.admin_user_toggle, name='admin_user_toggle'),
    path('admin-panel/usuarios/<int:pk>/delete/', views_admin.admin_user_delete, name='admin_user_delete'),

    path('admin-panel/reportes/', views_admin.admin_reports, name='admin_reports'),
    path('admin-panel/reportes/<int:pk>/', views_admin.admin_report_detail, name='admin_report_detail'),
    path('admin-panel/reportes/<int:pk>/<str:action>/', views_admin.admin_report_action, name='admin_report_action'),
]

