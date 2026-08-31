from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from utils.auth import authenticate, get_profile_store, load_current_user, validate_password
from utils.localization import t
from utils.profile_store import ProfileStoreError, ProfileStoreNotInitializedError


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            result = authenticate(request.form.get("username"), request.form.get("password"))
        except ProfileStoreNotInitializedError:
            flash(
                "اطلاعات کاربران هنوز منتقل نشده است. ابتدا دستور مهاجرت درج‌شده در مستندات راه‌اندازی را اجرا کنید.",
                "warning",
            )
            return render_template("auth/login.html"), 503
        except ProfileStoreError:
            flash("سرویس ورود موقتاً در دسترس نیست. لطفاً با مدیر سامانه تماس بگیرید.", "danger")
            return render_template("auth/login.html"), 503
        if result is not None:
            session.clear()
            session["user_id"] = result.user["id"]
            if result.must_change_password:
                return redirect(url_for("auth.change_password"))
            return redirect(url_for("desk.workdesk"))
        flash(t("auth.invalid_credentials"), "danger")
    return render_template("auth/login.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    user = load_current_user()
    if user is None:
        session.clear()
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        password = request.form.get("password")
        confirmation = request.form.get("password_confirmation")
        if password != confirmation:
            flash("گذرواژه و تکرار آن یکسان نیستند.", "danger")
        else:
            try:
                validate_password(password)
            except ValueError as exc:
                flash(str(exc), "danger")
            else:
                get_profile_store().change_password(user["id"], generate_password_hash(password))
                return redirect(url_for("desk.workdesk"))
    return render_template("auth/change_password.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
