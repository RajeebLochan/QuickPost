# Production-style image for QuickPost (Daphne serving HTTP + WebSockets).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY quickpost/ /app/
RUN useradd --create-home quickpost && mkdir -p /app/media /app/staticfiles && chown -R quickpost /app
USER quickpost

# collectstatic needs settings to import; these values are only used at build time.
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=False ALLOW_IN_MEMORY_CHANNEL_LAYER=True \
    python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "quickpost.asgi:application"]
