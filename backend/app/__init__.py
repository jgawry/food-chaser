import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from .extensions import limiter
from .routes import main_bp, deals_bp, grocery_bp
from .db import init_db

_FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend'))


def create_app(instance_path=None):
    kwargs = dict(instance_relative_config=True)
    if instance_path:
        kwargs["instance_path"] = instance_path
    app = Flask(__name__, **kwargs)
    CORS(app)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-insecure")
    app.config["APP_BASE_URL"] = os.environ.get("APP_BASE_URL", "http://localhost:5000")
    app.config["IMAGES_DIR"] = os.path.join(app.instance_path, "images")

    limiter.init_app(app)
    init_db(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(deals_bp)
    app.register_blueprint(grocery_bp)

    from .routes import auth_bp
    app.register_blueprint(auth_bp)

    @app.route('/')
    def index():
        return send_from_directory(_FRONTEND_DIR, 'index.html')

    @app.route('/<path:filename>')
    def frontend_static(filename):
        return send_from_directory(_FRONTEND_DIR, filename)

    return app
