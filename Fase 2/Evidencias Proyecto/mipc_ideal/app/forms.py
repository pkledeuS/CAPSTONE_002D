import re
from django import forms
from django.contrib.auth.models import User
from .models import (
    Profile, Producto, MarcaProducto, CategoriaProducto, TipoProducto
)

class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    profile_type = forms.ChoiceField(choices=[('usuario', 'Usuario'), ('tienda', 'Tienda')])

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
            Profile.objects.create(
                user=user,
                profile_type=self.cleaned_data['profile_type']
            )
        return user
    
    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Este nombre de usuario ya está registrado.")
        return username
    
# ---------- Helpers de normalización ----------
_THOUSANDS_RX = re.compile(r'(\d)[\.\s](\d{3}\b)')

def _strip_thousands(s: str) -> str:
    """Elimina separadores de miles tipo 5.500 -> 5500 (puede aplicarse varias veces)."""
    if not s:
        return s
    prev = None
    while prev != s:
        prev = s
        s = _THOUSANDS_RX.sub(r'\1\2', s)
    return s

def normalize_model_display(s: str) -> str:
    """
    Normaliza para mostrar: colapsa espacios, elimina miles en números, mantiene guiones útiles.
    'Ryzen 5 5.500' -> 'Ryzen 5 5500', 'AN515-58' se conserva.
    """
    if not s:
        return s
    s = s.strip()
    s = _strip_thousands(s)
    s = re.sub(r'\s+', ' ', s)
    return s

def model_key(s: str) -> str:
    """
    Llave canónica para deduplicar modelos (case-insensitive, sin espacios/guiones/puntos).
    Regla especial: si hay dos tokens numéricos consecutivos y el primero es 1 dígito
    y coincide con el prefijo del siguiente (p.ej. '5' y '5500'), descartamos el primero.
    """
    if not s:
        return ""
    disp = normalize_model_display(s).lower()

    # tokeniza conservando guiones alfanum: 'i7-12700H' -> ['i7-12700h']
    tokens = re.split(r'\s+', disp)

    # divide tokens mixtos en sub-tokens alfanum y num (para detectar '5' + '5500')
    split_tokens = []
    for tok in tokens:
        parts = re.findall(r'[a-z]+|\d+|-+', tok)
        if parts:
            split_tokens.extend(parts)
        else:
            split_tokens.append(tok)

    out = []
    i = 0
    while i < len(split_tokens):
        cur = split_tokens[i]
        nxt = split_tokens[i+1] if i + 1 < len(split_tokens) else None
        if cur.isdigit() and len(cur) == 1 and nxt and nxt.isdigit() and len(nxt) >= 3 and nxt.startswith(cur):
            # descarta el dígito 'serie' si le sigue el modelo largo comenzando con ese dígito
            i += 1
            continue
        out.append(cur)
        i += 1

    # quita todo lo que no sea [a-z0-9], pega todo
    joined = ''.join(re.sub(r'[^a-z0-9]', '', t) for t in out)
    return joined

# ---------- Formularios ----------

class ExistingProductOfferForm(forms.Form):
    producto = forms.ModelChoiceField(
        queryset=Producto.objects.all(),
        label="Producto"
    )
    precio = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=0,
        label="Precio (CLP)"
    )
    url_externa = forms.URLField(required=False, label="URL en tu tienda")
    stock = forms.IntegerField(min_value=0, required=False, initial=0, label="Stock")
    nota_tienda = forms.CharField(max_length=200, required=False, label="Nota visible")

class NewProductAndOfferForm(forms.Form):
    # OJO: quitamos 'nombre_producto' (se autogenera)
    modelo_producto = forms.CharField(max_length=100, label="Modelo")
    descripcion_producto = forms.CharField(widget=forms.Textarea, required=False, label="Descripción")
    imagen_producto = forms.ImageField(required=False, label="Imagen")

    marca_producto = forms.ModelChoiceField(queryset=MarcaProducto.objects.all(), label="Marca")
    categoria_producto = forms.ModelChoiceField(queryset=CategoriaProducto.objects.all(), label="Categoría")
    tipo_producto = forms.ModelChoiceField(queryset=TipoProducto.objects.all(), label="Tipo")

    precio = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, label="Precio (CLP)")
    url_externa = forms.URLField(required=False, label="URL en tu tienda")
    stock = forms.IntegerField(min_value=0, required=False, initial=0, label="Stock")
    nota_tienda = forms.CharField(max_length=200, required=False, label="Nota visible")

    # campos “virtuales” para usar en la vista
    _modelo_key = None
    _modelo_display = None
    _nombre_autogen = None

    def clean_modelo_producto(self):
        raw = self.cleaned_data.get('modelo_producto', '')
        disp = normalize_model_display(raw)
        self._modelo_display = disp
        self._modelo_key = model_key(disp)
        return disp

    def clean(self):
        cleaned = super().clean()
        marca = cleaned.get('marca_producto')
        # autogenerar nombre para guardar (Marca + Modelo normalizado)
        if marca and self._modelo_display:
            self._nombre_autogen = f"{marca.nombre_marca} {self._modelo_display}"
        return cleaned