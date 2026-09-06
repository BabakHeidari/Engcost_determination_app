from flask import Blueprint, g, render_template

from utils.auth import get_profile_store, login_required
from utils.profile_store import ProfileStoreError
from utils.profile_view import build_profile_view_model


profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile/profile")
@login_required
def profile():
    try:
        profile_view = build_profile_view_model(get_profile_store(), g.current_user)
    except ProfileStoreError:
        return render_template("profile/profile_error.html"), 503
    return render_template("profile/profile.html", profile=profile_view)
