# Bookworm Codebase Reference

A handoff document for any future Claude (or human collaborator) joining the Bookworm project. Read this before making changes — it captures structure, conventions, and the load-bearing decisions that aren't obvious from any single file.

Bookworm is a Django 5 + GeoDjango application that maps Little Free Libraries across British Columbia. It is deployed at <https://bookworm.guide>. The single Django app is `libraries/`; the project package is `bookworm/`.

**Last updated:** April 2026, post Phase 3 (spatial duplicate flagging + progressive rate-limit escalation).

---

## What changed in Phase 3

If you read the post-Phase-2 version of this doc, the diff to know about:

- One new model: `DuplicateCandidate` — records the spatial relationship between a newly-submitted library and existing libraries within `DUPLICATE_PROXIMITY_RADIUS_M`. Identity-agnostic; future-trust-tier-friendly.
- One new field on `Library`: `merged_into` (self-FK, `on_delete=SET_NULL`, `related_name='merged_from'`). Audit pointer; combined with `is_active=False` it tombstones a merged-away duplicate.
- One new admin: `DuplicateCandidateAdmin` with side-by-side comparison view and three bulk actions: `approve_as_new`, `reject`, `merge_into_existing`. Merge is single-select-only.
- New filter on `LibraryAdmin`: `HasPendingDuplicatesFilter` ("Flagged as potential duplicate").
- Migration `0004_duplicate_candidate.py` added.
- New helper: `_flag_duplicates(library)` in `views.py`, called from `submit_library` after Shelfie creation. Try/except-wrapped — never breaks submission.
- New settings constants: `DUPLICATE_PROXIMITY_RADIUS_M = 20`, `DUPLICATE_CANDIDATE_MAX = 3`, `RATE_LIMIT_ESCALATION_TIERS = [1, 3, 6, 6]`, `RATE_LIMIT_OFFENSE_WINDOW_S = 86400`.
- **Progressive rate-limit escalation now implemented.** First offense per key keeps the configured period; subsequent offenses within 24h escalate by `[1, 3, 6, 6]` multipliers. Per-key opt-out via `'escalates': False` on `here_resolve` and `here_log` (Hunt-burst-friendly). Per-IP, per-key tracking. Future trust-tier bypass hook: `request.bookworm_skip_rate_limit = True` skips both the check and offense registration.
- Auto-close-on-success bug in `map.html` fixed. Two `htmx:afterSwap` listeners merged into one. Library detail / submit offcanvases no longer close themselves 20s after a successful submission.
- Stale `# 5 per hour` comment on `issue_report` rate limit fixed (value is 10/hour).
- New tests: `test_phase3_models.py`, `test_phase3_views.py`, `test_phase3_admin.py`, `test_phase3_rate_limiting.py`.
- `_form_loaded_at` consumes `timezone.now().timestamp()` — unchanged from Phase 1, just calling it out because Phase 3 didn't touch the bot-detection layer.

---

## What changed in Phase 2

If you read the previous version of this doc, the diff to know about:

- Two new models: `StewardPartnership` (was tentatively called `StewardConsent` in earlier drafts; final name is `StewardPartnership`) and `ScanEvent`.
- Six new URLs: `/partners/`, `/partners/submit/`, `/partners/thanks/`, `/here/`, `/here/resolve/`, `/here/log/`.
- Three new top-level templates: `here.html`, `partnership_form.html`, `partnership_thanks.html`.
- Two new partials: `partials/here_picker.html`, `partials/here_no_match.html`.
- New form: `StewardPartnershipForm` (uses `HoneypotMixin` like the others).
- New admin classes: `StewardPartnershipAdmin`, `ScanEventAdmin` (read-mostly).
- Migration `0003_stewardpartnership_scanevent.py` added.
- Rate limits **substantially loosened** for human contributors and a new `here_resolve` rate limit added (see Rate Limiting section).
- `IssueReportAdmin.mark_unresolpyved` typo from the earlier doc is now fixed (`mark_unresolved`).
- The `submit_library_form` view no longer renders a standalone `submit_library.html` page — it redirects non-HTMX requests to `/map/?submit=1`. The map page handles auto-opening the offcanvas. There is no standalone full-page submit template.
- New tests: `test_phase2_models.py`, `test_phase2_forms.py`, `test_phase2_views.py`.

---

## Quick orientation

- **Stack:** Django 5 (GeoDjango) · PostgreSQL + PostGIS (Neon) · Cloudinary (image storage) · Bootstrap 5 + HTMX + Leaflet.js · WhiteNoise (static files) · Gunicorn · Docker on Railway.
- **Repo root** (local dev): `/Users/theda/PycharmProjects/PythonProject/Bookworm/bookworm/`
- **Domain:** `bookworm.guide` (Porkbun, served from Railway).
- **Single-app project.** All domain logic lives in the `libraries` app. No public auth — submissions are anonymous, with admin-only moderation via Django admin.
- **Tone of the codebase:** pragmatic, well-commented, trust-first-with-defenses. Honeypot fields, timing checks, and rate limits gate writes; nothing is locked behind login.

---

## Top-level layout

```
bookworm/                              # repo root (also the Django project working dir)
├── Dockerfile                         # Railway deployment image
├── start.sh                           # Container ENTRYPOINT (migrate, collectstatic, gunicorn)
├── Procfile.bak / nixpacks.toml       # Old deploy attempts; do not resurrect
├── requirements.txt
├── runtime.txt
├── pytest.ini
├── manage.py
├── .env                               # Local-only secrets
├── DEPLOYMENT_ROADMAP.md              # Living deployment doc
├── PARTNERSHIP_OUTREACH.md            # Tier-1 outreach plan, partner contacts
├── CODEBASE.md                        # ← you are here
│
├── bookworm/                          # Django project package
│   ├── settings.py                    # Environment-driven settings
│   ├── urls.py                        # Project URLconf
│   ├── middleware.py                  # SecurityHeadersMiddleware (CSP etc.)
│   ├── asgi.py / wsgi.py
│
├── libraries/                         # The single domain app
│   ├── models.py                      # Library, Shelfie, IssueReport, StewardPartnership, ScanEvent, DuplicateCandidate
│   ├── views.py                       # All views (function-based)
│   ├── forms.py                       # ModelForms with HoneypotMixin
│   ├── urls.py                        # App URLconf (namespace 'libraries')
│   ├── admin.py                       # Custom Django admin
│   ├── apps.py                        # AppConfig
│   ├── sitemaps.py                    # LibrarySitemap, StaticSitemap
│   ├── rate_limiting.py               # Decorator + helpers + Phase 3 escalation
│   ├── tests.py                       # (legacy/empty)
│   ├── migrations/                    # 0001_initial · 0002_* (two siblings) · 0003_stewardpartnership_scanevent · 0004_duplicate_candidate
│   │
│   ├── templates/libraries/
│   │   ├── landing.html               # Public landing page (/) — hero, stats, CTA
│   │   ├── map.html                   # Main map page (/map/) — 53KB, contains most JS
│   │   ├── library_detail_page.html   # Standalone /library/<id>-<slug>/ page (SEO + OG)
│   │   ├── here.html                  # /here/ QR landing — geolocate + resolve flow (~15KB)
│   │   ├── partnership_form.html      # /partners/ steward consent form (~10KB)
│   │   ├── partnership_thanks.html    # /partners/thanks/ confirmation
│   │   └── partials/
│   │       ├── library_detail.html
│   │       ├── submit_form.html       # New library submission (HTMX-only target now)
│   │       ├── submit_success.html
│   │       ├── shelfie_form.html / shelfie_success.html
│   │       ├── shelfie_report_form.html / shelfie_report_success.html
│   │       ├── report_form.html / report_success.html
│   │       ├── form_error.html
│   │       ├── rate_limited.html
│   │       ├── here_picker.html       # /here/ picker for ambiguous matches
│   │       └── here_no_match.html     # /here/ fallback when no library within 100m
│   │
│   ├── static/libraries/
│   │   ├── css/bookworm.css           # Shared design system (CSS variables)
│   │   ├── js/
│   │   │   ├── library-detail.js      # Lightbox, reporting, toasts
│   │   │   └── phase1-enhancements.js # Upload progress, image validation
│   │   └── images/                    # Logos, favicon.ico, OG default, hero
│   │
│   ├── templatetags/bookworm_tags.py  # cloudinary_og_image filter
│   │
│   └── tests/
│       ├── conftest.py                # pytest fixtures
│       ├── test_models.py / test_forms.py / test_views.py        # Phase 1
│       ├── test_phase2_models.py / test_phase2_forms.py / test_phase2_views.py
│       └── test_phase3_models.py / test_phase3_views.py / test_phase3_admin.py / test_phase3_rate_limiting.py
│
├── scripts/backup.sh
├── static/                            # Project-level static (mostly empty)
└── staticfiles/                       # collectstatic output (gitignored)
```

