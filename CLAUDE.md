# Food Chaser

A grocery store leaflet scraper that finds the best deals on items of interest. It scrapes promotional leaflets from grocery stores, extracts product/price data, and lets the user track and compare deals across stores.

## Branching & Deployment
- Default branch: `develop` — all work goes here
- `develop` auto-deploys to staging (http://34.26.127.50:8080) via GitHub Actions on push
- `master` is production — only merge from `develop` when releasing; do not push directly
- Production deploy is manual: `sudo bash /opt/food-chaser/deploy/deploy.sh production` on the VM

## Dev Commands
- Backend: `cd backend && python run.py` (runs on localhost:5000)
- Frontend: open `frontend/index.html` in browser (no build step)

## Architecture
- **Backend**: Flask REST API — scraping logic, data storage, deal comparison
- **Frontend**: Vanilla HTML/CSS/JS — no framework, no bundler
- All frontend→backend communication goes through `apiFetch()` in [frontend/js/api.js](frontend/js/api.js)
- All API routes are prefixed with `/api/`

## Conventions
- New API routes go in `backend/app/routes/` as separate files, registered in `backend/app/routes/__init__.py`
- Frontend JS is modular: keep scraping/API calls in `api.js`, UI logic in `main.js`, add new modules as needed
- No JS framework — keep it vanilla
- Use `python-dotenv` for all config/secrets via `.env` (see `.env.example`)

## Testing
- Tests live in `backend/tests/`; run with `cd backend && python -m pytest`
- Every new feature or API endpoint must have corresponding tests in `backend/tests/`
- Every bug fix must have a test that reproduces the bug before the fix
- Test files mirror the module they test: `test_auth.py` for auth routes, `test_routes.py` for deal routes, etc.
- Use `conftest.py` fixtures (`client`, `flask_app`) — do not spin up a real server
- Mock all external calls (SMTP, HTTP scrapers) — tests must run offline with no credentials
- CI runs the full test suite before every deploy; a failing test blocks deployment

## Features

### Scraping — POST `/api/scrape`
Runs both sources in one shot; partial failures are returned as `warnings` in the response.

#### Lidl Web Scraper (`backend/app/scraper/lidl.py`)
- Scrapes Lidl food category pages (`/h/{slug}/{id}`, `/c/{slug}/{id}`)
- Parses `<script id="__NUXT_DATA__">` flat JSON array for product/price data

#### Lidl Leaflet Auto-downloader + Parser (`backend/app/scraper/lidl_leaflet.py`)
- Fetches `lidl.pl/c/nasze-gazetki/s10008614`, extracts UUID (`data-track-id`) and title from the first `.flyer` block
- Constructs PDF URL: `https://object.storage.eu01.onstackit.cloud/leaflets/pdfs/{uuid}/{SLUG}-{n}.pdf`; probes HEAD requests for `n` 1–30 to find the right suffix (appears to be page count)
- Downloads PDF to a temp file, parses it with `pymupdf`, then deletes the temp file
- Parses two deal types: regular discounts and app-coupon ("N+M gratis") deals
- Filters OCR noise using Polish-text patterns

### PDF Export (`backend/app/export.py`)
- Generates styled A4 PDF report via `reportlab`, grouped by category
- GET `/api/deals/export/pdf?category=X` — downloads PDF

### Email Reports (`backend/app/email_report.py`)
- Sends deal report as HTML email with PDF attachment via SMTP (Gmail/SSL port 465)
- Credentials resolved in order: GCP Secret Manager → env vars (`SMTP_USER`/`SMTP_PASS`) → OS keyring
- POST `/api/deals/export/email?category=X` — sends email

### Deal Storage & API
- SQLite DB at `backend/instance/food_chaser.db`; upserts via UNIQUE INDEX on `(product_id, category)`
- Stale deal cleanup: scraping with `remove_stale=True` deletes deals from the same source not refreshed in the current batch
- GET `/api/deals` — list all deals; `?category=X` to filter
- GET `/api/deals/categories` — list available categories
- GET `/api/deals/my-list` — deals matching the user's grocery list (requires auth); returns `matched_items` annotation per deal

### Authentication (`backend/app/routes/auth.py`)
- Register with email + password (8+ chars), confirmation email with 24h token
- POST `/api/auth/resend-confirmation` — resend confirmation for unconfirmed accounts (rate limited 3/hr)
- JWT-based login; token stored in `localStorage`

### Custom Grocery Lists (`backend/app/routes/grocery.py`)
- Per-user CRUD: GET/POST/PUT/DELETE on `/api/grocery-list`
- "Show matching deals" button on My List tab fetches and displays deal cards matching grocery items

## Planned Features (not yet built)
1. **HTTPS on production** — enable TLS once a domain is registered (one-line Caddyfile change)
2. **Deal optimization** — for a user's grocery list, summarize the best deals across stores to minimize cost
3. **Additional scrapers** — Makro and Biedronka (currently only Lidl)
4. **Environment config in code** — manage `.env` per environment (dev/staging/prod) in the repo so deployment doesn't require manual VM setup; use GCP Secret Manager for secrets, checked-in config for everything else
