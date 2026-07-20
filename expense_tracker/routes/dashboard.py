"""Dashboard blueprint.

Stub only: renders the shell page so the template and static-asset wiring can be
verified end to end. Real expense listing and aggregation come later.
"""

from flask import Blueprint, render_template

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index() -> str:
    """Render the dashboard shell."""
    return render_template("index.html")