---

## Architecture in one paragraph

The browser loads `map.html`, which boots Leaflet, fetches `/api/libraries.geojson`, and clusters markers. Clicking a marker fires an HTMX request to `/library/<pk>/` that returns the `library_detail.html` partial into a Bootstrap offcanvas. From inside the offcanvas, "Add Shelfie" / "Report Issue" buttons swap their form partials into the same offcanvas slot. Form submissions POST back; on success the offcanvas swaps to a success partial, the map reloads markers, and a toast fires. Direct visits to `/library/<pk>-<slug>/` render `library_detail_page.html` (a standalone page that includes the same `library_detail.html` partial), used for SEO, social sharing, and as a destination from `/here/`. The `/here/` route is the QR-sticker landing: a minimal full page asking the user to share location, JS posts coords to `/here/resolve/`, the server picks the nearest library (direct match within 25m, picker for 25–100m ambiguity, no-match beyond 100m) and either returns an `HX-Redirect` to the library page or swaps in `here_picker.html` / `here_no_match.html`. `/partners/` is a separate full-page form for stewards who scanned a QR on their consent envelope. Submissions are anonymous; everything is gated by IP-based rate limits, a honeypot field, and a form-load-time anti-bot check. Admin moderation happens only in Django admin.

---

## Data model (`libraries/models.py`)

### `Library`
- `name` (CharField, blank) — optional; drives slug.
- `description` (TextField, blank).
- `location` (PointField, srid=4326) — WGS84. **Point order is `(lng, lat)`** in GeoDjango.
- `submitted_by_email` (EmailField, blank) — admin-only.
- `is_verified` (Bool, indexed) — admin approval gate.
- `is_active` (Bool, indexed) — soft-delete.
- `slug` (SlugField, blank) — auto-generated from `name` in `save()`.
- `last_updated` (DateTimeField, indexed) — refreshed by Shelfie `post_save` signal.
- `created_at` (DateTimeField, auto_now_add).
- `merged_into` (FK → self, nullable, on_delete=SET_NULL, related_name='merged_from') *(new in Phase 3)* — set by the duplicate-merge admin action when this library was a duplicate consolidated into another. Combined with `is_active=False` this row becomes a tombstone preserving audit history.

Properties: `freshness_status`, `freshness_color`, `latest_shelfie`. `get_absolute_url()` returns the SEO URL `/library/<pk>-<slug>/` if slug exists, else `/library/<pk>/`.

Indexes: `(is_verified, is_active)` composite, plus `last_updated`. PostGIS auto-creates a GiST index on `location`.

### `Shelfie`
- `library` (FK → Library, related_name='shelfies').
- `photo` (CloudinaryField, folder='bookworm/shelfies', auto-transformed to 1200×1200 limit, q_auto, f_auto).
- `book_highlights` (TextField, blank).
- `uploaded_at` (DateTimeField, indexed).

Signal: `post_save` → `update_library_timestamp` refreshes `library.last_updated` only on creation.

### `IssueReport`
- `library` (FK → Library).
- `shelfie` (FK → Shelfie, nullable) — present when reporting a specific photo.
- `issue_type` (CharField, choices) — combined `LIBRARY_ISSUE_CHOICES` + `PHOTO_ISSUE_CHOICES`.
- `description` (TextField, blank).
- `is_resolved` (Bool, indexed).
- `report_type` property → `'photo'` or `'library'`.

### `StewardPartnership` *(new in Phase 2)*
A steward's response to the consent envelope. Stewards may submit before their library is in Bookworm, so `library` is nullable; admin matches consent → library after review.

- `library_address` (CharField, max 300, required) — free-text location ("front lawn of 1234 Main St").
- `name` (CharField, max 200, blank) — optional steward name.
- `contact` (CharField, max 200, required) — email or phone, never displayed.
- `sticker_interest` (BooleanField, default False) — opt-in for QR sticker.
- `hunt_interest` (CharField, choices: `yes` / `tell_me_more` / `no`, default `no`).
- `hunt_message` (CharField, max 140, blank) — optional one-liner for visitors during Library Hunt.
- `library` (FK → Library, nullable, on_delete=SET_NULL, related_name='steward_partnerships') — admin-populated.
- `is_processed` (Bool, indexed, default False) — admin workflow flag.
- `admin_notes` (TextField, blank).
- `submitted_at` (DateTimeField, auto_now_add, indexed).

Indexes: `(is_processed, -submitted_at)` composite.

`hunt_interest_display_short` property returns "Yes" / "Tell me more" / "No" for admin list display.

### `ScanEvent` *(new in Phase 2)*
Records each `/here/` resolution outcome for analytics. Privacy-preserving: no IP, no user agent, coordinates rounded to 4 decimal places (~11m precision). Enough for cluster analysis (find missing libraries, tune picker thresholds), not enough to reconstruct a path.

- `outcome` (CharField, choices, indexed) — one of `matched` / `picker_shown` / `picker_resolved` / `no_match` / `denied` / `error`.
- `matched_library` (FK → Library, nullable, on_delete=SET_NULL, related_name='scan_events').
- `candidate_count` (PositiveSmallIntegerField, default 0).
- `location` (PointField, nullable, srid=4326) — already rounded by the time it lands here (`_round_coord` in views).
- `accuracy_meters` (PositiveIntegerField, nullable) — browser-reported.
- `occurred_at` (DateTimeField, auto_now_add, indexed).

