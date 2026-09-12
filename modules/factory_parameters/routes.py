from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, session, url_for
from utils.auth import get_profile_store, login_required
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
from utils.paths import parent_path, product_path
from utils.load_data import load_category_weights_of_costs, load_json, load_factory_summery, load_factory_subfield
from utils.updaters import json_to_excel_converter, modify_summery
from utils.xlsxTojson import to_json
import json



factory_parameters_bp = Blueprint("factory_parameters", __name__)

@factory_parameters_bp.route("/factory_parameters/", methods=["POST", "GET"])
@login_required
def factory_parameters():
    factories = FactoryService(get_profile_store()).get_accessible_factories(g.current_user, "factory_parameters")
    if not factories:
        abort(403)
    data = {"_order": ["factory_id", "factory name", "city"], "data": {
        "factory_id": [factory["id"] for factory in factories],
        "factory name": [factory["name"] for factory in factories],
        "city": [factory.get("location") or "" for factory in factories],
    }}
    return render_template("factory_parameters/factories.html", 
                           table_json = data)

# @factory_parameters_bp.route("/save", methods=["POST"])
# def save_params():
#     payload = request.get_json(force=True)
    
#     # Extract saving_file from payload
#     saving_file = payload.get("saving_file")
    
#     if not saving_file:
#         return jsonify({"error": "saving_file not specified in payload"}), 400
    
#     final_data = {
#         "_order": payload["_order"],
#         "data": payload["data"]
#     }
    
#     # Determine saving path based on saving_file
#     if saving_file == "factory":
#         saving_path = factories_path
#     elif saving_file == "factory_details":
#         saving_path = session.get("fac_path")
#     elif saving_file == "subfield":
#         saving_path = session.get("sub_path")
#     else:
#         return jsonify({"error": f"Invalid saving_file: {saving_file}"}), 400
    
#     # Check if saving_path exists
#     if not saving_path:
#         return jsonify({"error": f"Path not found for {saving_file}"}), 400
    
#     # Save the file
#     with open(f"{saving_path}.json", "w", encoding="utf-8") as f:
#         json.dump(final_data, f, ensure_ascii=False, indent=4)

#     if saving_file == "subfield":
#         json_to_excel_converter(f"{saving_path}.json", f"{session.get("fac_path")}.xlsx", sheet_name=session.get("subfield"), update_only=True)
#         modify_summery(session.get("factory_name"))
#     else:
#         json_to_excel_converter(f"{saving_path}.json", f"{saving_path}.xlsx")

#     return jsonify({"status": "ok", "saved_to": saving_path})


@factory_parameters_bp.route("/factory_parameters/<factory_name>", methods=["GET", "POST"])
@login_required
def factory_details(factory_name):
    if request.method == "POST":
        # Preserve compatibility with already-rendered legacy forms while using
        # Post/Redirect/Get so refresh and browser Back never require resubmission.
        return redirect(
            url_for("factory_parameters.factory_details", factory_name=factory_name),
            code=303,
        )
    try:
        factory_record = FactoryService(get_profile_store()).require_access(factory_name, g.current_user, "factory_parameters")
    except FactoryNotFoundError as exc:
        return render_template("factory_parameters/unavailable.html", message=str(exc)), 404
    except (FactoryAccessDeniedError, FactoryInactiveError):
        abort(403)
    factory = FactoryService(get_profile_store()).operational_key(factory_record)
    session["factory_id"] = factory_record["id"]
    session["factory_name"] = factory
    try:
        factory_json, fac_path = load_factory_summery(factory)
        category_table = load_category_weights_of_costs(factory)
        predicted_production = product_lister(factory)
        unconfigured = False
    except (FileNotFoundError, KeyError, ValueError):
        factory_json = {"_order": ["Subfield", "Cost", "PercentageOfAll"], "data": {"Subfield": [], "Cost": [], "PercentageOfAll": []}}
        category_table = {"_order": ["category", "selling_share_of_category"], "data": {"category": [], "selling_share_of_category": []}}
        predicted_production = {"_order": ["Product Name", "Predicted Production"], "data": {"Product Name": [], "Predicted Production": []}}
        fac_path = str(parent_path / "Factories" / factory / "Factory_Data.json")
        unconfigured = True
    session["fac_path"] = fac_path.replace(".json", "")
    return render_template("/factory_parameters/factory_details.html", 
                           table_json = factory_json, 
                           factory_name = factory, 
                           factory_display_name = factory_record["name"],
                           unconfigured = unconfigured,
                           category_table = category_table,
                           preditcionOfProductionPerCapitaData = predicted_production)

