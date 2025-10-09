from flask import Blueprint

bp = Blueprint("main", __name__)

from app.routes.main import routes  # noqa: F401, E402 - imported for route registration