Indexes: `(outcome, -occurred_at)` composite.

### `DuplicateCandidate` *(new in Phase 3)*
Records a spatial proximity match between a newly-submitted library and an existing one. Created at submission time when a new library lands within `DUPLICATE_PROXIMITY_RADIUS_M` (default 20m) of an existing active library. Up to `DUPLICATE_CANDIDATE_MAX` (default 3) closest matches are recorded per submission. **Never blocks the submission** — the submitter sees the standard success page; admin gains a review surface.

Deliberately identity-agnostic: records the spatial relationship, not who submitted. The future trust-tier system can layer on top without schema churn.

- `submitted_library` (FK → Library, on_delete=CASCADE, related_name='duplicate_candidates') — the new submission that triggered the flag.
- `existing_library` (FK → Library, on_delete=CASCADE, related_name='duplicate_matches') — the suspected duplicate.
- `distance_meters` (PositiveSmallIntegerField) — captured at submit time from the PostGIS query.
- `disposition` (CharField, choices, indexed, default `pending`) — one of `pending`, `approved_new`, `merged`, `rejected`.
- `admin_notes` (TextField, blank).
- `created_at` (DateTimeField, auto_now_add, indexed).
- `resolved_at` (DateTimeField, nullable) — set when disposition leaves `pending`.

Indexes: `(disposition, -created_at)` composite. Class constants: `PENDING`, `APPROVED_NEW`, `MERGED`, `REJECTED`. Has `is_pending` property for clarity.

**Migrations:** `0001_initial.py`, then `0002_issuereport_shelfie_alter_issuereport_issue_type.py` and `0002_library_slug.py` (siblings — Django merges by name). `0003_stewardpartnership_scanevent.py` depends on **both** 0002s explicitly. `0004_duplicate_candidate.py` depends on `0003`. New migrations should be `0005_*` and depend on `0004_duplicate_candidate`.

---

## URL map

Project-level (`bookworm/urls.py`):
- `/admin/` → Django admin
- `/sitemap.xml` → combined sitemap
- everything else → `libraries.urls`

App-level (`libraries/urls.py`, namespace `libraries`):

| Path | Name | View | Notes |
|---|---|---|---|
| `/` | `landing` | `landing_page` | Hero + 5-min cached stats. |
| `/map/` | `map` | `map_view` | Main interactive map. Accepts `?submit=1` to auto-open offcanvas. |
| `/api/libraries.geojson` | `libraries_geojson` | `libraries_geojson` | GET; bbox/proximity filters; cached by hashed key. |
| `/api/geocode/` | `geocode` | `geocode_address` | GET; Nominatim proxy; rate-limited 30/min. |
| `/library/<int:pk>-<slug:slug>/` | `library_detail` | `library_detail` | Canonical SEO URL. |
| `/library/<int:pk>/` | `library_detail_bare` | `library_detail_bare` | Bare PK; redirects to canonical for browsers, serves partial for HTMX. |
| `/submit/` | `submit_form` | `submit_library_form` | GET. **HTMX returns partial; non-HTMX redirects to `/map/?submit=1`** — there is no standalone full-page submit template. |
| `/submit/create/` | `submit_library` | `submit_library` | POST. On non-HTMX validation failure, also redirects to `/map/?submit=1`. |
| `/library/<library_pk>/shelfie/` | `upload_shelfie` | `upload_shelfie` | POST. |
| `/library/<library_pk>/shelfie/form/` | `shelfie_form` | `shelfie_form_partial` | GET partial. |
| `/library/<library_pk>/report/` | `report_issue` | `report_issue` | POST. |
| `/library/<library_pk>/report/form/` | `report_form` | `report_form_partial` | GET partial. |
| `/shelfie/<shelfie_pk>/report/` | `report_shelfie` | `report_shelfie` | POST. |
| `/shelfie/<shelfie_pk>/report/form/` | `shelfie_report_form` | `shelfie_report_form_partial` | GET partial. |
| `/partners/` | `partnership_form` | `partnership_form` | GET, full page. **Steward consent form.** |
| `/partners/submit/` | `partnership_submit` | `partnership_submit` | POST. Redirects to thanks on success; re-renders form on failure. |
| `/partners/thanks/` | `partnership_thanks` | `partnership_thanks` | GET, post-submission confirmation. |
| `/here/` | `here_landing` | `here_landing` | GET, full page. **QR sticker landing target.** |
| `/here/resolve/` | `here_resolve` | `here_resolve` | POST. Receives `lat`, `lng`, `accuracy`. Returns `HX-Redirect` (direct match), picker partial (ambiguous), or no-match partial. |
| `/here/log/` | `here_log` | `here_log` | POST, fire-and-forget. JS calls this on `denied` / `error` geolocation outcomes. |
| `/robots.txt` | `robots_txt` | `robots_txt` | Dynamic. |
| `/health/` | `health` | `health_check` | UptimeRobot target. |

**HTMX-vs-browser distinction** is detected via the `HX-Request` header on the library detail and submit form views, not separate URLs. The `/here/` flow and `/partners/` flow use traditional GET/POST patterns within full-page templates (HTMX is used inside `here.html` for the resolve call, but `/partners/` is straight Django form submission).

---

## Views (`libraries/views.py`)

All views are function-based. Patterns to know:

### General patterns (Phase 1 unchanged)
- **Caching.** `landing_page` caches stats 5 min. `libraries_geojson` builds a cache key from a bbox rounded to 3 decimals (~100m precision) plus near-lat/lng/radius, hashes md5, caches for `GEOJSON_CACHE_DURATION` (default 120 in prod). Sets `X-Cache: HIT|MISS`.
- **N+1 prevention.** GeoJSON uses `annotate(shelfie_count=Count('shelfies'))` and `prefetch_related`. Detail views use `Prefetch('shelfies', queryset=Shelfie.objects.order_by('-uploaded_at'))`.
- **Rate limiting.** Decorator on POST endpoints. Limits live in `settings.RATE_LIMIT_SETTINGS` and override decorator defaults.
- **Anti-bot timing.** `check_submission_timing(request)` reads hidden `_form_loaded_at` field; bails if elapsed < `MIN_SUBMISSION_TIME_SECONDS` (default 2s).
- **Honeypot.** Hidden `website_url` field; `HoneypotMixin.clean_website_url` rejects on submission. POST views also check `request.POST.get('website_url')` belt-and-suspenders.
- **HTMX detection.** `request.headers.get('HX-Request')` switches between partial and full page or JsonResponse.
- **Email notifications.** Library, shelfie, and partnership POSTs send admin emails via `send_mail(..., fail_silently=True)` when `ADMIN_EMAIL` is set.
- **Logging.** `logger.info` with `extra={...}` JSON-friendly fields on every successful submission.

### `/here/` flow (Phase 2)

