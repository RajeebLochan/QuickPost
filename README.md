# QuickPost

QuickPost is a small social network built with Django: 240-character posts with up to four photos, comments and replies, likes, reposts and quote posts, bookmarks, hashtags and mentions, private accounts, blocking and reporting, real-time direct messages, and live notifications. The feed also shows a daily line inspired by the Ramayana and Mahabharata.

It's server-rendered Django with a small amount of plain JavaScript. There's no front-end framework and no build step.

---

## Contents

- [Features](#features)
- [Quick start (local)](#quick-start-local)
- [Upgrading an existing checkout](#upgrading-an-existing-checkout-read-this-first)
- [Configuration](#configuration)
- [Real-time messaging: Daphne, Channels and Redis](#real-time-messaging-daphne-channels-and-redis)
- [Daily quote](#daily-quote)
- [PostgreSQL](#postgresql)
- [Docker Compose](#docker-compose)
- [Tests and checks](#tests-and-checks)
- [Deployment](#deployment)
- [Security checklist](#security-checklist)
- [Troubleshooting](#troubleshooting)
- [Project layout](#project-layout)
- [Credits](#credits)

## Features

| Area | What works |
| --- | --- |
| Accounts | Registration with email confirmation, login and logout, password reset by email, onboarding, username and email changes (a new email needs confirming again), password change, deactivation (hidden until you log in again) and permanent deletion |
| Profiles | Photo, cover, display name, bio, location and website. Follower, following and post counts, a media tab, and public or private accounts with follow requests |
| Posts | Text and up to 4 images (validated, resized, EXIF stripped), edit, delete, likes and dislikes (mutually exclusive), reposts, quote posts, bookmarks, copy link and share, `#hashtags`, `@mentions`, individual post pages |
| Feeds | A following feed, plus an Explore feed ranked by likes, comments and reposts in the last 14 days. Both are paginated with "Load more" |
| Comments | Threaded replies (one level), deletion by the author or the post owner, validation (500 characters), rate limiting, pagination |
| Messaging | One-to-one conversations over WebSockets: live delivery, typing indicator, read receipts ("Seen"), unread counts, conversation search, older-message loading, reconnection with an HTTP fallback that delivers through the same path |
| Notifications | New followers, follow requests, likes, comments, replies, mentions, reposts and messages. Stored in the database and pushed live, with a dropdown, a full page, unread badges, mark as read, mark all as read and deep links |
| Search | People (username or name), posts, hashtags, trending hashtags and suggested people (friends of friends) |
| Safety | Block and unblock, report posts, comments and users, an admin review queue with actions, private-account enforcement everywhere, rate limits on sensitive endpoints, upload validation |

## Quick start (local)

Requires Python 3.12+. Redis is optional for local development.

```bash
git clone https://github.com/RajeebLochan/QuickPost.git
```

```bash
cd QuickPost
```

```bash
python -m venv venv
```

```bash
source venv/bin/activate        # Windows: venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env            # then set DJANGO_DEBUG=True for local work
```

```bash
cd quickpost
```

```bash
python manage.py migrate
```

```bash
python manage.py createsuperuser
```

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000. `runserver` runs Daphne (ASGI), so WebSockets work with this one command. Without `REDIS_URL` it uses an in-process channel layer, which is fine for a single development server.

Confirmation and password-reset emails are printed in the `runserver` terminal during development. Open the link from there to confirm an account. Accounts that existed before this version are treated as already confirmed.

## Upgrading an existing checkout (read this first)

Earlier versions committed `quickpost/db.sqlite3`, `quickpost/media/` and `.env` to git. They're no longer tracked, and **pulling this change makes git delete those files from your working copy**. Back them up before pulling:

```bash
cp quickpost/db.sqlite3 ~/quickpost-db-backup.sqlite3
```

```bash
cp -r quickpost/media ~/quickpost-media-backup
```

If you already pulled, restore them from the last commit that still had them (they stay untracked afterwards):

```bash
git show main:quickpost/db.sqlite3 > quickpost/db.sqlite3
```

```bash
git archive main quickpost/media | tar -x
```

Then run `python manage.py migrate`. The migrations keep your data:

- Existing post photos become the post's first image.
- The shared default avatar file is replaced by generated initials.
- Existing accounts are marked as confirmed and onboarded.

## Configuration

All configuration comes from environment variables, read from `.env` in development. See [`.env.example`](.env.example).

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_DEBUG` | `False` | Set `True` locally only |
| `DJANGO_SECRET_KEY` | (none) | Required when debug is off. Generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` in debug | Comma separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | (empty) | For example `https://quickpost.example.com` |
| `DATABASE_URL` | SQLite file | For example `postgres://user:pass@host:5432/quickpost` |
| `REDIS_URL` | (empty) | Required in production (channel layer and shared cache) |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | console backend in debug | SMTP settings for confirmation and reset emails |
| `REQUIRE_EMAIL_VERIFICATION` | `True` | Posting, commenting and messaging need a confirmed email |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | (empty), `gemini-2.5-flash` | Optional, for the daily quote |
| `MEDIA_ROOT`, `SERVE_MEDIA` | `quickpost/media`, on in debug | Where uploads live, and whether Django serves them |
| `BEHIND_PROXY` | `False` | Trust `X-Forwarded-Proto` from your TLS proxy |
| `RATE_LIMITS_ENABLED` | `True` | Turn off only for load testing |

## Real-time messaging: Daphne, Channels and Redis

- Each logged-in browser tab opens **one** WebSocket at `/ws/live/`, authenticated with the session cookie.
- Messages, typing indicators, read receipts and notifications are all pushed to per-user groups (`user.<id>`).
- Every send, over the socket or the HTTP fallback, goes through `services.send_message`. That function validates, saves, and pushes to all participants after the transaction commits, so both paths deliver the same way.
- Without `REDIS_URL`, the in-memory layer works only inside one process, which is fine for `runserver`. With more than one process or server, set `REDIS_URL`:

```bash
redis-server
```

```bash
REDIS_URL=redis://localhost:6379/0 python manage.py runserver
```

## Daily quote

Pages never call Gemini. The quote flow:

- `python manage.py refresh_quote` asks Gemini for a new line and stores it in the database. Run it on a schedule.
- Pages read the newest stored quote through a 15-minute cache.
- With no stored quote, or one older than 48 hours, pages show one of ten built-in lines, rotating daily.
- Without `GEMINI_API_KEY` the command exits with an error and the built-in lines are used. Nothing breaks.

Example cron entry (every 12 hours):

```
0 */12 * * * cd /srv/quickpost/quickpost && /srv/quickpost/venv/bin/python manage.py refresh_quote --if-older-than 11
```

The Docker Compose stack runs this for you in the `quote` service. APScheduler was removed: it started twice under the autoreloader and never ran under production servers.

## PostgreSQL

SQLite is the default. For PostgreSQL, point `DATABASE_URL` at it:

```bash
createdb quickpost
```

```bash
DATABASE_URL=postgres://quickpost:password@localhost:5432/quickpost python manage.py migrate
```

The full test suite and the upgrade path from the old schema were run on PostgreSQL 16.

## Docker Compose

```bash
cp .env.example .env    # set DJANGO_SECRET_KEY to a long random value
```

```bash
docker compose up --build
```

This starts Daphne on http://localhost:8000 with PostgreSQL, Redis and the quote job. Create an admin with:

```bash
docker compose exec web python manage.py createsuperuser
```

## Tests and checks

From `quickpost/`:

```bash
python manage.py test post
```

```bash
DJANGO_DEBUG=True python manage.py check
```

```bash
DJANGO_DEBUG=True python manage.py makemigrations --check --dry-run
```

From the repository root, with `pip install -r requirements-dev.txt`:

```bash
ruff check quickpost && ruff format --check quickpost
```

The suite has 102 tests. It covers:

- Accounts and email confirmation.
- Missing avatar and photo files.
- Permissions on posts, comments, follows, private accounts, blocks and reports.
- Upload validation and pagination.
- A constant feed query count.
- Notifications.
- The WebSocket consumer: delivery, typing, read receipts and authorization.
- The daily quote's caching and fallback.

To run it against PostgreSQL and Redis, set `DATABASE_URL` and `REDIS_URL` first.

## Deployment

1. Set `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `REDIS_URL` and the SMTP settings.
2. `pip install -r requirements.txt`, then `python manage.py migrate` and `python manage.py collectstatic`.
3. Run `daphne -b 0.0.0.0 -p 8000 quickpost.asgi:application` (or several workers behind a load balancer) under systemd or a container.
4. Put a TLS proxy (nginx, Caddy, a load balancer) in front. Forward WebSocket upgrades for `/ws/` and set `BEHIND_PROXY=True`.
5. Serve `/media/` from the proxy or object storage. Django serves it only when `SERVE_MEDIA=True`. WhiteNoise serves `/static/`.
6. Schedule `refresh_quote` (see above).
7. Review reports at `/admin/` (Report: dismiss, remove content, or deactivate the account).

This repository hasn't been deployed anywhere as part of this work.

## Security checklist

- [ ] **Revoke the Gemini API keys that were committed in `.env` in commits `e580180`, `94401e9` and `e54b715`**, and create new ones. They're still in git history, so treat them as public. The history has not been rewritten. If you want that, do it deliberately (for example with `git filter-repo`) and force-push.
- [ ] The old `SECRET_KEY` in `settings.py` is public. Production must use a new `DJANGO_SECRET_KEY`.
- [ ] The previously committed `db.sqlite3` contained an admin account's password hash and session keys. Change that password, and delete old sessions if that database is used anywhere: `python manage.py shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"`.
- [ ] `DJANGO_DEBUG=False` and HTTPS in production. HSTS is on (30 days). Enable `SECURE_HSTS_INCLUDE_SUBDOMAINS` only if every subdomain uses HTTPS.
- [ ] Keep `.env`, databases and `media/` out of git (`.gitignore` covers them).

Already handled in code:

- Secrets come only from the environment.
- CSRF protection on every write.
- Secure cookies in production.
- Uploads are re-encoded with metadata stripped.
- Private and blocked content is hidden behind 404s.
- Authorization lives in the service layer, so the WebSocket follows the same rules as HTTP.
- Rate limits on login, registration, password reset, posting, commenting, messaging, following and reporting.

## Troubleshooting

- **Chat shows "Reconnecting…".** Check that you started the server with `python manage.py runserver` from this version (Daphne). With several processes, `REDIS_URL` must be set and Redis must be running.
- **`DJANGO_SECRET_KEY must be set`.** Set it, or set `DJANGO_DEBUG=True` for local work.
- **`REDIS_URL must be set in production`.** Production needs Redis. For a single-process demo you can set `ALLOW_IN_MEMORY_CHANNEL_LAYER=True`.
- **"Confirm your email first" when posting.** Open the link printed in the server console, or set `REQUIRE_EMAIL_VERIFICATION=False` locally.
- **"You're doing that too often".** A rate limit was hit. Limits reset within a minute (login: five minutes; registration and reports: an hour).
- **The daily quote never changes.** Run `python manage.py refresh_quote` and read its error. Without a key, the built-in lines rotate daily.

## Project layout

```
quickpost/
  quickpost/          settings, urls, asgi
  post/
    models.py         data model
    services.py       all writes: validation, permissions, notifications, pushes
    selectors.py      all reads: visibility rules, annotated feeds, pagination
    consumers.py      the /ws/live/ WebSocket consumer
    quotes.py         daily quote storage and fallback
    uploads.py        image validation and processing
    ratelimit.py      cache-backed rate limiting
    views/            one module per area (pages, posts, profiles, accounts, ...)
    templatetags/     icon sprite, rich text (links, #tags, @mentions), relative time
    tests/            the test suite
  templates/          all pages and partials
  static/             css/app.css (design system), js/app.js, js/chat.js
```

## Credits

- Icons: [Lucide](https://lucide.dev), ISC License (see `quickpost/static/LUCIDE-LICENSE.txt`).
- Type: Instrument Sans and Newsreader from Google Fonts.
- The interface redesign followed the "unslop" method by Damir Sokolovsky ([@heydamir](https://x.com/heydamir)), CC BY 4.0.
