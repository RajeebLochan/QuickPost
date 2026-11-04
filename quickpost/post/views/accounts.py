from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core import signing
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from .. import selectors, services
from ..emails import read_verification_token, send_verification_email
from ..forms import (
    AccountForm,
    ConfirmPasswordForm,
    DeleteAccountForm,
    LoginForm,
    PrivacyForm,
    ProfileForm,
    RegistrationForm,
)
from ..models import Block
from ..ratelimit import rate_limit


def _data(request):
    """Bound form data for POST (even when every checkbox is unchecked), else None."""
    return request.POST if request.method == "POST" else None


def _files(request):
    return request.FILES if request.method == "POST" else None


@rate_limit("register", limit=5, period=3600, by="ip")
def register(request):
    if request.user.is_authenticated:
        return redirect("feed")
    form = RegistrationForm(_data(request))
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        send_verification_email(request, user)
        messages.success(request, f"We sent a confirmation link to {user.email}")
        return redirect("onboarding")
    return render(request, "accounts/register.html", {"form": form})


@method_decorator(rate_limit("login", limit=10, period=300, by="ip"), name="dispatch")
class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if services.reactivate_account(form.get_user()):
            messages.success(self.request, "Your account is active again")
        return response


@method_decorator(rate_limit("password_reset", limit=5, period=3600, by="ip"), name="dispatch")
class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/email/password_reset.txt"
    subject_template_name = "accounts/email/password_reset_subject.txt"


def verify_email(request, token):
    try:
        user_id, email = read_verification_token(token)
    except signing.SignatureExpired:
        return render(request, "accounts/verify_result.html", {"ok": False, "expired": True}, status=400)
    except signing.BadSignature:
        return render(request, "accounts/verify_result.html", {"ok": False}, status=400)
    user = User.objects.filter(pk=user_id, email=email).select_related("profile").first()
    if user is None:
        return render(request, "accounts/verify_result.html", {"ok": False}, status=400)
    if not user.profile.email_verified:
        user.profile.email_verified = True
        user.profile.save(update_fields=["email_verified", "updated_at"])
    return render(request, "accounts/verify_result.html", {"ok": True})


@require_POST
@login_required
@rate_limit("resend_verification", limit=3, period=600)
def resend_verification(request):
    if request.user.profile.email_verified:
        messages.info(request, "Your email is already confirmed")
    else:
        send_verification_email(request, request.user)
        messages.success(request, f"Sent a new link to {request.user.email}")
    return redirect("settings_account")


@login_required
def onboarding(request):
    profile = request.user.profile
    form = ProfileForm(_data(request), _files(request), instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        profile.onboarded = True
        profile.save(update_fields=["onboarded", "updated_at"])
        return redirect("feed")
    return render(
        request,
        "accounts/onboarding.html",
        {"form": form, "suggestions": selectors.suggested_users(request.user, limit=5)},
    )


@login_required
def settings_profile(request):
    form = ProfileForm(_data(request), _files(request), instance=request.user.profile)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved")
            return redirect("profile", username=request.user.username)
        messages.error(request, "Check the highlighted fields")
    return render(request, "settings/profile.html", {"form": form, "section": "profile", "nav": "settings"})


@login_required
def settings_account(request):
    user = request.user
    old_email = user.email
    form = AccountForm(_data(request), instance=user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if user.email != old_email:
            user.profile.email_verified = False
            user.profile.save(update_fields=["email_verified", "updated_at"])
            send_verification_email(request, user)
            messages.success(request, f"Saved. Confirm your new address from the email sent to {user.email}")
        else:
            messages.success(request, "Account saved")
        return redirect("settings_account")
    return render(
        request,
        "settings/account.html",
        {"form": form, "section": "account", "nav": "settings", "password_form": ConfirmPasswordForm(user)},
    )


@login_required
def settings_privacy(request):
    profile = request.user.profile
    form = PrivacyForm(_data(request), initial={"is_private": profile.is_private})
    if request.method == "POST" and form.is_valid():
        services.set_private(request.user, form.cleaned_data["is_private"])
        messages.success(request, "Privacy settings saved")
        return redirect("settings_privacy")
    blocks = Block.objects.filter(blocker=request.user).select_related("blocked__profile")
    return render(
        request,
        "settings/privacy.html",
        {"form": form, "blocks": blocks, "section": "privacy", "nav": "settings"},
    )


@login_required
def settings_password(request):
    form = PasswordChangeForm(request.user, _data(request))
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Password changed")
        return redirect("settings_account")
    return render(request, "settings/password.html", {"form": form, "section": "account", "nav": "settings"})


@require_POST
@login_required
def deactivate(request):
    form = ConfirmPasswordForm(request.user, request.POST)
    if not form.is_valid():
        messages.error(request, "That password is incorrect. Your account is still active.")
        return redirect("settings_account")
    services.deactivate_account(request.user)
    logout(request)
    messages.info(request, "Your account is deactivated. Log in again any time to restore it.")
    return redirect("home")


@login_required
def delete_account(request):
    form = DeleteAccountForm(request.user, _data(request))
    if request.method == "POST" and form.is_valid():
        user = request.user
        logout(request)
        services.delete_account(user)
        messages.info(request, "Your account and everything in it has been deleted")
        return redirect("home")
    return render(request, "settings/delete.html", {"form": form, "section": "account", "nav": "settings"})


password_reset_done = auth_views.PasswordResetDoneView.as_view(
    template_name="accounts/password_reset_done.html"
)
password_reset_confirm = auth_views.PasswordResetConfirmView.as_view(
    template_name="accounts/password_reset_confirm.html", success_url=reverse_lazy("password_reset_complete")
)
password_reset_complete = auth_views.PasswordResetCompleteView.as_view(
    template_name="accounts/password_reset_complete.html"
)
