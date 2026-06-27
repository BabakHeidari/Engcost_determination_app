from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from utils.auth import authenticate
from utils.localization import t

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/", methods=["GET","POST"])
@auth_bp.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if authenticate(username, password) == "OK":
            session["user"] = username
            return redirect(url_for("desk.workdesk"))

        flash(t("auth.invalid_credentials"),"danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():

    session.clear()
    return redirect(url_for("auth.login"))
