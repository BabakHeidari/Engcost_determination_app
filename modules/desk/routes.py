from flask import Blueprint, render_template, session
from utils.auth import login_required

desk_bp = Blueprint("desk", __name__)

@desk_bp.route("/workdesk")
@login_required
def workdesk():
    return render_template("desk/workdesk.html")
