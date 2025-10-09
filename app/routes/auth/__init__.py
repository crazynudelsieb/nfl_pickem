from flask import Blueprint

bp = Blueprint("auth", __name__)

from app.routes.auth import routes  # noqa: F401, E402 - imported for route registration
