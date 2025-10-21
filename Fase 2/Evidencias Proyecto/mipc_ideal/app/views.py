from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from .forms import RegisterForm
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.template import loader
from .models import (
    Producto, CategoriaProducto, TipoProducto,
    TipoServicio, PreferenciaUsuario, TiendaCategoria,
    Tienda, Profile
)

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

# Create your views here.
def home(request):
    productos_vistos = Producto.objects.order_by('-vistas')[:6]
    productos_recientes = Producto.objects.order_by('-fecha_creacion')[:6]
    
    return render(request, 'home.html', {
        'productos_vistos': productos_vistos,
        'productos_recientes': productos_recientes
    })


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
    session_key = f'viewed_product_{producto_id}'

    if not request.session.get(session_key, False):
        producto.vistas += 1
        producto.save(update_fields=['vistas'])
        request.session[session_key] = True

    return render(request, 'product-detail.html', {'producto': producto})


def products_by_category(request, categoria_id):
    categoria = CategoriaProducto.objects.get(id=categoria_id)
    productos = Producto.objects.filter(categoria_producto=categoria)
    productos_recientes = productos.order_by('-fecha_creacion')[:6]
    return render(request, 'products-view.html', {
        'productos': productos,
        'productos_recientes': productos_recientes,
        'categoria': categoria
    })

def products_by_type(request, tipo_id):
    tipo = TipoProducto.objects.get(id=tipo_id)
    productos = Producto.objects.filter(tipo_producto=tipo)
    productos_recientes = productos.order_by('-fecha_creacion')[:6]
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

            return redirect('edit_profile')
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
def edit_profile(request):
    user = request.user
    profile = Profile.objects.get(user=user)
    context = {'user': user, 'profile_type': profile.profile_type}

    # --- PERFIL USUARIO ---
    if profile.profile_type == 'usuario':
        categorias = CategoriaProducto.objects.all()
        tipos = TipoProducto.objects.all()

        if request.method == 'POST':
            username = request.POST.get('username')
            new_email = request.POST.get('new_email')
            new_password = request.POST.get('new_password')

            # Actualizar datos básicos
            if username:
                user.username = username
            if new_email:
                user.email = new_email
            if new_password:
                user.set_password(new_password)
            user.save()

            # Actualizar preferencias
            PreferenciaUsuario.objects.filter(usuario=user).delete()
            seleccion_categorias = request.POST.getlist('categorias')
            seleccion_tipos = request.POST.getlist('tipos')

            for categoria_id in seleccion_categorias:
                PreferenciaUsuario.objects.create(usuario=user, categoria_id=categoria_id)
            for tipo_id in seleccion_tipos:
                PreferenciaUsuario.objects.create(usuario=user, tipo_producto_id=tipo_id)

            messages.success(request, "Cambios guardados correctamente.")
            return redirect('edit_profile')

        else:
            seleccionadas = PreferenciaUsuario.objects.filter(usuario=user)

        context.update({
            'categorias': categorias,
            'tipos': tipos,
            'seleccionadas_categorias': list(seleccionadas.values_list('categoria_id', flat=True)),
            'seleccionadas_tipos': list(seleccionadas.values_list('tipo_producto_id', flat=True))
        })

    # --- PERFIL TIENDA ---
    elif profile.profile_type == 'tienda':
        servicios = TipoServicio.objects.all()
        categorias = CategoriaProducto.objects.all()

        # Obtener tienda asociada al usuario
        tienda = Tienda.objects.filter(user=user).first()

        if request.method == 'POST':
            username = request.POST.get('username')
            new_email = request.POST.get('new_email')
            new_password = request.POST.get('new_password')

            # Actualizar datos básicos
            if username:
                user.username = username
            if new_email:
                user.email = new_email
            if new_password:
                user.set_password(new_password)
            user.save()

            # Actualizar servicios y categorías de la tienda
            TiendaCategoria.objects.filter(tienda=tienda).delete()
            seleccion_categorias = request.POST.getlist('categorias')
            seleccion_servicios = request.POST.getlist('servicios')

            for categoria_id in seleccion_categorias:
                TiendaCategoria.objects.create(tienda=tienda, categoria_id=categoria_id)

            # (Opcional) si manejas relación directa con servicios
            if hasattr(tienda, 'servicios'):
                tienda.servicios.clear()
                for servicio_id in seleccion_servicios:
                    tienda.servicios.add(servicio_id)

            messages.success(request, "Cambios de tienda guardados correctamente.")
            return redirect('edit_profile')

        else:
            seleccionadas_categorias = TiendaCategoria.objects.filter(tienda=tienda).values_list('categoria_id', flat=True)
            seleccionados_servicios = []
            if hasattr(tienda, 'servicios'):
                seleccionados_servicios = tienda.servicios.values_list('id', flat=True)

        context.update({
            'servicios': servicios,
            'categorias': categorias,
            'seleccionadas_categorias': list(seleccionadas_categorias),
            'seleccionados_servicios': list(seleccionados_servicios)
        })

    return render(request, 'edit-profile.html', context)


def check_username(request):
    username = request.GET.get('username', None)
    exists = User.objects.filter(username__iexact=username).exists()
    return JsonResponse({'exists': exists})

def check_email(request):
    email = request.GET.get('email', None)
    exists = User.objects.filter(email__iexact=email).exists()
    return JsonResponse({'exists': exists})

@login_required
def preferences_products_view(request):
    user = request.user
    preferencias = PreferenciaUsuario.objects.filter(usuario=user)

    # IDs de preferencias
    categorias_ids = list(preferencias.values_list('categoria_id', flat=True))
    tipos_ids = list(preferencias.values_list('tipo_producto_id', flat=True))

    # Si el usuario seleccionó ambos tipos de filtro → intersección
    if categorias_ids and tipos_ids:
        productos = Producto.objects.filter(
            categoria_producto__in=categorias_ids,
            tipo_producto__in=tipos_ids
        ).distinct()

    # Si solo hay categorías
    elif categorias_ids:
        productos = Producto.objects.filter(
            categoria_producto__in=categorias_ids
        ).distinct()

    # Si solo hay tipos
    elif tipos_ids:
        productos = Producto.objects.filter(
            tipo_producto__in=tipos_ids
        ).distinct()

    else:
        productos = Producto.objects.none()

    return render(request, 'preferences-products-view.html', {
        'productos': productos,
    })