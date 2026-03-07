# Bookworm: Deployment Roadmap & Checklist

> Railway deployment plan for Bookworm: Little Library Finder
> Last updated: March 2026

---

## Overview

This document covers everything needed to take Bookworm from local development to live on Railway. The deployment is organized into four sequential phases. Each phase must be completed and verified before moving to the next.

---

## Phase 1 — Pre-Flight (Local Preparation)

Everything in this phase happens on your local machine before touching Railway.

### 1.1 — Git Repository Setup

The project is not currently under version control. This is the first and most critical step.

- [ ] **Create `.gitignore`** at project root (alongside `manage.py`)
  - Must exclude: `.env`, `__pycache__/`, `*.pyc`, `.DS_Store`, `staticfiles/`, `media/`, `.pytest_cache/`, `db.sqlite3`, `*.egg-info/`
  - Must NOT exclude: `Procfile`, `requirements.txt`, `runtime.txt`, `nixpacks.toml`
- [ ] **Initialize git repo**
  ```bash
  cd /path/to/Bookworm/bookworm
  git init
  git add .
  git commit -m "Initial commit: Bookworm MVP"
  ```
- [ ] **Create GitHub repository** (public or private)
  ```bash
  git remote add origin git@github.com:YOUR_USERNAME/bookworm.git
  git push -u origin main
  ```
- [ ] **Verify `.env` is NOT in the commit** — run `git status` and confirm `.env` does not appear in tracked files

### 1.2 — Settings.py: Railway DATABASE_URL Support

Railway provides a single `DATABASE_URL` environment variable rather than separate `DB_NAME`, `DB_USER`, etc. The settings need to parse this.

- [ ] **Add `dj-database-url` parsing** to the database config block in `settings.py`
  - Use `DATABASE_URL` if present (Railway), fall back to individual `DB_*` vars (local dev)
  - The engine must be overridden to `django.contrib.gis.db.backends.postgis` since `dj-database-url` defaults to regular `psycopg2`
- [ ] **Code change required:**
  ```python
  # Replace the existing DATABASES block with:
  import dj_database_url

  DATABASE_URL = os.environ.get('DATABASE_URL')
  if DATABASE_URL:
      DATABASES = {
          'default': dj_database_url.config(
              default=DATABASE_URL,
              conn_max_age=60,
              conn_health_checks=True,
              engine='django.contrib.gis.db.backends.postgis',
          )
      }
  else:
      DATABASES = {
          'default': {
              'ENGINE': 'django.contrib.gis.db.backends.postgis',
              'NAME': os.environ.get('DB_NAME', 'bookworm'),
              'USER': os.environ.get('DB_USER', os.environ.get('USER', 'postgres')),
              'PASSWORD': os.environ.get('DB_PASSWORD', ''),
              'HOST': os.environ.get('DB_HOST', 'localhost'),
              'PORT': os.environ.get('DB_PORT', '5432'),
              'CONN_MAX_AGE': 60,
              'CONN_HEALTH_CHECKS': True,
          }
      }
  ```
- [ ] **Test locally** — confirm the app still runs with your existing `.env` (the `else` branch)

### 1.3 — Production Settings Hardening

Review and tighten settings for production.

- [ ] **`ALLOWED_HOSTS` default cleanup** — remove the ngrok and LAN IP defaults; production should only allow explicitly set hosts
  ```python
  ALLOWED_HOSTS = [
      h.strip()
      for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
      if h.strip()
  ]
  ```
- [ ] **`GEOJSON_CACHE_DURATION`** — bump default from 60 to 120 for production
- [ ] **`STATICFILES_STORAGE` deprecation** — Django 5.x renamed this to `STORAGES`. Current setting works but emits a deprecation warning. Update to:
  ```python
  STORAGES = {
      "staticfiles": {
          "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
      },
  }
  ```
  (Keep the old `STATICFILES_STORAGE` as a fallback comment for reference)
- [ ] **Verify `DEBUG` defaults to `False`** — already correct, just confirm
- [ ] **Verify `SECRET_KEY` raises in production** — already correct

### 1.4 — Deployment Files Audit

These files were created earlier. Verify they're correct and present alongside `manage.py`.

- [ ] **`requirements.txt`** — present and complete
- [ ] **`Procfile`** — present with `release` and `web` commands
- [ ] **`runtime.txt`** — present, specifies `python-3.12`
- [ ] **`nixpacks.toml`** — present, installs `gdal`, `geos`, `proj` system packages
- [ ] **Run `pip install -r requirements.txt`** locally to verify no dependency conflicts

### 1.5 — Run Tests

- [ ] **Run the test suite** before deploying
  ```bash
  pytest
  ```
- [ ] All 40 tests should pass
- [ ] Fix any failures before proceeding

### 1.6 — Collect Static Files (Dry Run)

- [ ] **Run collectstatic locally** to catch any issues
  ```bash
  python manage.py collectstatic --noinput --dry-run
  ```
- [ ] Verify no errors — especially that `bookworm-nav-logo.png` and all other new assets are picked up

---

## Phase 2 — Railway Setup

