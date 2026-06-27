from flask import Blueprint, render_template, jsonify, request, session
from utils.auth import login_required
from utils.paths import factories_path, parent_path, product_path
from utils.load_data import load_category_weights_of_costs, load_json, load_factory_summery, load_factory_subfield
from utils.updaters import json_to_excel_converter, modify_summery
from utils.xlsxTojson import to_json
import json



factory_parameters_bp = Blueprint("factory_parameters", __name__)

@factory_parameters_bp.route("/factory_parameters/", methods=["POST", "GET"])
@login_required
def factory_parameters():
    facs_path = factories_path + ".json"
    session["facs_path"] = facs_path
    data = load_json(facs_path)
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


@factory_parameters_bp.route("/factory_parameters/<factory_name>", methods=["POST"])
@login_required
def factory_details(factory_name):
    factory = request.form["factory name"]
    session["factory_name"] = factory
    factory_json, fac_path = load_factory_summery(factory)
    session["fac_path"] = fac_path.replace(".json", "")
    category_table = load_category_weights_of_costs(factory)
    predicted_production = product_lister(factory)
    return render_template("/factory_parameters/factory_details.html", 
                           table_json = factory_json, 
                           factory_name = factory, 
                           category_table = category_table,
                           preditcionOfProductionPerCapitaData = predicted_production)

@factory_parameters_bp.route('/save_factories', methods=['POST'])
def save_factories():
    data = request.get_json()
    factory_name = session.get("factory_name")
    file_path = f'{parent_path}\\Factories\\{factory_name}\\Factory_Data.json'
    to_json(file_path, data)
    return jsonify({"status": "success"})

@factory_parameters_bp.route('/save_category_table', methods=['POST'])
def save_category_table():
    data = request.get_json()
    factory_name = session.get("factory_name")
    file_path = f'{parent_path}\\Factories\\{factory_name}\\category_weights.json'
    to_json(file_path, data)
    return jsonify({"status": "success"})

@factory_parameters_bp.route('/save_factory_subfields', methods=['POST'])
def save_factory_subfields():
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
    factory_name = session.get("factory_name")
    Subfield = request.form["Subfield"]
    subfield_json, sub_path = load_factory_subfield(factory_name, Subfield)
    session["sub_path"], session["subfield"] = sub_path.replace(".json", ""), Subfield
    # print(subfield_json)
    return render_template("/factory_parameters/factory_subfield.html", 
                           table_json = subfield_json, factory_name = factory_name,
                            Subfield=Subfield)

@factory_parameters_bp.route("/save_prediction_production_per_capita", methods=["POST"])
@login_required
def save_prediction_production_per_capita():
    factory_name = session.get("factory_name")
    data = request.get_json()
    file_path = f'{parent_path}\\Factories\\{factory_name}\\ProductionPrediction.json'
    to_json(file_path, data)
    return jsonify({"status": "success"})

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