@factory_parameters_bp.route('/save_factories', methods=['POST'])
@login_required
def save_factories():
    error = _validate_session_factory("MODIFY")
    if error:
        return error
    data = request.get_json()
    factory_name = session.get("factory_name")
    file_path = f'{parent_path}\\Factories\\{factory_name}\\Factory_Data.json'
    to_json(file_path, data)
    return jsonify({"status": "success"})

@factory_parameters_bp.route('/save_category_table', methods=['POST'])
@login_required
def save_category_table():
    error = _validate_session_factory("MODIFY")
    if error:
        return error
    data = request.get_json()
    factory_name = session.get("factory_name")
    file_path = f'{parent_path}\\Factories\\{factory_name}\\category_weights.json'
    to_json(file_path, data)
    return jsonify({"status": "success"})

@factory_parameters_bp.route('/save_factory_subfields', methods=['POST'])
@login_required
def save_factory_subfields():
    error = _validate_session_factory("MODIFY")
    if error:
        return error
    data = request.get_json()
    factory_name = session.get("factory_name")
    subfield = session.get("subfield")
    file_path_prefix = f'{parent_path}\\Factories\\{factory_name}\\Factory_Data'
    to_json(file_path_prefix+f'_{subfield}.json', data)
    json_to_excel_converter(file_path_prefix+f'_{subfield}.json', 
                            file_path_prefix+f'.xlsx', subfield, True)
    modify_summery(factory_name)
    return jsonify({"status": "success"})

@factory_parameters_bp.route("/factory_parameters/<factory_name>/<Subfield>", methods=["POST", "GET"])
@login_required
def subfield(factory_name, Subfield):
    if request.method == "POST":
        # Old table forms posted the subfield value. Canonicalize that request
        # into a bookmarkable GET URL before rendering any data.
        return redirect(
            url_for(
                "factory_parameters.subfield",
                factory_name=factory_name,
                Subfield=Subfield,
            ),
            code=303,
        )
    try:
        factory_record = FactoryService(get_profile_store()).require_access(factory_name, g.current_user, "factory_parameters")
    except FactoryNotFoundError as exc:
        return render_template("factory_parameters/unavailable.html", message=str(exc)), 404
    except (FactoryAccessDeniedError, FactoryInactiveError):
        abort(403)
    operational_key = FactoryService(get_profile_store()).operational_key(factory_record)
    session["factory_id"] = factory_record["id"]
    session["factory_name"] = operational_key
    try:
        subfield_json, sub_path = load_factory_subfield(operational_key, Subfield)
    except FileNotFoundError:
        return render_template("factory_parameters/unavailable.html", message="پارامترهای این کارخانه هنوز پیکربندی نشده است."), 409
    session["sub_path"], session["subfield"] = sub_path.replace(".json", ""), Subfield
    # print(subfield_json)
    return render_template("/factory_parameters/factory_subfield.html", 
                           table_json = subfield_json, factory_name = factory_name,
                            Subfield=Subfield)

@factory_parameters_bp.route("/save_prediction_production_per_capita", methods=["POST"])
@login_required
def save_prediction_production_per_capita():
    error = _validate_session_factory("MODIFY")
    if error:
        return error
    factory_name = session.get("factory_name")
    data = request.get_json()
    file_path = f'{parent_path}\\Factories\\{factory_name}\\ProductionPrediction.json'
    to_json(file_path, data)
    return jsonify({"status": "success"})


def _validate_session_factory(permission):
    factory_id = session.get("factory_id")
    try:
        factory = FactoryService(get_profile_store()).require_access(factory_id, g.current_user, "factory_parameters", permission)
    except FactoryNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    if session.get("factory_name") != FactoryService(get_profile_store()).operational_key(factory):
        return jsonify({"status": "error", "message": "زمینه کارخانه معتبر نیست."}), 400
    return None

def product_lister(factory_name):
    try:
        file_path = f'{parent_path}\\Factories\\{factory_name}\\ProductionPrediction.json'
        product_dict = load_json(file_path)
    except:
        from pandas import read_json
        product_list = read_json(product_path+".json")
        product_list = list(product_list[product_list["Factory"]==factory_name]["Product_Name"])
        product_dict = {"_order": ["Product Name", "Predicted Production"],
                        "data": 
                        {"Product Name": product_list, 
                        "Predicted Production": [0]*len(product_list)}}
    return product_dict
