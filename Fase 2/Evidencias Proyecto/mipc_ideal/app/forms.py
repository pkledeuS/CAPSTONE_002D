from django import forms
from django.contrib.auth.models import User
from .models import Profile

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