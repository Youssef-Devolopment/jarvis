from flask import Blueprint, render_template

from config import VERSION

bp = Blueprint("views", __name__)


@bp.get("/")
def index():
    # version feeds the static-asset cache buster (?v=) so an upgrade
    # always loads fresh CSS/JS without a manual hard-refresh.
    return render_template("index.html", version=VERSION)