The picker constants are tunable and live as module-level constants near the helpers in `views.py`:

```python
HERE_DIRECT_MATCH_RADIUS_M = 25     # nearest within 25m → likely the right one
HERE_PICKER_RADIUS_M = 100          # nothing past 100m is a candidate
HERE_DISAMBIGUATION_GAP_M = 50      # gap between #1 and #2 to call match "clear"
HERE_PICKER_MAX_CANDIDATES = 3      # most candidates shown in picker
```

Decision tree in `here_resolve`:

1. Validate lat/lng. Invalid → log `error`, return `here_no_match.html` with status 400.
2. Query candidates within 100m, ordered by distance. Take top `HERE_PICKER_MAX_CANDIDATES + 1`.
3. No candidates → log `no_match`, return `here_no_match.html`.
4. Compute `is_clear_winner`: nearest within 25m **AND** (only one candidate, OR gap to second ≥ 50m).
5. Clear winner → log `matched`, return empty body with `HX-Redirect: <library_url>` header.
6. Else → log `picker_shown`, return `here_picker.html` with top 3 candidates.

`_log_scan(...)` in views is the analytics writer — wrapped in try/except so analytics never crashes user flow. Always rounds coords via `_round_coord(value, places=4)` before storing.

`here_log` is the JS-callback endpoint for `denied` / `error` outcomes (geolocation API failures). Whitelist of valid outcomes; falls through to `error` for anything else. Returns empty 200.

### Spatial duplicate flagging *(Phase 3)*

The `_flag_duplicates(library)` helper sits near `_log_scan` in `views.py` — same convention: submission-time analytics-style sidecar, try/except-wrapped so it can't break user flow. Called from `submit_library` immediately after Shelfie creation.

Query shape: `Library.objects.filter(is_active=True, location__distance_lte=(library.location, D(m=radius_m))).exclude(pk=library.pk).annotate(distance=Distance(...)).order_by('distance')[:DUPLICATE_CANDIDATE_MAX]`. Includes unverified-but-active libraries deliberately — catches the most common duplicate scenario (user submits twice from the same form-load before either is verified). Excludes inactive (soft-deleted) libraries.

Distance is captured into `DuplicateCandidate.distance_meters` from the annotation, rounded to the nearest integer. Settings constants `DUPLICATE_PROXIMITY_RADIUS_M` and `DUPLICATE_CANDIDATE_MAX` are read via `getattr(settings, ..., default)` so the helper survives if either constant is removed.

### `/partners/` flow (Phase 2)

Three views, traditional form pattern:

- `partnership_form` (GET): renders `partnership_form.html` with empty `StewardPartnershipForm` and `form_loaded_at` timestamp.
- `partnership_submit` (POST, rate-limited): runs timing check, honeypot check, then `form.is_valid()`. Validation errors re-render the form with status 422. On success, saves the model, fires admin email, logs, redirects to thanks.
- `partnership_thanks` (GET): static confirmation page.

Notice the form's `clean()` method has a UX nudge: if the steward declines both the sticker AND the Hunt, it adds a non-field error suggesting they probably hit the wrong button. **This is a soft warning, not a blocker — the form still saves on resubmit if the steward really meant it.** The view re-renders with status 422 and the warning visible; the steward can adjust or simply resubmit.

---

## Forms (`libraries/forms.py`)

All forms use `HoneypotMixin` first in MRO. The mixin injects `website_url` CharField with `class="hp-field"` (CSS-hidden), `tabindex="-1"`, `aria-hidden`, plus `clean_website_url` raising `ValidationError` if filled.

- **`LibrarySubmissionForm(HoneypotMixin, ModelForm)`** — fields: `name`, `description`, `submitted_by_email`. Adds hidden `latitude`/`longitude`, required `photo`, optional `book_highlights`. `save()` constructs `Point(lng, lat, srid=4326)`, forces `is_verified=False`. View creates the initial Shelfie from `cleaned_data['photo']` after.
- **`ShelfieUploadForm(HoneypotMixin, ModelForm)`** — fields: `photo`, `book_highlights`. Takes `library` kwarg. **Auto-published on verified libraries — no admin gate.**
- **`IssueReportForm(HoneypotMixin, ModelForm)`** — takes `library` and optional `shelfie` kwargs. Swaps `issue_type.choices` based on `shelfie` presence.
- **`StewardPartnershipForm(HoneypotMixin, ModelForm)`** *(new)* — fields: `library_address`, `name`, `contact`, `sticker_interest`, `hunt_interest`, `hunt_message`. Custom `clean()` adds the "you declined both" non-field warning (see `/partners/` flow above). Custom `clean_contact()` ensures non-empty trimmed string. Hunt date hardcoded in label as "Saturday, August 15, 2026" — **change here when the date is finalized.**

---

## Rate limiting (`libraries/rate_limiting.py`)

Custom decorator backed by Django's database cache (works across Gunicorn workers). Phase 3 added progressive escalation; the decorator signature `rate_limit(key_prefix, limit=5, period=3600)` is unchanged.

### Two cache key spaces

- `rate_limit:{key_prefix}:{ip}` — window counter. JSON payload: `count`, `first_request` (ISO), `effective_period` (post-escalation), `offense_registered` (bool). TTL = `effective_period`.
- `rate_limit_offenses:{key_prefix}:{ip}` *(Phase 3)* — escalation tracker. JSON payload: `tier` (1-indexed), `last_offense_at`. TTL = `RATE_LIMIT_OFFENSE_WINDOW_S` (default 86400 = 24h).

### Helpers

- `get_client_ip` handles `X-Forwarded-For` (Railway is behind a proxy).
- `get_rate_limit_info(key_prefix, ip, limit=None)` returns `(count, seconds_until_reset, is_limited)`. The decorator passes its already-resolved `limit` so settings overrides for known keys and decorator args for unknown keys both work correctly. Reads stored `effective_period` so the surfaced countdown reflects the *current* tier.
- `increment_rate_limit(key_prefix, ip, period)` — `period` is the *effective* (possibly escalated) period. **Known race condition** flagged in code: simultaneous requests can both read-then-write and undercount. Acceptable at current scale.
- `_read_offense_tier`, `_bump_offense_tier`, `_effective_period_for_tier` *(Phase 3)* — offense tracking primitives. Tier escalates by 1 per offense, capped at `len(RATE_LIMIT_ESCALATION_TIERS)`. Effective period = `base_period * tiers[tier-1]`.
- `_mark_offense_registered`, `_is_offense_already_registered` *(Phase 3)* — the "once per blocked window" guarantee. Spam-clicking submit while blocked does NOT escalate further.
- `format_time_remaining` produces user-facing strings.
- `rate_limit(key_prefix, limit, period)` decorator. On limit hit, registers an offense (if not already registered for this window), bumps tier, rewrites `effective_period`, logs warning, returns `partials/rate_limited.html` (HTMX) or JSON 429. **Bypass hook:** `getattr(request, 'bookworm_skip_rate_limit', False)` skips both the check and offense registration. Future trust-tier middleware sets it; nothing sets it today.
- `check_submission_timing(request)` reads `_form_loaded_at` POST field, returns `(is_suspicious, message)`.

