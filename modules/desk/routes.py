from flask import Blueprint, render_template, session
from utils.auth import login_required, require_access

desk_bp = Blueprint("desk", __name__)

@desk_bp.route("/workdesk")
@login_required
@require_access("desk", "READ")
def workdesk():
    return render_template("desk/workdesk.html")
