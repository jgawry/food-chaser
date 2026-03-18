from flask import Blueprint

main_bp = Blueprint("main", __name__)

from . import main
from .deals import deals_bp
from .auth import auth_bp
from .grocery import grocery_bp

__all__ = ["main_bp", "deals_bp", "auth_bp", "grocery_bp"]
