from functools import wraps
from flask import session, redirect, url_for
import pandas as pd
import hashlib
from utils.paths import parent_path


def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "user" not in session:
            return redirect(url_for("auth.login"))

        return f(*args, **kwargs)

    return decorated_function


def authenticate(username:str, password:str):

    auth_data_path = str(parent_path)+r"\Overall\auth_data"
    auth_data = pd.read_excel(auth_data_path+".xlsx")
    user_data = auth_data[auth_data["username"] == username.lower()]
    # password = password.removeprefix
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

    if user_data.size != 0:
        if user_data["password_hash"].values[0] == password_hash:
            # session["auth"] = "seccess"
            # print(session["auth"])
            # return session
            return "OK"
        else:
            # session["auth"] = "failure"
            # print(session["auth"])
            # return session
            return "NotOK"
    else:
        # session["auth"] = "failure"
        # print(session["auth"])
        # return session
        return "NotOK"

def accounter():
    username = input("Enter the username:\n").lower()
    password = hashlib.sha256(input("Enter the password:\n").encode("utf-8")).hexdigest()
    role = input("What role would you considered for him/her: admin or user\n")
    auth_data_path = str(parent_path)+r"\Overall\auth_data"
    auth_data = pd.read_excel(auth_data_path+".xlsx")
    auth_data.loc[len(auth_data)] = [username, password, role]
    auth_data.to_excel(auth_data_path+".xlsx", index=False)
    return username, password
    
    
# u, p = accounter()
# authenticate(input("username\n"), input("password\n"))