from flask import Flask, redirect, url_for, session
# from functools import wraps
from modules.auth.routes import auth_bp
from modules.desk.routes import desk_bp
from modules.product.routes import product_bp
from modules.dashboard.routes import dashboard_bp
from modules.general_parameters.routes import general_parameters_bp
from modules.factory_parameters.routes import factory_parameters_bp
from modules.cost_calculation.routes import cost_calculation_bp
from modules.profile.routes import profile_bp
import secrets
from utils.localization import DEFAULT_DIRECTION, DEFAULT_LANGUAGE, DEFAULT_LOCALE, t


app = Flask(__name__)
# app.secret_key = secrets.token_hex()
app.secret_key = "WILL BE CHANGED TO UPPER"


# register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(desk_bp)
app.register_blueprint(product_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(general_parameters_bp)
app.register_blueprint(factory_parameters_bp)
app.register_blueprint(cost_calculation_bp, url_prefix="/cost")
app.register_blueprint(profile_bp)

@app.context_processor
def inject_user():
    try:
        user = session.get("user").capitalize()
    except:
        user = None
    return {
        "user": user,
        "app_language": DEFAULT_LANGUAGE,
        "app_locale": DEFAULT_LOCALE,
        "app_direction": DEFAULT_DIRECTION,
        "t": t,
    }

@app.route("/")
def home():
    return redirect(url_for("login"))
    

if __name__ == "__main__":
    app.run(debug=True)



# from flask import Flask, render_template, request, redirect, url_for, session, flash
# from functools import wraps


# app = Flask(__name__)
# app.secret_key = "super_secret_key_change_this"


# def login_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):

#         if "user" not in session:
#             return redirect(url_for("login"))

#         return f(*args, **kwargs)

#     return decorated_function


# @app.route("/")
# def home():
#     return redirect(url_for("login"))


# @app.route("/login", methods=["GET","POST"])
# def login():

#     if request.method == "POST":

#         username = request.form.get("username")
#         password = request.form.get("password")

#         if username == "admin" and password == "admin":

#             session["user"] = username
#             return redirect(url_for("workdesk"))

#         flash("Invalid username or password","danger")

#     return render_template("auth/login.html")


# @app.route("/workdesk")
# @login_required
# def workdesk():

#     if "user" not in session:
#         return redirect(url_for("login"))

#     return render_template("desk/workdesk.html")


# @app.route('/product')
# @login_required
# def product():
#     return render_template('product/configuration.html')

# @app.route('/parameter')
# @login_required
# def parameter():
#     return render_template('parameter/tuning.html')

# @app.route('/dashboard')
# @login_required
# def dashboard():
#     return render_template('dashboard/dashboard.html')

# @app.route('/cost')
# @login_required
# def cost():
#     return render_template('cost/calculation.html')

# @app.route('/profile')
# @login_required
# def profile():
#     return render_template('profile/profile.html')

# @app.route("/logout")
# def logout():

#     session.clear()
#     return redirect(url_for("login"))

# if __name__ == '__main__':
#     app.run(debug=True)
