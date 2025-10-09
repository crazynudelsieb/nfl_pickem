from flask import Blueprint

bp = Blueprint("api", __name__)

from app.routes.api import routes  # noqa: F401, E402 - imported for route registration
