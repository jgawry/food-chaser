from flask import Blueprint, jsonify, request, current_app, g

from ..auth_utils import require_auth
from ..db import get_grocery_items, add_grocery_item, update_grocery_item, delete_grocery_item

grocery_bp = Blueprint("grocery", __name__)


@grocery_bp.route("/api/grocery-list", methods=["GET"])
@require_auth
def list_items():
    items = get_grocery_items(current_app, g.current_user_id)
    return jsonify({"items": items})


@grocery_bp.route("/api/grocery-list", methods=["POST"])
@require_auth
def create_item():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    quantity = (data.get("quantity") or "").strip() or None
    item = add_grocery_item(current_app, g.current_user_id, name, quantity)
    return jsonify({"item": item}), 201


@grocery_bp.route("/api/grocery-list/<int:item_id>", methods=["PUT"])
@require_auth
def edit_item(item_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    quantity = (data.get("quantity") or "").strip() or None
    item = update_grocery_item(current_app, item_id, g.current_user_id, name, quantity)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify({"item": item})


@grocery_bp.route("/api/grocery-list/<int:item_id>", methods=["DELETE"])
@require_auth
def remove_item(item_id):
    deleted = delete_grocery_item(current_app, item_id, g.current_user_id)
    if not deleted:
        return jsonify({"error": "Item not found"}), 404
    return jsonify({"deleted": True})