### What counts as an offense

*One transition from "not blocked" to "blocked" within a single rate-limit window.* The first request that hits `count >= limit` in a fresh window registers the offense. Subsequent blocked requests in the same window do not re-escalate. Once the window expires, the offense record (separate cache key, 24h TTL) is still alive — the next time the user hits the limit again, tier increments.

### Current limits (`settings.RATE_LIMIT_SETTINGS`) — substantially loosened from launch defaults

| Key | Limit | Period | Escalates? | Notes |
|---|---|---|---|---|
| `library_submit` | 50 | 600s (10 min) | yes | Tier 2 = 30 min, tier 3+ = 60 min cap. |
| `shelfie_upload` | 50 | 1800s (30 min) | yes | Tier 2 = 90 min, tier 3+ = 3h cap. |
| `issue_report` | 10 | 3600s (1 hour) | yes | Tier 2 = 3h, tier 3+ = 6h cap. |
| `geocode_search` | 30 | 60s (1 min) | yes | Tier 2 = 3 min, tier 3+ = 6 min cap. |
| `steward_partnership` | 5 | 3600s (1 hour) | yes | Phase 2; intentionally tight. |
| `here_resolve` | 20 | 300s (5 min) | **no** | Hunt-burst-friendly. Honest users hitting the limit should not be locked out of their stickers. |
| `here_log` | 20 | 300s (5 min) | **no** | Same reasoning. |

**Always change limits in `settings.py`, not the decorator argument** — for keys present in settings, the settings values override decorator defaults. For keys NOT in settings (zero call sites today), decorator args are honoured.

### Escalation schedule

`RATE_LIMIT_ESCALATION_TIERS = [1, 3, 6, 6]` — the multipliers applied to base period at tier 1/2/3/4+. Tier caps at the table length. To change the schedule, edit settings; no code change needed.

`RATE_LIMIT_OFFENSE_WINDOW_S = 86400` — how long an offense record persists after the last offense. After 24h of quiet, the next offense resets to tier 1.

### Future trust-tier integration

When the trust-tier system arrives, middleware can set `request.bookworm_skip_rate_limit = True` for users at or above a chosen tier, and the decorator will pass through without checking or recording offenses. The hook is in place; no decorator changes will be required.

---

## Settings (`bookworm/settings.py`)

Environment-driven via `python-dotenv`. SECRET_KEY required in prod.

- **`ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`** — comma-separated env vars.
- **Database.** `DATABASE_URL` via `dj-database-url` (Railway/Neon) or individual `DB_*` vars. Engine forced to `django.contrib.gis.db.backends.postgis` — **never remove this override**, dj-database-url defaults to plain psycopg2 which breaks GeoDjango.
- **Storages (Django 5.x format).**
  - `default` → `cloudinary_storage.storage.MediaCloudinaryStorage`
  - `staticfiles` → `whitenoise.storage.CompressedManifestStaticFilesStorage`
- **Cloudinary.** Configured from `CLOUDINARY_URL`. **Don't re-add the old `CLOUDINARY_STORAGE` dict** — it overrode URL parsing.
- **Caching.** `DatabaseCache` on `bookworm_cache_table`. `start.sh` runs `createcachetable` on every deploy (idempotent).
- **GDAL/GEOS paths.** Hardcoded macOS Homebrew paths; Linux/Docker uses Django auto-detect from apt-installed libs.
- **Logging.** Console handler. JSON formatter in production, verbose in DEBUG.
- **HTTPS.** Gated on `ENABLE_HTTPS=true` env var. HSTS commented out — enable manually after confirming HTTPS is stable.
- **Email.** Console backend by default; SMTP via env. `ADMIN_EMAIL` controls notification delivery.
- **`MAX_UPLOAD_SIZE_MB = 10`** — both Django's `*_UPLOAD_MAX_MEMORY_SIZE` and a separate var passed to forms for client-side validation.
- **`MIN_SUBMISSION_TIME_SECONDS = 2`** — anti-bot timing threshold.

---

## Security middleware (`bookworm/middleware.py`)

`SecurityHeadersMiddleware` adds five headers (skipping CSP for `/admin/`):

- **CSP** — built dynamically. Allows: self, jsdelivr, unpkg, Google Fonts, Cloudinary, OSM tiles, CartoDB tiles, Nominatim. Uses `'unsafe-inline'` for both scripts and styles because all top-level templates contain inline `<script>`/`<style>` blocks. **CSP supports `/here/` and `/partners/` already** — both load Bootstrap from jsdelivr, fonts from Google Fonts, HTMX from unpkg (in `here.html`).
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(self), camera=(self), microphone=()` — **important: `geolocation=(self)` is what allows `/here/` to call `navigator.geolocation`.**

Middleware order matters — placed after `whitenoise` and before sessions/CSRF.

---

## Templates and front-end conventions

### The "centralization" rule
**Load-bearing.** All page-specific styles and JavaScript live inline in the consuming top-level template (`map.html`, `here.html`, `partnership_form.html`, etc.) — not in partials. Partials contain only HTML + HTMX attributes + occasional inline `onclick` handlers. Reasons:

- Partials are HTMX swap targets — `<script>` inside risks double-execution.
- Single source of truth for page state.
- Shared JS lives in `static/libraries/js/library-detail.js` or `phase1-enhancements.js` only when reused across multiple top-level pages.

When adding new functionality: **page-specific → top-level template script block; reused → shared JS file; never → inside a partial.** This applies to the new Phase 2 pages too — the picker and no-match partials are deliberately style-free, and `here.html` owns all their visual rules.

### Shared design system (`static/libraries/css/bookworm.css`)
Imported by all top-level templates. Defines CSS variables:

- Primary palette `--color-primary-{50…900}` (warm teal/forest, primary 800 = `#1a5f4a`).
- Accent palette `--color-accent-{100…600}` (warm amber).
- Neutrals `--color-neutral-{50…900}` (warm grays).
- Semantic colors `--color-fresh`, `--color-stale`, `--color-needs-visit`, `--color-danger` plus `*-bg` variants.
- Typography: `--font-display: 'Fraunces'`, `--font-body: 'DM Sans'`.
- Spacing: `--header-height`, `--radius-{sm,md,lg,xl,full}`.
- Shadows: `--shadow-{sm,md,lg,xl}`.
- Transitions: `--transition-{fast,base,slow}`.

**Always reference these variables instead of hardcoding hex/rem values.** The Phase 2 templates follow this convention; QA should verify it remained consistent.

### Top-level templates

