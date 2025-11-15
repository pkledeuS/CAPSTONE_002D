# app/views.py
import unicodedata
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from .forms import RegisterForm
from .models import Profile, Producto, Reporte, ProductReference, ReferenceVisit
# =========================
#   SPEC TEMPLATES + CANON
# =========================
# Plantillas de campos (orden deseado en UI) por TIPO de producto
SPEC_TEMPLATES = {
    'Procesador': [
        'Frecuencia', 'Frecuencia turbo máxima', 'Núcleos / hilos', 'Caché',
        'Socket', 'Núcleo', 'Proceso de manufactura', 'TDP', 'Cooler', 'Gráficos integrados'
    ],
    'Memoria RAM': [
        'Capacidad', 'Tipo', 'Velocidad', 'Formato', 'Voltaje',
        'Latencia CI (CAS)', 'Latencia Trcd', 'Latencia Trp', 'Latencia Tras',
        'Soporte ECC', 'Soporte full buffered'
    ],
    'Fuente de poder': [
        'Potencia', 'Certificación', 'Tamaño', 'PFC activo', 'Modular',
        'Corriente en la línea de 12V', 'Corriente en la línea de 5V', 'Corriente en la línea de 3.3V'
    ],
    'Tarjetas Gráficas': [
        'Fabricante', 'GPU', 'Memoria', 'Bus',
        'Frecuencias core (base / boost / OC)', 'Frecuencia memorias',
        'Núcleo', 'Perfil', 'Refrigeración', 'Slots', 'Largo',
        'Iluminación', '¿Backplate?', 'Conectores de poder', 'Puertos de video'
    ],
    'Placas madre': [
        'Socket', 'Chipset', 'Factor de forma', 'Fases VRM',
        'Slots RAM', 'Máx RAM', 'Slots M.2', 'Puertos SATA',
        'Wi-Fi', 'Bluetooth', 'LAN', 'Audio', 'Puertos traseros', 'BIOS/UEFI'
    ],
    'Notebook': [
        'Procesador', 'Núcleos', 'RAM', 'Pantalla', 'Resolución', 'Tasa de refresco',
        'Batería', 'Almacenamiento', 'Tarjeta de Video', 'Puertos',
        'Conectividad', 'Webcam', 'Teclado retroiluminado', 'Peso', 'SO', 'Idioma teclado'
    ],
    'Computador': [
        'Procesador', 'Núcleos', 'RAM', 'Almacenamiento', 'Tarjeta de Video',
        'Fuente de poder', 'Placa madre', 'Gabinete', 'Puertos', 'Conectividad', 'SO'
    ],
    'All-in-One': [
        'Procesador', 'Núcleos', 'RAM', 'Pantalla', 'Resolución',
        'Almacenamiento', 'Tarjeta de Video', 'Puertos', 'Conectividad',
        'Peso', 'SO', 'Periféricos inalámbricos'
    ],
    'Tablet': [
        'Part number', 'Pantalla', 'Resolución', 'Memoria interna', 'RAM',
        'Conectividad celular', 'Sistema operativo', 'Color', 'Peso', 'Dimensiones',
        'Almacenamiento externo', 'Batería', 'Cámara principal', 'Cámara frontal',
        'GPS', 'Bluetooth', 'Salida de audífonos', 'Procesador', 'CPU', 'GPU'
    ],
}
def _norm_key(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = " ".join(s.split())
    return s
SPEC_CANON = {
    # CPU
    _norm_key("frecuencia"): "Frecuencia",
    _norm_key("clock"): "Frecuencia",
    _norm_key("frecuencia turbo maxima"): "Frecuencia turbo máxima",
    _norm_key("boost"): "Frecuencia turbo máxima",
    _norm_key("núcleos / hilos"): "Núcleos / hilos",
    _norm_key("nucleos / hilos"): "Núcleos / hilos",
    _norm_key("cache"): "Caché",
    _norm_key("socket"): "Socket",
    _norm_key("tdp"): "TDP",
    _norm_key("graficos integrados"): "Gráficos integrados",
    _norm_key("litografia"): "Proceso de manufactura",
    _norm_key("proceso de manufactura"): "Proceso de manufactura",
    _norm_key("nucleo"): "Núcleo",
    # RAM
    _norm_key("capacidad"): "Capacidad",
    _norm_key("tipo"): "Tipo",
    _norm_key("velocidad"): "Velocidad",
    _norm_key("formato"): "Formato",
    _norm_key("voltaje"): "Voltaje",
    _norm_key("latencia cas"): "Latencia CI (CAS)",
    _norm_key("cl"): "Latencia CI (CAS)",
    _norm_key("cas latency"): "Latencia CI (CAS)",
    # PSU
    _norm_key("potencia"): "Potencia",
    _norm_key("certificacion"): "Certificación",
    _norm_key("80 plus"): "Certificación",
    _norm_key("80plus"): "Certificación",
    _norm_key("tamano"): "Tamaño",
    _norm_key("form factor"): "Tamaño",
    _norm_key("pfc activo"): "PFC activo",
    _norm_key("pfc"): "PFC activo",
    _norm_key("modular"): "Modular",
    _norm_key("semi modular"): "Modular",
    _norm_key("full modular"): "Modular",
    _norm_key("corriente 12v"): "Corriente en la línea de 12V",
    _norm_key("corriente 5v"): "Corriente en la línea de 5V",
    _norm_key("corriente 3.3v"): "Corriente en la línea de 3.3V",
    # GPU
    _norm_key("fabricante"): "Fabricante",
    _norm_key("gpu"): "GPU",
    _norm_key("memoria"): "Memoria",
    _norm_key("vram"): "Memoria",
    _norm_key("bus"): "Bus",
    _norm_key("frecuencias core (base / boost / oc)"): "Frecuencias core (base / boost / OC)",
    _norm_key("frecuencia memorias"): "Frecuencia memorias",
    _norm_key("refrigeracion"): "Refrigeración",
    _norm_key("slots"): "Slots",
    _norm_key("largo"): "Largo",
    _norm_key("iluminacion"): "Iluminación",
    _norm_key("backplate"): "¿Backplate?",
    _norm_key("conectores de poder"): "Conectores de poder",
    _norm_key("puertos de video"): "Puertos de video",
    _norm_key("salidas de video"): "Puertos de video",
    # Motherboard
    _norm_key("chipset"): "Chipset",
    _norm_key("factor de forma"): "Factor de forma",
    _norm_key("formato"): "Factor de forma",
    _norm_key("fases vrm"): "Fases VRM",
    _norm_key("etapas vrm"): "Fases VRM",
    _norm_key("slots ram"): "Slots RAM",
    _norm_key("max ram"): "Máx RAM",
    _norm_key("memoria maxima"): "Máx RAM",
    _norm_key("slots m.2"): "Slots M.2",
    _norm_key("puertos sata"): "Puertos SATA",
    _norm_key("wifi"): "Wi-Fi",
    _norm_key("bluetooth"): "Bluetooth",
    _norm_key("lan"): "LAN",
    _norm_key("audio"): "Audio",
    _norm_key("puertos traseros"): "Puertos traseros",
    _norm_key("bios"): "BIOS/UEFI",
    _norm_key("uefi"): "BIOS/UEFI",
    # Notebook / AIO / Computador
    _norm_key("procesador"): "Procesador",
    _norm_key("nucleos"): "Núcleos",
    _norm_key("ram"): "RAM",
    _norm_key("pantalla"): "Pantalla",
    _norm_key("resolucion"): "Resolución",
    _norm_key("tasa de refresco"): "Tasa de refresco",
    _norm_key("hz"): "Tasa de refresco",
    _norm_key("bateria"): "Batería",
    _norm_key("almacenamiento"): "Almacenamiento",
    _norm_key("tarjeta de video"): "Tarjeta de Video",
    _norm_key("gpu dedicada"): "Tarjeta de Video",
    _norm_key("puertos"): "Puertos",
    _norm_key("conectividad"): "Conectividad",
    _norm_key("webcam"): "Webcam",
    _norm_key("teclado retroiluminado"): "Teclado retroiluminado",
    _norm_key("peso"): "Peso",
    _norm_key("so"): "SO",
    _norm_key("idioma teclado"): "Idioma teclado",
    _norm_key("placa madre"): "Placa madre",
    _norm_key("gabinete"): "Gabinete",
    _norm_key("perifericos inalambricos"): "Periféricos inalámbricos",
    # Tablet
    _norm_key("part number"): "Part number",
    _norm_key("memoria interna"): "Memoria interna",
    _norm_key("conectividad celular"): "Conectividad celular",
    _norm_key("sistema operativo"): "Sistema operativo",
    _norm_key("almacenamiento externo"): "Almacenamiento externo",
    _norm_key("camara principal"): "Cámara principal",
    _norm_key("camara frontal"): "Cámara frontal",
    _norm_key("bluetooth"): "Bluetooth",
    _norm_key("gps"): "GPS",
    _norm_key("salida de audifonos"): "Salida de audífonos",
}
# =========================
#   AUTH + PERFIL
# =========================
def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Cuenta creada correctamente.")
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(request, username=username, password=password)
            if user is not None:
                auth_login(request, user)
            return redirect("edit_profile")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})

