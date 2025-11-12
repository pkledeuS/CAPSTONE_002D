from django import forms
from django.contrib.auth.models import User
from .models import Profile, ProductReview


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
