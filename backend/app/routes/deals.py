import os

from flask import Blueprint, jsonify, request, current_app, Response, g

from ..scraper import WEB_SCRAPERS, LEAFLET_SCRAPERS
from ..db import save_deals, get_deals, get_categories, get_deals_for_grocery_list
from ..auth_utils import require_auth
from ..export import generate_deals_pdf
from ..email_report import send_deals_email

deals_bp = Blueprint("deals", __name__)

_KNOWN_STORES = set(WEB_SCRAPERS) | set(LEAFLET_SCRAPERS)


@deals_bp.route("/api/scrape", methods=["POST"])
def scrape():
    """Scrape Lidl website categories and auto-download the latest leaflet."""
    store = request.args.get("store")
    if store and store not in _KNOWN_STORES:
        return jsonify({"error": f"Unknown store: {store}"}), 400

    all_products = []
    errors = []

    web_scrapers = {store: WEB_SCRAPERS[store]} if store else WEB_SCRAPERS
    leaflet_scrapers = {store: LEAFLET_SCRAPERS[store]} if store and store in LEAFLET_SCRAPERS else (LEAFLET_SCRAPERS if not store else {})

    try:
        for scraper in web_scrapers.values():
            all_products.extend(scraper.scrape())
    except Exception as e:
        errors.append(f"web: {e}")

    for store_name, scraper in leaflet_scrapers.items():
        if hasattr(scraper, "scrape_latest"):
            try:
                all_products.extend(scraper.scrape_latest())
            except Exception as e:
                errors.append(f"leaflet ({store_name}): {e}")

    saved = save_deals(current_app, all_products, remove_stale=True) if all_products else 0
    result = {"scraped": len(all_products), "saved": saved}
    if errors:
        result["warnings"] = errors
    return jsonify(result)


@deals_bp.route("/api/scrape/leaflet", methods=["POST"])
def scrape_leaflet():
    """Parse a locally stored leaflet PDF and save deals."""
    data = request.get_json(silent=True) or {}
    pdf_path = data.get("pdf_path")
    store = data.get("store")

    if not pdf_path:
        return jsonify({"error": "pdf_path is required"}), 400
    if not store:
        return jsonify({"error": "store is required"}), 400
    if store not in LEAFLET_SCRAPERS:
        return jsonify({"error": f"Unknown store: {store}"}), 400
    if not os.path.exists(pdf_path):
        return jsonify({"error": f"File not found: {pdf_path}"}), 404

    from ..scraper.lidl_leaflet import parse_leaflet
    deals = parse_leaflet(pdf_path)
    saved = save_deals(current_app, deals) if deals else 0
    return jsonify({"parsed": len(deals), "saved": saved})


@deals_bp.route("/api/deals", methods=["GET"])
def list_deals():
    category = request.args.get("category")
    deals = get_deals(current_app, category or None)
    return jsonify({"deals": deals, "count": len(deals)})


@deals_bp.route("/api/deals/categories", methods=["GET"])
def list_categories():
    cats = get_categories(current_app)
    return jsonify({"categories": cats})


@deals_bp.route("/api/deals/my-list", methods=["GET"])
@require_auth
def deals_for_my_list():
    """Return only deals matching the authenticated user's grocery list."""
    category = request.args.get("category")
    deals = get_deals_for_grocery_list(current_app, g.current_user_id, category or None)
    return jsonify({"deals": deals, "count": len(deals)})


@deals_bp.route("/api/deals/export/pdf", methods=["GET"])
def export_pdf():
    category = request.args.get("category")
    deals = get_deals(current_app, category or None)
    pdf_bytes = generate_deals_pdf(deals)
    filename = f"deals-{category or 'all'}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@deals_bp.route("/api/deals/export/email", methods=["POST"])
def email_pdf():
    category = request.args.get("category")
    deals = get_deals(current_app, category or None)
    pdf_bytes = generate_deals_pdf(deals)
    try:
        send_deals_email(pdf_bytes, category)
        return jsonify({"sent": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
