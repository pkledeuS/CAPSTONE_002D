# -*- coding: utf-8 -*-
"""
Cómo usar:
    python manage.py shell < attach_specs.py

Qué hace:
- Recorre tus Productos existentes.
- Si un producto NO tiene especificaciones, genera un set realista según su Tipo (CPU, RAM, PSU, Notebook, Computador, Tablet)
  y su Categoría (Gamer, Hogar, Estudio, Trabajo, Diseño).
- No duplica: si ya hay specs para un producto, lo deja tal cual.
"""

import random
from django.db import transaction
from app.models import Producto, EspecificacionProducto

# --- Helpers ---------------------------------------------------------------

def level_from_categoria(nombre):
    """
    Devuelve un 'nivel' aproximado según la categoría para escalar specs.
    Mayor = mejores especificaciones.
    """
    if not nombre:
        return 2
    nombre = nombre.lower()
    if "gamer" in nombre:
        return 4
    if "diseño" in nombre or "diseno" in nombre:
        return 4
    if "trabajo" in nombre:
        return 3
    if "estudio" in nombre:
        return 2
    if "hogar" in nombre:
        return 1
    return 2

def rand_range(base_min, base_max, lvl, step=1):
    """
    Ajusta un rango base según 'lvl'.
    lvl 1 => -10%, lvl 4 => +20% aprox.
    """
    scale = {1: 0.9, 2: 1.0, 3: 1.1, 4: 1.2}.get(lvl, 1.0)
    lo = int(base_min * scale)
    hi = int(base_max * scale)
    if lo >= hi:
        lo, hi = base_min, base_max
    # fuerza pasos
    lo = (lo // step) * step
    hi = (hi // step) * step
    return random.randrange(lo, hi + step, step)

def make_cpu_specs(p, lvl):
    # Núcleos/Hilos
    cores = rand_range(4, 8, lvl)
    threads = cores * 2 if cores <= 12 else int(cores * 1.5)
    base = round(rand_range(3200, 3700, lvl, 100) / 1000.0, 2)  # GHz
    boost = round(base + random.choice([0.5, 0.6, 0.7, 0.8]), 2)
    tdp = rand_range(45, 125, lvl, 5)
    sockets = ["AM4", "AM5", "LGA1200", "LGA1700"]
    arch = random.choice(["Zen 3", "Zen 4", "Alder Lake", "Raptor Lake"])
    return [
        ("Núcleos", str(cores)),
        ("Hilos", str(threads)),
        ("Frecuencia base", f"{base} GHz"),
        ("Frecuencia turbo", f"{boost} GHz"),
        ("TDP", f"{tdp} W"),
        ("Socket", random.choice(sockets)),
        ("Arquitectura", arch),
    ]

def make_ram_specs(p, lvl):
    cap = rand_range(8, 32, lvl, 8)  # GB
    speed = rand_range(2666, 6000, lvl, 200)  # MHz
    ddr = random.choice(["DDR4", "DDR5"])
    cas = random.choice([16, 18, 22, 30, 36])
    volt = random.choice([1.2, 1.25, 1.35])
    return [
        ("Capacidad", f"{cap} GB"),
        ("Velocidad", f"{speed} MHz"),
        ("Tipo", ddr),
        ("Latencia CAS", f"CL{cas}"),
        ("Voltaje", f"{volt} V"),
        ("Disipación", random.choice(["Sí", "No"])),
    ]

def make_psu_specs(p, lvl):
    watt = rand_range(450, 1000, lvl, 50)
    eff = random.choice(["80+ Bronze", "80+ Silver", "80+ Gold", "80+ Platinum"])
    modular = random.choice(["No modular", "Semi-modular", "Full modular"])
    protec = "OVP/OPP/SCP/UVP"
    size = random.choice(["ATX", "SFX"])
    return [
        ("Potencia", f"{watt} W"),
        ("Certificación", eff),
        ("Modularidad", modular),
        ("Protecciones", protec),
        ("Formato", size),
        ("Garantía", random.choice(["3 años", "5 años"])),
    ]

def make_notebook_specs(p, lvl):
    cpu = random.choice(["Intel i5", "Intel i7", "Ryzen 5", "Ryzen 7"])
    ram = rand_range(8, 32, lvl, 8)
    ssd = rand_range(256, 1024, lvl, 128)
    screen = random.choice(["14\" FHD 60Hz", "15.6\" FHD 60Hz", "16\" 120Hz", "14\" 120Hz"])
    gpu = random.choice(["Integrada", "RTX 3050", "RTX 4050", "Radeon 660M"])
    weight = round(random.uniform(1.2, 2.4), 2)
    battery = rand_range(45, 80, lvl, 5)  # Wh
    os = random.choice(["Windows 11", "Windows 10", "Linux"])
    return [
        ("CPU", cpu),
        ("RAM", f"{ram} GB"),
        ("Almacenamiento", f"{ssd} GB SSD"),
        ("Pantalla", screen),
        ("GPU", gpu),
        ("Peso", f"{weight} kg"),
        ("Batería", f"{battery} Wh"),
        ("Sistema operativo", os),
    ]

def make_pc_specs(p, lvl):
    cpu = random.choice(["Ryzen 5", "Ryzen 7", "Intel i5", "Intel i7"])
    ram = rand_range(16, 64, lvl, 8)
    gpu = random.choice(["RTX 3060", "RTX 4060", "RTX 4070", "RX 7600", "Integrada"])
    ssd = rand_range(512, 2048, lvl, 256)
    psu = rand_range(550, 850, lvl, 50)
    case = random.choice(["ATX", "Micro-ATX", "Mini-ITX"])
    return [
        ("CPU", cpu),
        ("RAM", f"{ram} GB"),
        ("GPU", gpu),
        ("Almacenamiento", f"{ssd} GB SSD"),
        ("PSU", f"{psu} W"),
        ("Formato", case),
    ]

def make_tablet_specs(p, lvl):
    soc = random.choice(["Apple M1", "Apple M2", "Snapdragon 8 Gen 2", "Tensor G2"])
    screen = random.choice(["11\" 120Hz", "12.9\" 120Hz", "10.5\" 90Hz"])
    ram = rand_range(6, 16, lvl, 2)
    storage = random.choice([128, 256, 512, 1024])
    battery = rand_range(7000, 11000, lvl, 500)  # mAh
    os = random.choice(["iPadOS", "Android 14"])
    stylus = random.choice(["Soporta lápiz", "Sin lápiz"])
    return [
        ("Procesador", soc),
        ("Pantalla", screen),
        ("RAM", f"{ram} GB"),
        ("Almacenamiento", f"{storage} GB"),
        ("Batería", f"{battery} mAh"),
        ("Sistema operativo", os),
        ("Stylus", stylus),
    ]

def build_specs_for(p):
    cat = getattr(p.categoria_producto, "nombre_categoria", "") or ""
    tipo = getattr(p.tipo_producto, "nombre_tipo", "") or ""
    lvl = level_from_categoria(cat)

    tipo_l = tipo.lower()
    if "procesador" in tipo_l or "cpu" in tipo_l:
        return make_cpu_specs(p, lvl)
    if "memoria" in tipo_l or "ram" in tipo_l:
        return make_ram_specs(p, lvl)
    if "fuente" in tipo_l:
        return make_psu_specs(p, lvl)
    if "notebook" in tipo_l:
        return make_notebook_specs(p, lvl)
    if "computador" in tipo_l or "pc" in tipo_l:
        return make_pc_specs(p, lvl)
    if "tablet" in tipo_l:
        return make_tablet_specs(p, lvl)

    # fallback genérico
    return [
        ("Garantía", random.choice(["1 año", "2 años"])),
        ("Origen", random.choice(["China", "Vietnam", "México"])),
    ]

# --- Main ------------------------------------------------------------------

created_total = 0
skipped = 0

from django.db import transaction

with transaction.atomic():
    for p in Producto.objects.all().select_related("categoria_producto", "tipo_producto"):
        # Evitar duplicar
        if EspecificacionProducto.objects.filter(producto=p).exists():
            skipped += 1
            continue

        # Semilla para reproducibilidad por producto
        random.seed(p.id * 1337)

        pairs = build_specs_for(p)
        objs = [
            EspecificacionProducto(
                producto=p,
                nombre_especificacion=k,
                valor_especificacion=v
            ) for k, v in pairs
        ]
        EspecificacionProducto.objects.bulk_create(objs)
        created_total += len(objs)

print(f"Especificaciones creadas: {created_total}. Productos saltados (ya tenían specs): {skipped}.")
