from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from .forms import RegisterForm
from django.contrib import messages
from django.http import HttpResponse
from django.template import loader
from .models import Producto, CategoriaProducto, TipoProducto, Preferencias, \
    TipoServicio, PreferenciasUsuario, TiendaTipoServicio, Tienda, Profile
from django.contrib.auth.decorators import login_required

# Create your views here.
def home(request):
    return render(request, 'home.html')

def edit_user(request):
    return render(request, 'edit-profile-user.html')

def edit_store(request):
    return render(request, 'edit-profile-store.html')

def info(request):
    return render(request, 'info.html')

def products(request):
    productos = Producto.objects.all()
    productos_recientes = Producto.objects.order_by('-fecha_creacion')[:6]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes
    })

def product_detail(request, producto_id):
    producto = Producto.objects.get(id=producto_id)
    return render(request, 'product-detail.html', {'producto': producto})

def products_by_category(request, categoria_id):
    categoria = CategoriaProducto.objects.get(id=categoria_id)
    productos = Producto.objects.filter(categoria_producto=categoria)
    productos_recientes = productos.order_by('-fecha_creacion')[:10]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes,
        'categoria': categoria
    })

def products_by_type(request, tipo_id):
    tipo = TipoProducto.objects.get(id=tipo_id)
    productos = Producto.objects.filter(tipo_producto=tipo)
    productos_recientes = productos.order_by('-fecha_creacion')[:10]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes,
        'tipo': tipo
    })

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Cuenta creada correctamente.")

            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                auth_login(request, user)

            return redirect('configurate_profile')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})

def login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            messages.success(request, f'Bienvenido {user.username}')
            return redirect('home')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos. Por favor, inténtalo de nuevo.')
            return render(request, 'registration/login.html')
    return render(request, 'registration/login.html')
    
def logout(request):
    auth_logout(request)
    return redirect('home')

@login_required
def configurate_profile(request):
    perfil = request.user.profile.profile_type

    if perfil == 'usuario':
        opciones = Preferencias.objects.all()
        seleccionadas = PreferenciasUsuario.objects.filter(usuario=request.user)
    else:
        tienda, created = Tienda.objects.get_or_create(user=request.user)
        opciones = TipoServicio.objects.all()
        seleccionadas = TiendaTipoServicio.objects.filter(tienda=tienda)

    if request.method == 'POST':
        if perfil == 'usuario':
            PreferenciasUsuario.objects.filter(usuario=request.user).delete()
            seleccion = request.POST.getlist('opciones')
            for opcion_id in seleccion:
                PreferenciasUsuario.objects.create(
                    usuario=request.user,
                    preferencia_id=opcion_id
                )
        else:
            TiendaTipoServicio.objects.filter(tienda=tienda).delete()
            seleccion = request.POST.getlist('opciones')
            for opcion_id in seleccion:
                TiendaTipoServicio.objects.create(
                    tienda=tienda,
                    tipo_servicio_id=opcion_id
                )
        return redirect('home')

    return render(request, 'configurate-profile.html', {
        'perfil': perfil,
        'opciones': opciones,
        'seleccionadas': seleccionadas
    })

@login_required
def edit_profile(request):
    profile = request.user.profile
    context = {
        'profile_type': profile.profile_type,
        'user': request.user
    }

    if profile.profile_type == 'usuario':
        context['opciones'] = Preferencias.objects.all()
        context['seleccionadas'] = PreferenciasUsuario.objects.filter(usuario=request.user)
    else:
        context['opciones'] = TipoServicio.objects.all()
        context['seleccionadas'] = TiendaTipoServicio.objects.filter(tienda=request.user.tienda)

    if request.method == 'POST':
        username = request.POST.get('username')
        new_email = request.POST.get('new_email')
        new_password = request.POST.get('new_password')

        if username:
            request.user.username = username
        if new_email:
            request.user.email = new_email
        if new_password:
            request.user.set_password(new_password)
        request.user.save()

        # Actualizar preferencias o servicios
        seleccion = request.POST.getlist('opciones')
        if profile.profile_type == 'usuario':
            PreferenciasUsuario.objects.filter(usuario=request.user).delete()
            for opcion_id in seleccion:
                PreferenciasUsuario.objects.create(
                    usuario=request.user,
                    preferencia_id=opcion_id
                )
        else:
            TiendaTipoServicio.objects.filter(tienda=request.user.tienda).delete()
            for opcion_id in seleccion:
                TiendaTipoServicio.objects.create(
                    tienda=request.user.tienda,
                    tipo_servicio_id=opcion_id
                )

        messages.success(request, 'Perfil actualizado correctamente.')
        return redirect('edit_profile')

    return render(request, 'edit-profile.html', context)