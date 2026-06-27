from flask import Blueprint, render_template, jsonify, request, session
from utils.auth import login_required
from utils.paths import material_path
import json
from utils.updaters import material_data_updater

general_parameters_bp = Blueprint("general_parameters", __name__)

@general_parameters_bp.route("/general_parameters/")
@login_required
def general_parameters():
    with open(material_path+".json", "r") as f:
        data = json.load(f)
    # LOGGED_IN_USER = session.get("user")
    return render_template("general_parameters/general_parameters.html",table_json = data)


@general_parameters_bp.route("/save_materials", methods=["POST"])
def save_materials():
    payload = request.get_json(force=True)

    updating_payload = {
        # "_order": payload["_order"],
        # "data": payload["data"],
        "added": payload["added"],
        "edited": payload["edited"],
        "deleted": payload["deleted"],
        "last_modification_date": payload["last_modification_date"]
    }

    # with open(material_path+".json", "w", encoding="utf-8") as f:
    #     json.dump(final_material, f, ensure_ascii=False, indent=4)
    material_data_updater(updating_payload)

    
    # product_cost_recalculation()

    return jsonify({"status": "ok"})