from flask import Blueprint, g, jsonify, render_template, request

from utils.auth import get_profile_store, login_required
from utils.profile_store import ProfileDataConflictError, ProfileDataValidationError, ProfileStoreError
from utils.profile_users import prepare_new_user
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


@profile_bp.post("/api/profile/users")
@login_required
def create_user():
    try:
        candidate = prepare_new_user(request.get_json(silent=True))
        user = get_profile_store().create_user_as_actor(g.current_user["id"], candidate)
    except ProfileDataConflictError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 409
    except ProfileDataValidationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except ProfileStoreError:
        return jsonify({"ok": False, "message": "ذخیره کاربر امکان‌پذیر نشد."}), 503
    except OSError:
        return jsonify({"ok": False, "message": "ذخیره کاربر امکان‌پذیر نشد."}), 503
    return jsonify({"ok": True, "user": user}), 201
