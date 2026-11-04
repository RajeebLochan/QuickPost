from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .models import POST_MAX_LENGTH, Report, UserProfile
from .uploads import AVATAR_SIZE, COVER_SIZE, process_image, validate_image_file

USERNAME_HELP = "3 to 30 characters: letters, numbers, dots and underscores"
username_validator = RegexValidator(
    r"^[A-Za-z0-9_.]{3,30}$", "Use 3 to 30 letters, numbers, dots or underscores."
)
RESERVED_USERNAMES = {
    "admin",
    "administrator",
    "root",
    "support",
    "help",
    "settings",
    "explore",
    "search",
    "messages",
    "notifications",
    "saved",
    "accounts",
    "quickpost",
    "api",
    "static",
    "media",
}


def clean_username_value(username, instance=None):
    username = (username or "").strip()
    username_validator(username)
    if username.lower() in RESERVED_USERNAMES:
        raise ValidationError("That username is reserved.")
    qs = User.objects.filter(username__iexact=username)
    if instance is not None:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise ValidationError("That username is taken.")
    return username


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleImageInput

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        files = [f for f in files if f]
        limit = settings.QUICKPOST["MAX_IMAGES_PER_POST"]
        if len(files) > limit:
            raise ValidationError(f"Add at most {limit} images.")
        for upload in files:
            validate_image_file(upload)
        return files


class PostForm(forms.Form):
    content = forms.CharField(
        max_length=POST_MAX_LENGTH,
        required=False,
        strip=True,
        widget=forms.Textarea(
            attrs={"rows": 4, "maxlength": POST_MAX_LENGTH, "placeholder": "What's happening"}
        ),
    )
    images = MultipleImageField(
        widget=MultipleImageInput(attrs={"accept": "image/jpeg,image/png,image/webp,image/gif"})
    )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("content") and not cleaned.get("images"):
            raise ValidationError("Write something or add a photo.")
        return cleaned


class EditPostForm(forms.Form):
    content = forms.CharField(
        max_length=POST_MAX_LENGTH,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": POST_MAX_LENGTH}),
    )


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email")
        help_texts = {"username": USERNAME_HELP}

    def clean_username(self):
        return clean_username_value(self.cleaned_data.get("username"))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "That username and password don't match.",
        "inactive": "This account has been suspended.",
    }


class ImageProcessingMixin:
    """Validates and normalises image fields before they are saved."""

    def _clean_image(self, name, size):
        upload = self.cleaned_data.get(name)
        if upload and hasattr(upload, "content_type"):  # a new upload, not the existing file
            validate_image_file(upload)
            return process_image(upload, size)
        return upload


class ProfileForm(ImageProcessingMixin, forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["display_name", "bio", "profile_image", "cover_image", "location", "website"]
        widgets = {
            "profile_image": forms.FileInput(attrs={"accept": "image/*"}),
            "cover_image": forms.FileInput(attrs={"accept": "image/*"}),
        }
        labels = {"display_name": "Name", "profile_image": "Photo", "cover_image": "Cover"}

    bio = forms.CharField(
        max_length=160, required=False, widget=forms.Textarea(attrs={"rows": 3, "maxlength": 160})
    )

    def clean_profile_image(self):
        return self._clean_image("profile_image", AVATAR_SIZE)

    def clean_cover_image(self):
        return self._clean_image("cover_image", COVER_SIZE)


class AccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email"]
        help_texts = {"username": USERNAME_HELP}

    email = forms.EmailField(required=True)

    def clean_username(self):
        return clean_username_value(self.cleaned_data.get("username"), instance=self.instance)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Another account uses this email.")
        return email


class PrivacyForm(forms.Form):
    is_private = forms.BooleanField(required=False, label="Private account")


class ConfirmPasswordForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise ValidationError("That password is incorrect.")
        return password


class DeleteAccountForm(ConfirmPasswordForm):
    confirm_username = forms.CharField(label="Type your username to confirm")

    def clean_confirm_username(self):
        value = self.cleaned_data["confirm_username"].strip()
        if value != self.user.username:
            raise ValidationError("That doesn't match your username.")
        return value


class ReportForm(forms.Form):
    reason = forms.ChoiceField(choices=Report.Reason.choices)
    details = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    target_type = forms.ChoiceField(choices=[("post", "post"), ("comment", "comment"), ("user", "user")])
    target_id = forms.IntegerField(min_value=1)
