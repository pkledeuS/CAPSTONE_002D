from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader

# Create your views here.
def home(request):
    return render(request, 'home.html')

def login(request):
    return render(request, 'login.html')

def register(request):
    return render(request, 'register.html')

def edit_user(request):
    return render(request, 'edit-profile-user.html')

def edit_store(request):
    return render(request, 'edit-profile-store.html')

def products(request):
    return render(request, 'products-view.html')

def info(request):
    return render(request, 'info.html')