### 2.1 — Create Railway Project

- [ ] Log into [Railway](https://railway.app)
- [ ] Create new project → "Deploy from GitHub repo"
- [ ] Connect your GitHub account and select the `bookworm` repository
- [ ] Railway will detect the `Procfile` and `nixpacks.toml` automatically

### 2.2 — Provision PostgreSQL with PostGIS

- [ ] Add a PostgreSQL plugin to your Railway project
- [ ] **Enable PostGIS extension** — Railway's Postgres doesn't have PostGIS by default. You'll need to run this in the Railway database shell (or via `railway run`):
  ```sql
  CREATE EXTENSION IF NOT EXISTS postgis;
  ```
- [ ] Confirm `DATABASE_URL` is auto-injected into the service environment

### 2.3 — Configure Environment Variables

Set these in Railway's service variables panel:

| Variable | Value | Notes |
|----------|-------|-------|
| `SECRET_KEY` | *(generate a new 50+ char random string)* | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | `false` | Never `true` in production |
| `ALLOWED_HOSTS` | `your-app.up.railway.app` | Add custom domain later if needed |
| `CSRF_TRUSTED_ORIGINS` | `https://your-app.up.railway.app` | Must include `https://` prefix |
| `ENABLE_HTTPS` | `true` | Activates SSL redirect + secure cookies |
| `CLOUDINARY_URL` | *(from your Cloudinary dashboard)* | Same URL as in your local `.env` |
| `DJANGO_SETTINGS_MODULE` | `bookworm.settings` | May be needed if Railway can't detect it |
| `GEOJSON_CACHE_DURATION` | `120` | 2 minutes for production |

**Email (optional at launch — console backend is the default):**

| Variable | Value |
|----------|-------|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | SMTP host (e.g., `smtp.gmail.com`) |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` | Your email |
| `EMAIL_HOST_PASSWORD` | App-specific password |
| `ADMIN_EMAIL` | Where notifications go |

### 2.4 — Deploy

- [ ] Push to GitHub — Railway auto-deploys on push to `main`
- [ ] **Watch the build logs** for:
  - Nixpacks installing `gdal`, `geos`, `proj` ✓
  - `pip install -r requirements.txt` succeeding ✓
  - `release` command running (`migrate`, `createcachetable`, `collectstatic`) ✓
  - `web` process starting (gunicorn) ✓
- [ ] If the build fails, check the error against common issues in the Troubleshooting section below

---

## Phase 3 — Post-Deploy Verification

### 3.1 — Smoke Tests (Manual)

Run through these immediately after first successful deploy:

- [ ] **`/health/`** — returns `{"status": "ok"}`
- [ ] **`/`** (landing page) — loads with hero image, stats, branding
- [ ] **`/map/`** — map renders with tiles, no console errors
- [ ] **`/admin/`** — Django admin login page loads
- [ ] **`/sitemap.xml`** — returns valid XML
- [ ] **`/robots.txt`** — returns text with correct sitemap URL (https, not http)

### 3.2 — Create Admin Superuser

- [ ] Via Railway console or `railway run`:
  ```bash
  python manage.py createsuperuser
  ```
- [ ] Log into `/admin/` and verify access

### 3.3 — Seed Initial Data

- [ ] **Add at least one verified library** via Django admin to confirm:
  - PostGIS spatial queries work (the map shows the marker)
  - GeoJSON API returns data
  - Library detail page renders at `/library/<pk>-<slug>/`
- [ ] **Upload a test shelfie** to confirm Cloudinary integration works in production

### 3.4 — Security Headers Check

- [ ] Visit the site and inspect response headers (browser DevTools → Network tab):
  - `Content-Security-Policy` — present ✓
  - `X-Frame-Options: DENY` — present ✓
  - `X-Content-Type-Options: nosniff` — present ✓
  - `Referrer-Policy` — present ✓
  - `Strict-Transport-Security` — NOT present yet (enable after HTTPS is confirmed working)
- [ ] **Test HTTPS redirect** — visit `http://your-app.up.railway.app` and confirm it redirects to `https://`

### 3.5 — Functional Tests

- [ ] **Submit a library** via the map page form — confirm:
  - Location picker works
  - Address search (Nominatim) works
  - Photo upload to Cloudinary succeeds
  - Success message displays
  - Admin email notification arrives (if SMTP configured)
- [ ] **Upload a shelfie** to the test library — confirm:
  - Photo uploads successfully
  - Library freshness updates to "Fresh"
  - Shelfie appears in carousel
- [ ] **Report an issue** — confirm form submits and success displays
- [ ] **Report a photo** — confirm form submits
- [ ] **Rate limiting** — submit 5+ libraries rapidly, confirm rate limit message with countdown appears
- [ ] **Lightbox** — tap a shelfie, confirm lightbox opens with swipe/keyboard navigation

### 3.6 — Mobile Testing

- [ ] Test on **iOS Safari** (or Safari via macOS simulator)
- [ ] Test on **Android Chrome**
- [ ] Verify:
  - Map loads and is responsive to touch
  - Offcanvas panels open/close smoothly
  - Camera capture works on shelfie/submit forms
  - Navbar logo is properly sized
  - Geolocation works (requires HTTPS — should work on Railway)

---

## Phase 4 — Production Hardening

### 4.1 — Enable HSTS

After confirming HTTPS works correctly for at least 24 hours:

- [ ] Uncomment HSTS settings in `settings.py`:
  ```python
  SECURE_HSTS_SECONDS = 31536000  # 1 year
  SECURE_HSTS_INCLUDE_SUBDOMAINS = True
  SECURE_HSTS_PRELOAD = True
  ```
- [ ] Deploy and verify the `Strict-Transport-Security` header appears

### 4.2 — Uptime Monitoring

- [ ] Set up [UptimeRobot](https://uptimerobot.com) (free tier):
  - Monitor URL: `https://your-app.up.railway.app/health/`
  - Check interval: 5 minutes
  - Alert contacts: your email
- [ ] Verify you receive an alert if the site goes down

### 4.3 — Custom Domain (Optional)

- [ ] Add custom domain in Railway settings
- [ ] Configure DNS (CNAME record pointing to Railway)
- [ ] Update `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to include the new domain
- [ ] SSL is automatic on Railway for custom domains

### 4.4 — Database Backups

- [ ] **Railway provides automatic backups** on paid plans — verify this is enabled
- [ ] For additional safety, set up the `scripts/backup.sh` as a scheduled task:
  ```bash
  # Manual backup via Railway CLI
  railway run python manage.py dumpdata --natural-primary --natural-foreign --indent 2 > backup.json
  ```
- [ ] Test restoring a backup to confirm the process works

### 4.5 — CSP Review for Production CDN Domains

- [ ] Open browser console on the live site — check for CSP violation warnings
- [ ] If Cloudinary images are blocked, verify `*.cloudinary.com` is in the `img-src` directive
- [ ] If any CDN resources are blocked, add their domains to the appropriate CSP directive in `middleware.py`

---

## Troubleshooting

### Build fails: "Could not find GDAL library"
The `nixpacks.toml` isn't being detected. Ensure it's in the same directory as `manage.py` and committed to git.

### Build fails: "No module named 'django.contrib.gis'"
PostGIS system libraries aren't installed. Check `nixpacks.toml` has `gdal`, `geos`, and `proj`.

### Release command fails: "relation does not exist"
PostGIS extension isn't enabled. Run `CREATE EXTENSION IF NOT EXISTS postgis;` in the Railway database shell.

### App crashes: "DisallowedHost"
`ALLOWED_HOSTS` doesn't include the Railway domain. Check for trailing whitespace or missing commas.

### Static files 404
`collectstatic` didn't run or WhiteNoise isn't configured. Check the `release` command in `Procfile` and verify `whitenoise` is in `MIDDLEWARE`.

### Cloudinary uploads fail
`CLOUDINARY_URL` environment variable isn't set or is malformed. It should look like: `cloudinary://API_KEY:API_SECRET@CLOUD_NAME`

### Map tiles don't load
CSP is blocking tile requests. Check the `img-src` directive includes `https://*.basemaps.cartocdn.com`.

### Geolocation doesn't work
Requires HTTPS (secure context). Confirm `ENABLE_HTTPS=true` and the site loads via `https://`.

---

## Environment Variable Reference

### Required for Production

| Variable | Example | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | `a1b2c3d4e5...` (50+ chars) | Django cryptographic signing |
| `DEBUG` | `false` | Disables debug mode |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/dbname` | Auto-set by Railway Postgres |
| `ALLOWED_HOSTS` | `myapp.up.railway.app` | Comma-separated valid hostnames |
| `CSRF_TRUSTED_ORIGINS` | `https://myapp.up.railway.app` | Must include scheme |
| `ENABLE_HTTPS` | `true` | SSL redirect + secure cookies |
| `CLOUDINARY_URL` | `cloudinary://key:secret@cloud` | Image storage |

### Optional

| Variable | Default | Purpose |
|----------|---------|---------|
| `GEOJSON_CACHE_DURATION` | `60` | Cache TTL in seconds |
| `EMAIL_BACKEND` | Console backend | Set to SMTP for real emails |
| `EMAIL_HOST` | *(empty)* | SMTP server |
| `EMAIL_PORT` | `587` | SMTP port |
| `EMAIL_HOST_USER` | *(empty)* | SMTP username |
| `EMAIL_HOST_PASSWORD` | *(empty)* | SMTP password |
| `ADMIN_EMAIL` | *(empty)* | Notification recipient |

---

## File Manifest (Deployment-Related)

All paths relative to project root (alongside `manage.py`):

```
Procfile              — Railway process definitions
requirements.txt      — Python dependencies
runtime.txt           — Python version pin
nixpacks.toml         — System-level GeoDjango deps (GDAL, GEOS, PROJ)
.gitignore            — Git exclusions (MUST exclude .env)
bookworm/settings.py  — Django settings (DATABASE_URL support needed)
bookworm/middleware.py — CSP and security headers
bookworm/wsgi.py      — WSGI entry point (used by Gunicorn)
```
