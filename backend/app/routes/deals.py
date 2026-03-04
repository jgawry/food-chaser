import os

from flask import Blueprint, jsonify, request, current_app, Response

from ..scraper.lidl import scrape_all_categories
from ..scraper.lidl_leaflet import parse_leaflet
from ..db import save_deals, get_deals, get_categories
from ..export import generate_deals_pdf
from ..email_report import send_deals_email

deals_bp = Blueprint("deals", __name__)


@deals_bp.route("/api/scrape", methods=["POST"])
def scrape():
    try:
        products = scrape_all_categories()
        saved = save_deals(current_app, products)
        return jsonify({"scraped": len(products), "saved": saved})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@deals_bp.route("/api/deals", methods=["GET"])
def list_deals():
    category = request.args.get("category")
    deals = get_deals(current_app, category or None)
    return jsonify({"deals": deals, "count": len(deals)})


@deals_bp.route("/api/scrape/leaflet", methods=["POST"])
def scrape_leaflet():
    data = request.get_json(silent=True) or {}
    pdf_path = data.get("pdf_path", "").strip()
    if not pdf_path:
        return jsonify({"error": "pdf_path is required"}), 400
    if not os.path.isfile(pdf_path):
        return jsonify({"error": f"File not found: {pdf_path}"}), 404
    try:
        deals = parse_leaflet(pdf_path)
        saved = save_deals(current_app, deals)
        return jsonify({"parsed": len(deals), "saved": saved})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