- **`landing.html`** — landing page. Hero + stats, how-it-works, CTA to map.
- **`map.html`** — main app. Leaflet, marker cluster, "Add Library" offcanvas with embedded location picker (a second Leaflet instance), detail offcanvas loading `partials/library_detail.html` via HTMX. Reads `?submit=1` to auto-open the submit offcanvas. Geolocation control is manual-tap only — no auto-prompt (browsers block non-gesture geolocation). CONFIG object with URLs and constants. Toast container.
- **`library_detail_page.html`** — standalone SEO page. Open Graph + Twitter card meta, JSON-LD `schema.org/Place`, canonical URL. Body uses `{% include 'libraries/partials/library_detail.html' %}` — same partial as the offcanvas. **The QR funnel from `/here/` lands here when a library matches directly.**
- **`here.html`** *(Phase 2)* — the QR sticker landing. Minimal full page: brand/headline/sub, single "Find my library" button (high-prominence). Self-contained vanilla JS (no HTMX-driven page initially — it loads HTMX from unpkg but uses `htmx.ajax()` programmatically in the click handler). Calls `navigator.geolocation.getCurrentPosition` with `enableHighAccuracy: true`, 12s timeout, 30s `maximumAge`. POSTs coords to `/here/resolve/` and swaps result into `#here-result`. Has an `htmx:beforeSwap` listener that allows status codes 200/400/422 to swap (the resolver uses 400 for invalid coords with the no-match template). On geolocation denial/error, calls `/here/log/` fire-and-forget and shows a JS-rendered error card (uses `textContent` to avoid XSS). Includes a `<details class="what-is">` "What is Bookworm?" disclosure for first-time scanners. Footer credits the Vancouver Foundation grant.
- **`partnership_form.html`** *(Phase 2)* — full-page steward consent form. Single `<form method="post">` to `/partners/submit/`, no HTMX. CSRF + `_form_loaded_at` hidden. Honeypot rendered via `{{ form.website_url }}` inside a `.hp-field` wrapper with `aria-hidden`. The Hunt block is highlighted with `--color-accent-100` background + 4px left border. Live character counter (vanilla JS) for `hunt_message` (140 char max). `<meta name="robots" content="noindex">` — steward-facing, not search-indexed. **The Hunt date "Saturday, August 15, 2026" appears as the legend label inline** — when the date changes, update both `forms.py` (label) and any Hunt copy in the form template if you've added more.
- **`partnership_thanks.html`** *(Phase 2)* — minimal centered card with two CTA links (open map / back home). `<meta name="robots" content="noindex">`. Footer credits the grant.

### Partials

Located in `templates/libraries/partials/`. Each has a single responsibility. Phase 1 partials unchanged. Phase 2 additions:

- `here_picker.html` — list of 1–3 nearest candidates, each rendered as a `<a class="picker-link">` linking to `library.get_absolute_url`. Distance shown in metres. Fallback link at bottom: "None of these — open the full map." All styling lives in `here.html` (`.picker-list`, `.picker-link`, `.picker-name`, `.picker-desc`, `.picker-distance`, etc.).
- `here_no_match.html` — single result card with two stacked `btn-here-ghost` actions: "Add this library to Bookworm" → `/map/?submit=1`, and "Open the map and tap manually" → `/map/`. **Designed for the most common no-match case: an unmapped library that needs to be added.** All styling in `here.html`.

### Shared JS files
- **`library-detail.js`** — `openShelfieViewer`, `closeShelfieViewer`, `navigateShelfie`, `updateLightboxContent`, `openShelfieReport`, `reportCurrentShelfie`, `showToast`, `escapeHtml`, plus keyboard (←/→/Esc) and touch-swipe handlers. Imported by `map.html` and `library_detail_page.html`. **Not used by `here.html` or `partnership_form.html`** — they're standalone.
- **`phase1-enhancements.js`** — HTMX upload progress, client-side image validation, image preview, address search debouncing, retry handling. Imported only by `map.html`.

### Custom template tag
`{% load bookworm_tags %}` then `{{ shelfie.photo.url|cloudinary_og_image }}` → rewrites a Cloudinary URL to insert `c_fill,w_1200,h_630,g_center,q_auto,f_auto/` after `/upload/`. Used for OG and Twitter card images.

---

## Admin (`libraries/admin.py`)

Phase 1 unchanged (`LibraryAdmin`, `ShelfieAdmin`, `IssueReportAdmin`). Phase 2 additions: `StewardPartnershipAdmin`, `ScanEventAdmin`. Phase 3 additions: `DuplicateCandidateAdmin` and `HasPendingDuplicatesFilter`.

### `StewardPartnershipAdmin`
- `list_display`: `library_address_short`, `name`, `sticker_interest`, `hunt_interest_display_short` (custom method), `library`, `is_processed`, `submitted_at`.
- `list_filter`: `is_processed`, `sticker_interest`, `hunt_interest`, `submitted_at`.
- `search_fields`: `library_address`, `name`, `contact`, `hunt_message`, `admin_notes`.
- `autocomplete_fields = ('library',)` — admin types to search the matching Library record. **`LibraryAdmin` doesn't currently declare `search_fields` for itself in a way that supports this autocomplete cleanly** — it does define `search_fields = ['name', 'description', 'submitted_by_email']`, so autocomplete works via name/description/email. If autocomplete misbehaves, that's where to look.
- Fieldsets: "Steward submission" (address/name/contact/submitted_at) → "Partnership" (sticker/hunt/message) → "Admin workflow" (library FK, is_processed, admin_notes).
- Bulk actions: `mark_processed`, `mark_unprocessed`.
- `library_address_short`: truncates to 60 chars with ellipsis for list display.

### `ScanEventAdmin`
**Read-mostly.** `has_add_permission` and `has_change_permission` both return `False` — admins can browse and filter scans for analytics but can't edit them. `has_delete_permission` returns `True` for housekeeping (purging old scans).

- `list_display`: `occurred_at`, `outcome`, `matched_library`, `candidate_count`, `accuracy_meters`.
- `list_filter`: `outcome`, `occurred_at`.
- `date_hierarchy`: `occurred_at`.
- Everything is `readonly_fields`.

The `IssueReportAdmin.mark_unresolpyved` typo from earlier is now fixed (`mark_unresolved`).

### `DuplicateCandidateAdmin` *(new in Phase 3)*
Side-by-side review of potential duplicate library submissions.

