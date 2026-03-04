import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from .routes import main_bp, deals_bp
from .db import init_db

_FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend'))


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    CORS(app)

    init_db(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(deals_bp)

    @app.route('/')
    def index():
        return send_from_directory(_FRONTEND_DIR, 'index.html')

    @app.route('/<path:filename>')
    def frontend_static(filename):
        return send_from_directory(_FRONTEND_DIR, filename)

    return app
