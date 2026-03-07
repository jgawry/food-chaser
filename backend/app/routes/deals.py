from flask import Blueprint, jsonify, request, current_app, Response

from ..scraper import WEB_SCRAPERS, LEAFLET_SCRAPERS
from ..db import save_deals, get_deals, get_categories
from ..export import generate_deals_pdf
from ..email_report import send_deals_email

deals_bp = Blueprint("deals", __name__)


@deals_bp.route("/api/scrape", methods=["POST"])
def scrape():
    """Scrape Lidl website categories and auto-download the latest leaflet."""
    all_products = []
    errors = []

    # Web scrape
    try:
        for scraper in WEB_SCRAPERS.values():
            all_products.extend(scraper.scrape())
    except Exception as e:
        errors.append(f"web: {e}")

    # Leaflet auto-download
    for store, scraper in LEAFLET_SCRAPERS.items():
        if hasattr(scraper, "scrape_latest"):
            try:
                all_products.extend(scraper.scrape_latest())
            except Exception as e:
                errors.append(f"leaflet ({store}): {e}")

    saved = save_deals(current_app, all_products) if all_products else 0
    result = {"scraped": len(all_products), "saved": saved}
    if errors:
        result["warnings"] = errors
    return jsonify(result)


@deals_bp.route("/api/deals", methods=["GET"])
def list_deals():
    category = request.args.get("category")
    deals = get_deals(current_app, category or None)
    return jsonify({"deals": deals, "count": len(deals)})


@deals_bp.route("/api/deals/categories", methods=["GET"])
def list_categories():
    cats = get_categories(current_app)
    return jsonify({"categories": cats})


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