def login(request):
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            messages.success(request, f"Bienvenido {user.username}")
            if user.is_staff or user.is_superuser:
                return redirect("admin_dashboard")
            return redirect("reco_home")
        messages.error(request, "Usuario o contrasena incorrectos.")
    return render(request, "registration/login.html")

def logout(request):
    auth_logout(request)
    return redirect("reco_home")

@login_required
def edit_profile(request):
    user = request.user
    profile, _ = Profile.objects.get_or_create(
        user=user,
        defaults={"profile_type": "admin" if user.is_staff else "usuario"},
    )
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        new_email = (request.POST.get("new_email") or "").strip()
        new_password = (request.POST.get("new_password") or "").strip()
        if username:
            user.username = username
        if new_email:
            user.email = new_email
        if new_password:
            user.set_password(new_password)
        user.save()
        messages.success(request, "Cambios guardados correctamente.")
        return redirect("edit_profile")
    context = {
        "user": user,
        "profile_type": profile.profile_type,
    }
    return render(request, "edit-profile.html", context)


def info(request):
    return render(request, "info.html")
# =========================
#   REPORTES / UTILIDADES
# =========================
def check_username(request):
    username = request.GET.get("username", "")
    exists = User.objects.filter(username__iexact=username).exists()
    return JsonResponse({"exists": exists})
def check_email(request):
    email = request.GET.get("email", "")
    exists = User.objects.filter(email__iexact=email).exists()
    return JsonResponse({"exists": exists})

@login_required
@require_POST
def reportar_producto(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    default_redirect = f"{reverse('reco_detail')}?id={producto_id}"
    next_url = next_url or default_redirect
    
    try:
        Reporte.objects.create(
            target_type="producto",
            producto=producto,
            reporter=request.user,
            motivo=request.POST.get("motivo"),
            detalle=request.POST.get("detalle"),
        )
        messages.success(request, "Reporte enviado correctamente.")
    except Exception:
        messages.error(request, "Error al enviar el reporte.")
    return redirect(next_url)


def reference_redirect(request, reference_id):
    referencia = get_object_or_404(ProductReference, pk=reference_id)
    ReferenceVisit.objects.create(
        referencia=referencia,
        usuario=request.user if request.user.is_authenticated else None,
    )
    target = referencia.url_fuente or ""
    if not target:
        target = f"{reverse('reco_detail')}?id={referencia.producto_id}"
    return redirect(target)
