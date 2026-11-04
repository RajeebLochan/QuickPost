import re
from datetime import timedelta

from django import template
from django.urls import reverse
from django.utils import timezone
from django.utils.html import conditional_escape, escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()

TOKEN_RE = re.compile(
    r"(?P<url>https?://[^\s<]+[^\s<.,:;\"')\]!?])"
    r"|(?<![\w&/])#(?P<tag>\w{1,50})"
    r"|(?<![\w@/])@(?P<mention>[\w.+-]{1,150}(?<![.+-]))"
)


@register.simple_tag
def icon(name, label=""):
    """Inline Lucide icon from the sprite in partials/icons.svg."""
    if label:
        return format_html(
            '<svg class="icon" role="img" aria-label="{}"><use href="#i-{}"></use></svg>', label, name
        )
    return format_html('<svg class="icon" aria-hidden="true"><use href="#i-{}"></use></svg>', name)


@register.filter(needs_autoescape=True)
def rich_text(value, autoescape=True):
    """Escape text, then link URLs, #hashtags and @mentions. Line breaks become <br>."""
    text = str(value or "")
    out, last = [], 0
    for match in TOKEN_RE.finditer(text):
        out.append(escape(text[last : match.start()]))
        if match.group("url"):
            url = match.group("url")
            shown = re.sub(r"^https?://(www\.)?", "", url)
            if len(shown) > 40:
                shown = shown[:39] + "…"
            out.append(
                format_html('<a href="{}" rel="nofollow ugc noopener" target="_blank">{}</a>', url, shown)
            )
        elif match.group("tag"):
            tag = match.group("tag")
            out.append(format_html('<a href="{}">#{}</a>', reverse("hashtag", args=[tag.lower()]), tag))
        else:
            name = match.group("mention")
            out.append(format_html('<a href="{}">@{}</a>', reverse("profile", args=[name]), name))
        last = match.end()
    out.append(escape(text[last:]))
    return mark_safe("".join(str(part) for part in out).replace("\n", "<br>"))


@register.filter
def ago(value):
    """Short relative time: now, 5m, 3h, 2d, then a date."""
    if not value:
        return ""
    now = timezone.now()
    delta = now - value
    if delta < timedelta(minutes=1):
        return "now"
    if delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() // 60)}m"
    if delta < timedelta(days=1):
        return f"{int(delta.total_seconds() // 3600)}h"
    if delta < timedelta(days=7):
        return f"{delta.days}d"
    local = timezone.localtime(value)
    if local.year == timezone.localtime(now).year:
        return f"{local.day} {local:%b}"
    return f"{local.day} {local:%b} {local.year}"


@register.filter
def compact(value):
    """1234 -> 1.2K, 1500000 -> 1.5M."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return value
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "K"
    return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"


@register.inclusion_tag("partials/avatar.html")
def avatar(user, size="md"):
    profile = getattr(user, "profile", None)
    return {
        "url": profile.avatar_url if profile else "",
        "initial": profile.initial if profile else (user.username[:1].upper() if user else "?"),
        "name": profile.name if profile else getattr(user, "username", ""),
        "size": size,
        "hue": (user.pk * 47) % 360 if user and user.pk else 0,
    }


@register.simple_tag(takes_context=True)
def active(context, name):
    return "is-active" if context.get("nav") == name else ""


@register.filter
def attr_escape(value):
    return conditional_escape(value)