- `list_display`: `id`, `submitted_link`, `existing_link`, `distance_meters`, `disposition`, `created_at`. The link methods render as `<a href='...'>#PK Name</a>` to the corresponding `LibraryAdmin` change view.
- `list_filter`: `disposition`, `created_at`. `date_hierarchy`: `created_at`.
- `search_fields`: `submitted_library__name`, `existing_library__name`, `admin_notes`.
- `readonly_fields` includes `side_by_side_view` — a custom `format_html` table showing both libraries' name, PK, coordinates, description, and latest shelfie photo for at-a-glance comparison.
- Three bulk actions:
  - **`approve_as_new`** — sets `disposition=APPROVED_NEW`, `resolved_at=now()`. Does NOT modify either library record. Clears the flag for admin; standard verification flow continues normally on the submitted library.
  - **`reject`** — sets `disposition=REJECTED`, `resolved_at=now()`. Soft-deletes the submitted library (`is_active=False`). Existing library untouched. `merged_into` stays NULL — reserved for actual merges.
  - **`merge_into_existing`** — single-select-only (multi-select aborts with an error message). Calls `_perform_merge(candidate)` (extracted staticmethod for testability) inside `transaction.atomic()`:
    1. Reassign FKs from submitted → existing for `Shelfie.library`, `IssueReport.library`, `StewardPartnership.library`. Bulk `.update(...)` calls — does NOT fire post_save signals.
    2. `existing.last_updated = max(existing.last_updated, submitted.last_updated)`. Bulk-shelfie reassignment doesn't fire the timestamp signal, so we set this explicitly. The doomed-row's freshness is correctly inherited; the survivor is never demoted.
    3. Submitted: `is_active=False`, `merged_into=existing`. Soft-delete with audit pointer.
    4. Candidate: `disposition=MERGED`, `resolved_at=now()`.
    5. **Sibling auto-resolve** — any other PENDING `DuplicateCandidate` rows where `submitted_library=submitted` get auto-marked `MERGED` with `resolved_at=now()`. Apartment-complex case: a submission flags 3 existing libraries → admin merges into one → other two pending flags would otherwise sit forever pointing at a now-deactivated submission.
  - The merge bypasses `Library.save()` via `Library.objects.filter(pk=...).update(...)` to skip the slug-overwrite side effect on the survivor.
  - On `IssueReport.shelfie`: the report's shelfie FK is preserved as-is. Since the shelfie's library FK was just moved from doomed → survivor, the report's shelfie pointer keeps resolving correctly.

