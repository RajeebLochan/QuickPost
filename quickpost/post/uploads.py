"""Image upload validation and normalisation.

Every image is opened with Pillow, checked against an allow-list of formats
and a size limit, re-oriented, stripped of metadata (EXIF can contain GPS
coordinates) and downscaled. GIFs are kept as-is so animation survives.
"""

import io
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}
MAX_PIXELS = 40_000_000

AVATAR_SIZE = 400
COVER_SIZE = 1600
POST_IMAGE_SIZE = 2048


def max_image_bytes():
    return settings.QUICKPOST["MAX_IMAGE_BYTES"]


def validate_image_file(upload):
    """Raise ValidationError unless `upload` is a safe, supported image."""
    if upload.size > max_image_bytes():
        limit_mb = max_image_bytes() // (1024 * 1024)
        raise ValidationError(f"Images must be {limit_mb} MB or smaller.", code="too_large")
    try:
        upload.seek(0)
        with Image.open(upload) as img:
            fmt = img.format
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValidationError("That file is not a supported image.", code="invalid") from exc
    finally:
        upload.seek(0)
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("Use a JPEG, PNG, WebP or GIF image.", code="format")
    if width * height > MAX_PIXELS:
        raise ValidationError("That image is too large to process.", code="dimensions")
    return fmt


def process_image(upload, max_side):
    """Return a ContentFile with a clean, downscaled copy of `upload`."""
    fmt = validate_image_file(upload)
    base = os.path.splitext(os.path.basename(upload.name or "image"))[0][:40] or "image"
    if fmt == "GIF":
        upload.seek(0)
        with Image.open(upload) as img:
            size = img.size
        upload.seek(0)
        content = ContentFile(upload.read(), name=f"{base}.gif")
        content.image_size = size
        return content

    upload.seek(0)
    with Image.open(upload) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        if fmt == "PNG":
            img.save(out, format="PNG", optimize=True)
            ext = "png"
        elif fmt == "WEBP":
            img.save(out, format="WEBP", quality=85)
            ext = "webp"
        else:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(out, format="JPEG", quality=85, optimize=True, progressive=True)
            ext = "jpg"
        size = img.size
    content = ContentFile(out.getvalue(), name=f"{base}.{ext}")
    content.image_size = size  # (width, height) of the stored file
    return content
