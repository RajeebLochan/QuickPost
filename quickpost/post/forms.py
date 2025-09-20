from django import forms
from .models import Post
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Post, UserProfile

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['content', 'photo']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'What\'s on your mind?',
                'rows': 3
            }),
            'photo': forms.ClearableFileInput(attrs={
                'class': 'form-control'
            })
        }

class UserRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'password1': forms.PasswordInput(attrs={'class': 'form-control'}),
            'password2': forms.PasswordInput(attrs={'class': 'form-control'}),
        }

class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
        }

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['bio', 'profile_image', 'location', 'website', 'birth_date']
        widgets = {
            'bio': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4, 
                'placeholder': 'Tell us about yourself...'
            }),
            'profile_image': forms.FileInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'City, Country'
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-control', 
                'placeholder': 'https://yourwebsite.com'
            }),
            'birth_date': forms.DateInput(attrs={
                'class': 'form-control', 
                'type': 'date'
            }),
        }