from flask import Blueprint, render_template, jsonify, request
from utils.auth import login_required, require_access
from utils.paths import material_path
from utils.load_data import load_json
from utils.updaters import material_data_updater

general_parameters_bp = Blueprint("general_parameters", __name__)

@general_parameters_bp.route("/general_parameters/")
@login_required
@require_access("general_parameters", "READ")
def general_parameters():
    # Use the same explicit UTF-8 reader as BOM and the material updater.
    data = load_json(material_path + ".json")
    return render_template("general_parameters/general_parameters.html",table_json = data)


@general_parameters_bp.route("/save_materials", methods=["POST"])
@login_required
@require_access("general_parameters", "MODIFY")
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
