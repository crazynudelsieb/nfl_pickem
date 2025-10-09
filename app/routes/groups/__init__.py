from flask import Blueprint

bp = Blueprint("groups", __name__)

from app.routes.groups import routes  # noqa: F401, E402 - imported for route registration
