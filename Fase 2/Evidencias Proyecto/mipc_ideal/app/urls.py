from django.urls import path
from django.shortcuts import redirect
from . import views

def redirect_to_home(request):
    return redirect('/home/')

urlpatterns = [
    path('', redirect_to_home, name='root'),
    path('home/', views.app_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
]