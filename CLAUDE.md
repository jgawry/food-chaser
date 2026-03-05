# Food Chaser

A grocery store leaflet scraper that finds the best deals on items of interest. It scrapes promotional leaflets from grocery stores, extracts product/price data, and lets the user track and compare deals across stores.

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

## Features

### Lidl Web Scraper
- Scrapes Lidl food category pages (`/h/{slug}/{id}`, `/c/{slug}/{id}`)
- Parses `<script id="__NUXT_DATA__">` flat JSON array for product/price data
- POST `/api/scrape` triggers scrape and saves to SQLite DB

### PDF Leaflet Scraper (`backend/app/scraper/lidl_leaflet.py`)
- Parses Lidl promotional leaflet PDFs using `pymupdf`
- Extracts brand, name, qty, price, old price, discount %, promo labels
- Handles two deal types: regular deals and app-coupon ("N+M gratis") deals
- Filters OCR noise using Polish-text patterns
- POST `/api/scrape/leaflet` — body: `{"pdf_path": "/absolute/path/to/leaflet.pdf"}`

### PDF Export (`backend/app/export.py`)
- Generates styled A4 PDF report via `reportlab`, grouped by category
- GET `/api/deals/export/pdf?category=X` — downloads PDF

### Email Reports (`backend/app/email_report.py`)
- Sends deal report as HTML email with PDF attachment via SMTP (Gmail/SSL port 465)
- Credentials: keyring vault (priority) or `.env` (`SMTP_USER` / `SMTP_PASS`)
- Run `python store_credentials.py` once to store credentials in OS keyring
- POST `/api/deals/export/email?category=X` — sends email

### Deal Storage & API
- SQLite DB at `backend/instance/food_chaser.db`; upserts via UNIQUE INDEX on `(product_id, category)`
- GET `/api/deals` — list all deals; `?category=X` to filter
- GET `/api/deals/categories` — list available categories

## Planned Features (not yet built)
- User-defined list of tracked grocery items
- Deal comparison across stores
