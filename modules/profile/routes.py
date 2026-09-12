from io import BytesIO

from flask import Blueprint, g, jsonify, render_template, request, send_file

from utils.auth import get_profile_store, login_required, require_access, require_top_level_admin
from utils.profile_factories import prepare_new_factory
from utils.profile_excel import profile_exchange_bytes
from utils.profile_store import ProfileDataConflictError, ProfileDataValidationError, ProfileStoreError
from utils.profile_users import prepare_new_user, prepare_password_reset, prepare_user_update
from utils.profile_view import build_profile_view_model


profile_bp = Blueprint("profile", __name__)


@profile_bp.get("/api/profile/export.xlsx")
@login_required
@require_top_level_admin
def export_profile_excel():
    """Download a read-only administrative snapshot; Excel is never authoritative."""
    try:
        payload = profile_exchange_bytes(get_profile_store())
    except (ProfileStoreError, OSError):
        return jsonify({"ok": False, "message": "تهیه خروجی اکسل امکان‌پذیر نشد."}), 503
    return send_file(
        BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="profile-administration-export.xlsx",
    )


@profile_bp.route("/profile/profile")
@login_required
@require_access("profile", "READ")
def profile():
    try:
        profile_view = build_profile_view_model(get_profile_store(), g.current_user)
    except ProfileStoreError:
        return render_template("profile/profile_error.html"), 503
    return render_template("profile/profile.html", profile=profile_view)


@profile_bp.post("/api/profile/users")
@login_required
@require_top_level_admin
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


@profile_bp.patch("/api/profile/users/<user_id>")
@login_required
@require_top_level_admin
def edit_user(user_id):
    try:
        changes, revision = prepare_user_update(request.get_json(silent=True))
        user = get_profile_store().update_user_as_actor(g.current_user["id"], user_id, changes, revision)
    except ProfileDataConflictError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 409
    except ProfileDataValidationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except ProfileStoreError:
        return jsonify({"ok": False, "message": "ویرایش کاربر امکان‌پذیر نشد."}), 503
    return jsonify({"ok": True, "user": user})


@profile_bp.post("/api/profile/users/<user_id>/password-reset")
@login_required
@require_top_level_admin
def reset_user_password(user_id):
    try:
        password_hash, revision = prepare_password_reset(request.get_json(silent=True))
        user = get_profile_store().reset_password_as_actor(g.current_user["id"], user_id, password_hash, revision)
    except ProfileDataConflictError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 409
    except ProfileDataValidationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except ProfileStoreError:
        return jsonify({"ok": False, "message": "بازنشانی گذرواژه امکان‌پذیر نشد."}), 503
    return jsonify({"ok": True, "user": user})


@profile_bp.post("/api/profile/factories")
@login_required
@require_top_level_admin
def create_factory():
    try:
        candidate = prepare_new_factory(request.get_json(silent=True))
        factory = get_profile_store().create_factory_as_actor(g.current_user["id"], candidate)
    except ProfileDataConflictError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 409
    except ProfileDataValidationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except (ProfileStoreError, OSError):
        return jsonify({"ok": False, "message": "ذخیره کارخانه امکان‌پذیر نشد."}), 503
    return jsonify({"ok": True, "factory": factory}), 201
