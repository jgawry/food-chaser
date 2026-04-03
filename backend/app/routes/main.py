from flask import jsonify, Response, current_app, send_from_directory
from . import main_bp


@main_bp.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@main_bp.route("/api/placeholder-image", methods=["GET"])
def placeholder_image():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
        '<rect width="200" height="200" fill="#f5f5f5"/>'
        '<rect x="60" y="55" width="80" height="65" rx="4" fill="none" stroke="#d0d0d0" stroke-width="2"/>'
        '<circle cx="82" cy="76" r="8" fill="#d0d0d0"/>'
        '<polyline points="60,105 83,83 103,100 122,78 140,105" fill="none" stroke="#d0d0d0" stroke-width="2"/>'
        '<text x="100" y="148" text-anchor="middle" fill="#bbb" font-size="12" font-family="sans-serif">No image</text>'
        "</svg>"
    )
    return Response(svg, mimetype="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@main_bp.route("/api/images/<path:filename>", methods=["GET"])
def serve_leaflet_image(filename):
    images_dir = current_app.config["IMAGES_DIR"]
    return send_from_directory(images_dir, filename)
