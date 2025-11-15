from django import forms
from django.contrib.auth.models import User
from django.forms import inlineformset_factory

from .models import (
    CategoriaProducto,
    EspecificacionProducto,
    MarcaProducto,
    ProductReference,
    ProductReview,
    Producto,
    Profile,
    TipoProducto,
)


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["username", "email", "password"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            Profile.objects.create(user=user, profile_type="usuario")
        return user

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Este nombre de usuario ya esta registrado.")
        return username


class ProductReviewForm(forms.ModelForm):
    class Meta:
        model = ProductReview
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.NumberInput(attrs={"min": 1, "max": 5, "class": "d-none", "id": "rating-input"}),
            "comment": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Cuentanos que te gusto o no del producto...",
                    "class": "form-control",
                }
            ),
        }
        labels = {
            "rating": "Calificacion",
            "comment": "Comentario (opcional)",
        }

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        if not rating:
            raise forms.ValidationError("Selecciona una calificacion (1 a 5).")
        if rating < 1 or rating > 5:
            raise forms.ValidationError("La calificacion debe estar entre 1 y 5.")
        return rating


class AdminProductForm(forms.ModelForm):
    imagen_producto = forms.ImageField(required=False)
    categorias_extra = forms.ModelMultipleChoiceField(
        queryset=CategoriaProducto.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "4"}),
        label="Categorias adicionales",
    )

    class Meta:
        model = Producto
        fields = [
            "nombre_producto",
            "descripcion_producto",
            "modelo_producto",
            "imagen_producto",
            "marca_producto",
            "categoria_producto",
            "tipo_producto",
            "categorias_extra",
            "is_active",
        ]
        widgets = {
            "nombre_producto": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion_producto": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "modelo_producto": forms.TextInput(attrs={"class": "form-control"}),
            "marca_producto": forms.Select(attrs={"class": "form-select"}),
            "categoria_producto": forms.Select(attrs={"class": "form-select"}),
            "tipo_producto": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "nombre_producto": "Nombre comercial",
            "descripcion_producto": "Descripcion",
            "modelo_producto": "Modelo / SKU",
            "imagen_producto": "Imagen principal",
            "marca_producto": "Marca",
            "categoria_producto": "Categoria principal",
            "tipo_producto": "Tipo de producto",
            "categorias_extra": "Categorias adicionales",
            "is_active": "Mostrar en el catalogo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categorias_extra"].queryset = CategoriaProducto.objects.order_by("nombre_categoria")
        self.fields["marca_producto"].queryset = MarcaProducto.objects.order_by("nombre_marca")
        self.fields["categoria_producto"].queryset = CategoriaProducto.objects.order_by("nombre_categoria")
        self.fields["tipo_producto"].queryset = TipoProducto.objects.order_by("nombre_tipo")

    def clean_imagen_producto(self):
        imagen = self.cleaned_data.get("imagen_producto")
        if not imagen and not (self.instance and self.instance.pk and self.instance.imagen_producto):
            raise forms.ValidationError("Debes subir una imagen para el producto.")
        return imagen or self.instance.imagen_producto


class ProductReferenceForm(forms.ModelForm):
    class Meta:
        model = ProductReference
        fields = ["nombre_fuente", "url_fuente", "precio", "stock", "nota"]
        widgets = {
            "nombre_fuente": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre de la tienda"}),
            "url_fuente": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
            "precio": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "stock": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "nota": forms.TextInput(attrs={"class": "form-control", "placeholder": "Opcional"}),
        }
        labels = {
            "nombre_fuente": "Tienda / Fuente",
            "url_fuente": "URL",
            "precio": "Precio (CLP)",
            "stock": "Stock",
            "nota": "Nota",
        }


class ProductSpecForm(forms.ModelForm):
    class Meta:
        model = EspecificacionProducto
        fields = ["nombre_especificacion", "valor_especificacion"]
        widgets = {
            "nombre_especificacion": forms.TextInput(
                attrs={"class": "form-control spec-name", "placeholder": "Ej. Memoria"}
            ),
            "valor_especificacion": forms.TextInput(
                attrs={"class": "form-control spec-value", "placeholder": "Ej. 16 GB DDR4"}
            ),
        }
        labels = {
            "nombre_especificacion": "Campo",
            "valor_especificacion": "Valor",
        }


ProductReferenceFormSet = inlineformset_factory(
    Producto,
    ProductReference,
    form=ProductReferenceForm,
    extra=2,
    can_delete=True,
)


ProductSpecFormSet = inlineformset_factory(
    Producto,
    EspecificacionProducto,
    form=ProductSpecForm,
    extra=3,
    can_delete=True,
)