### `HasPendingDuplicatesFilter` on `LibraryAdmin` *(new in Phase 3)*
SimpleListFilter with one option: "Flagged as potential duplicate." Filters libraries that ARE the suspected new submission (have a pending `DuplicateCandidate` where they're the `submitted_library`). Lets admin find flagged submissions from the existing library list. Uses `.distinct()` to avoid duplicate rows when a submission has multiple candidates.

---

## Sitemaps (`libraries/sitemaps.py`)

Unchanged from Phase 1. `/here/`, `/partners/`, and `/partners/thanks/` are **not** in the sitemap by design — `/here/` is a QR-only landing surface (no SEO value), and `/partners/` has `<meta name="robots" content="noindex">`.

---

## Caching strategy

- Backend: `DatabaseCache` on `bookworm_cache_table`.
- Cached: landing stats (5 min), GeoJSON (60s dev / 120s prod), rate limit counters (TTL = period).
- Invalidation: TTL-only. New library submissions become visible after at most `GEOJSON_CACHE_DURATION` seconds.
- `ScanEvent` rows are not cached — they're write-only from the resolver.

---

## Deployment

### Local (macOS, Conda)
1. `brew install gdal geos`.
2. `.env` with DEBUG=True, DB creds, CLOUDINARY_URL, ALLOWED_HOSTS=localhost,127.0.0.1.
3. PostGIS-enabled local Postgres (`CREATE EXTENSION postgis;`).
4. `python manage.py migrate && python manage.py createcachetable && python manage.py runserver`.

### Production (Railway)
- **Image:** `Dockerfile` (`python:3.12-slim` + apt-installed GDAL/GEOS/PROJ).
- **Entrypoint:** `start.sh` → migrate → createcachetable → collectstatic → createsuperuser (idempotent) → gunicorn.
- **Database:** Neon free-tier Postgres + PostGIS.
- **Image storage:** Cloudinary.
- **Static files:** WhiteNoise from gunicorn. `CompressedManifestStaticFilesStorage` requires `collectstatic` to have run.
- **Required env vars:** `SECRET_KEY`, `DATABASE_URL` (Neon), `CLOUDINARY_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `ENABLE_HTTPS=true`, `DEBUG=False`, optional `ADMIN_EMAIL`, `EMAIL_*`, `DJANGO_SUPERUSER_*`.
- **Domain:** `bookworm.guide` (Porkbun → Railway CNAME).
- **Health check:** `/health/`.

### Things that did not work — do not reintroduce
- **Nixpacks** for GDAL detection.
- **Procfile + `$PORT`** literal-string expansion.
- **`CLOUDINARY_STORAGE` dict alongside `CLOUDINARY_URL`**.
- **Missing Pillow** caused `ModuleNotFoundError`; explicit install in Dockerfile + requirements.

---

## Testing

- Runner: `pytest` with `pytest-django`. `pytest.ini` has `--reuse-db -v`.
- Phase 1 tests: `test_models.py`, `test_forms.py`, `test_views.py`.
- Phase 2 tests: `test_phase2_models.py`, `test_phase2_forms.py`, `test_phase2_views.py`. The `/here/` resolver is the most thoroughly tested surface — test setup uses fixed offsets in metres from a known Vancouver point so distance assertions are deterministic.
- Phase 3 tests: `test_phase3_models.py`, `test_phase3_views.py`, `test_phase3_admin.py`, `test_phase3_rate_limiting.py`. Same metres-offset pattern for spatial assertions. Rate-limit tests use `RequestFactory` + a tiny inline view (no URLconf pollution) and a `cache_clear` autouse fixture to wipe the rate-limit namespace between tests — `DatabaseCache` is shared across tests under `--reuse-db`.
- Key fixtures (`conftest.py`): `simple_staticfiles` (autouse, replaces `STORAGES` to use plain `StaticFilesStorage` because the Compressed manifest doesn't exist in tests), `verified_library`, `unnamed_library`, `unverified_library`, `inactive_library`, `stale_library`, `needs_visit_library`, `shelfie`, `issue_report`, `sample_image` (Pillow-generated 10×10 red JPEG).
- `CloudinaryField` in tests: populated with a plain string (e.g. `"bookworm/shelfies/test_photo"`); never hits real Cloudinary.

---

## Conventions and gotchas

1. **`Point(lng, lat, srid=4326)`** — longitude first. Mistaking puts libraries in Antarctica.
2. **`Library.save()` always overwrites slug** based on current `name`. Renaming changes canonical URL; old URLs still resolve via redirect.
3. **Auto-publish for shelfies on verified libraries.** New libraries require admin approval; new shelfies do not.
4. **Honeypot field is `website_url`.** Don't add a real form field by that name. The visible label "Leave this field empty" is intentional.
5. **`_form_loaded_at` hidden field.** Every GET that returns a form must include `form_loaded_at: timezone.now().timestamp()` in context. Without it the timing check passes silently — adding new forms without it weakens bot detection.
6. **HTMX status code allow-list.** `phase1-enhancements.js` allows 400/422/429 swap on `/map/`. `here.html` has its own scoped allow-list (200/400/422). Returning a partial with another error code gets swallowed.
7. **Two `0002_` migrations exist as siblings.** `0003_stewardpartnership_scanevent.py` depends on both explicitly. `0004_duplicate_candidate.py` depends on `0003`. New migrations should be `0005_*` and depend on `0004`.
8. **GeoJSON cache key precision.** Bbox rounded to 3 decimals (~100m). Pan-by-meter movements share cache.
9. **Geolocation prompt requires user gesture.** No auto-`setTimeout` prompts — browsers block them. The "Use My Location" button on `/map/` and "Find my library" on `/here/` are the only paths.
10. **`MIN_SUBMISSION_TIME_SECONDS = 2`** is generous. Real users never trip it.
11. **Filesystem MCP behavior** (for collaborators using Claude): `edit_file` is intermittent on this codebase; full-file `write_file` is the reliable fallback. Binary assets cannot be transferred via MCP — drop them in manually.
12. **`landing.html` has not been read in detail in this doc.** If modifying, read directly first.
13. **Picker thresholds are tunable.** `HERE_DIRECT_MATCH_RADIUS_M`, `HERE_PICKER_RADIUS_M`, `HERE_DISAMBIGUATION_GAP_M`, `HERE_PICKER_MAX_CANDIDATES` live near the top of the helpers section in `views.py`. After the first weeks of stickers in the wild, look at the `ScanEvent` distribution and tune.
14. **Hunt date is hardcoded** in `forms.py` (the `hunt_interest` label) as "Saturday, August 15, 2026". When this changes, update there. Check `partnership_form.html` for any other Hunt copy that should follow.
15. **Favicon path mismatch.** The Phase 2 templates (`here.html`, `partnership_form.html`, `partnership_thanks.html`) reference `{% static 'libraries/images/favicon.png' %}` but the actual file is `favicon.ico`. **This is a real bug** — those pages will 404 on the favicon. Either rename the file in templates to `favicon.ico` or add a `favicon.png`. Phase 1 templates use `favicon.ico` correctly.
16. **`/here/` and `/partners/` use Bootstrap 5.3.0**, while `map.html` and `library_detail_page.html` use Bootstrap 5.3.2. Cosmetic, but worth aligning eventually for consistency.
17. **`/here/` and `/partners/` import only Bootstrap CSS, not its JS bundle.** They don't use any JS components (toast, modal, offcanvas) so this is correct — but if you ever add a Bootstrap JS component to those pages, remember to include the bundle.
18. **`StewardPartnership.HUNT_INTEREST_*` constants** are defined on the model. Use them, not magic strings, when filtering or comparing.
19. **`ScanEvent` is append-only via the admin.** If you need to write a fixture or seed scan data, use `ScanEvent.objects.create(...)` directly — the admin's `has_add_permission=False` only affects the admin UI.
20. **`DuplicateCandidate` is created by `_flag_duplicates` at submission time.** Don't write candidate rows manually unless backfilling. The helper is the single source of creation logic and includes the cap-at-`DUPLICATE_CANDIDATE_MAX` and ordering rules.
21. **Merge action is single-select-only.** Selecting >1 candidate aborts with an error. Bulk merge would require per-row target selection, which doesn't fit Django's bulk-action model.
22. **The merge action bypasses `Library.save()`** via `.update()`. This is intentional — `Library.save()` overwrites the slug from `name`, which would corrupt the survivor's URL. If you ever extend `Library.save()` to do something the merge needs, update the merge logic explicitly.
23. **Phase 3 admin `_perform_merge` is `@staticmethod`** so tests can call it without going through the bulk-action wrapper. If you need to add side effects (e.g. notification email) to the merge, do it on the staticmethod, not the bulk-action handler.
24. **Rate-limit offense "once per window" guarantee.** Spam-clicking submit while blocked does NOT escalate further. The `offense_registered` flag on the window-counter cache entry is the load-bearing piece — don't remove it without re-thinking escalation semantics.
25. **`escalates: False` keys still rate-limit normally**, they just never escalate. Use it for endpoints where a single legitimate user can hit the limit during normal use (Library Hunt bursts, etc.). Default is `True`; omit the key to opt in.
26. **`request.bookworm_skip_rate_limit` is a future hook**, nothing sets it today. Don't rely on it being set in any current view. When trust-tier middleware lands, this is where the bypass goes.

---

## Common change recipes

**Adding a new field to `Library`:** edit `models.py`, makemigrations as `0004_library_<field>`, update `LibraryAdmin.fieldsets`/`list_display`, update `LibrarySubmissionForm.Meta.fields`, update `submit_form.html`, update `library_detail.html` and `library_detail_page.html` if user-visible, update `conftest.py` fixtures if non-nullable.

**Adding a new submission endpoint:** add view to `views.py` with `@require_POST` + `@rate_limit('your_key', limit=N, period=P)`, add the limit to `RATE_LIMIT_SETTINGS`, wrap with `check_submission_timing` early-return, form must subclass `HoneypotMixin`, double-check `request.POST.get('website_url')`, return success/error partials with standard paths, add URL to `urls.py`. If user-triggered via HTMX, add the trigger to the relevant partial; if success swap should fire a toast, include `<div class="submission-success" data-message="...">` in the success partial.

**Adding a new template partial:** place in `templates/libraries/partials/`. **Do not** include `<script>` or `<style>` blocks — promote those to the consuming top-level template. Use existing CSS variables.

**Tuning the `/here/` resolver thresholds:** edit the constants near the top of the helpers section in `views.py`. The decision tree is in `here_resolve` and is easy to follow. Add a regression test in `test_phase2_views.py` for any new threshold logic.

---

## Outstanding items / on the horizon

From `DEPLOYMENT_ROADMAP.md`, project memory, and recent strategy work:

- **In progress / next**:
  - Initial content seeding via Django admin (carryover from launch).
  - UptimeRobot monitoring on `/health/` (carryover from launch).
  - HSTS enablement post HTTPS confirmation (carryover from launch).
- **Awaiting**:
  - Neighbourhood Small Grant decision (applied for $500 sticker printing budget).
  - Tier 1 partnership outreach (Pulpfiction, Iron Dog, Massy, Paper Hound, Upstart & Crow, Book Warehouse, Kidsbooks). Tracked in `PARTNERSHIP_OUTREACH.md`.
- **Later**:
  - Trust-tier system for submissions (anon → device-recognized → email-verified → admin-promoted). Phase 3 added the bypass hook; the rest is unwritten.
  - Library Hunt event (date currently in-form as Aug 15, 2026).
  - Sentry error tracking on free tier.
  - Cost monitoring on Neon and Cloudinary free tiers.
  - Tune `DUPLICATE_PROXIMITY_RADIUS_M` after observing `DuplicateCandidate` data in the wild — too few flags means raise the radius, too many false positives means lower it.
  - Tune `RATE_LIMIT_ESCALATION_TIERS` if real abuse patterns suggest a different ladder.

---

## When in doubt

- Schema changes → read `models.py` and the most recent migration first.
- UX/visual changes → read `bookworm.css` (design tokens) and the relevant top-level template — never just the partial.
- Deployment changes → read `Dockerfile` + `start.sh` + the "Things that did not work" section.
- New features touching writes → read `rate_limiting.py` and one existing POST view (`partnership_submit` or `submit_library` are the most complete examples) before writing.
- `/here/` flow changes → read the helpers section in `views.py` (constants + `_log_scan` + `_round_coord`) before touching the resolver.
- Production is live and serves real users at <https://bookworm.guide>. Test locally; deploy via Railway's git push integration.
