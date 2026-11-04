import logging

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)

VERIFY_SALT = "quickpost.verify-email"
VERIFY_MAX_AGE = 60 * 60 * 24 * 3


def make_verification_token(user):
    return signing.dumps({"u": user.pk, "e": user.email}, salt=VERIFY_SALT)


def read_verification_token(token):
    """Return (user_id, email) or raise signing.BadSignature / SignatureExpired."""
    data = signing.loads(token, salt=VERIFY_SALT, max_age=VERIFY_MAX_AGE)
    return data["u"], data["e"]


def send_verification_email(request, user):
    link = request.build_absolute_uri(reverse("verify_email", args=[make_verification_token(user)]))
    body = (
        f"Hi {user.username},\n\n"
        f"Confirm your email address for QuickPost by opening this link:\n{link}\n\n"
        "The link works for three days. If you didn't create this account, ignore this email.\n"
    )
    send_mail("Confirm your QuickPost email", body, settings.DEFAULT_FROM_EMAIL, [user.email])
    logger.info("event=verification_email_sent user=%s", user.pk)
