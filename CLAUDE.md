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

## Planned Features (not yet built)
- Scraper for grocery store leaflets (PDF or web-based)
- Product/deal data extraction and normalization
- User-defined list of tracked grocery items
- Deal comparison across stores
- Possibly a simple notification system for new deals
