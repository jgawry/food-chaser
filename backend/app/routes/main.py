from flask import jsonify
from . import main_bp


@main_bp.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})
