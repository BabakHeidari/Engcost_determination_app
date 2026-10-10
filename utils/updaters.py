import pandas as pd
from utils.paths import parent_path, material_path
from pathlib import Path
import json
from typing import Union, Optional
from flask import session, jsonify
from datetime import datetime, date, time
import os
from shutil import copy2
from utils.xlsxTojson import xlsx_to_json_convertor, to_json
from utils.load_data import load_json
from utils.product_catalog import build_product_hierarchy, product_catalog_document


def modify_summery(factory):
    file_path = Path(parent_path) / "Factories" / factory / "Factory_Data.xlsx"
    data_list = list()
    all_sheets = pd.read_excel(file_path, sheet_name=None)
    sheet_names = list(all_sheets.keys())
    selling_share, summery_sheet = sheet_names.pop(-2), sheet_names.pop()

    for i, subfield in enumerate(sheet_names):
        subfield_sheet = all_sheets[subfield]
        row = [subfield, sum(subfield_sheet['cost']), None]
        data_list.append(row)
    all_sheets[summery_sheet] = pd.DataFrame(data=data_list, columns=["Subfield", "Cost", "PercentageOfAll"])
    all_sheets[summery_sheet]["PercentageOfAll"] = (all_sheets[summery_sheet]["Cost"]/sum(all_sheets[summery_sheet]["Cost"]))*100

    with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        all_sheets[summery_sheet].to_excel(writer, sheet_name=summery_sheet, index=False)
    
    # file_path_str = str(file_path)
    xlsx_to_json_convertor(excel_path=str(file_path), if_sheet=True, sheet_name="Summery")
    return all_sheets[summery_sheet]


# modify_summery(factory='HajAmini')


def json_to_excel_converter(
    json_path: Union[str, Path], 
    output_path: Optional[Union[str, Path]] = None,
    sheet_name: str = "Sheet1",
    update_only: bool = True
) -> str:
    """
    Convert a JSON file to Excel, optionally updating only a specific sheet.
    
    Args:
        json_path: Path to the input JSON file
        output_path: Path for the output Excel file (optional)
        sheet_name: Name of the Excel sheet to update/create (default: "Sheet1")
        update_only: If True, update only the specified sheet; if False, create new file
    
    Returns:
        Path to the Excel file
    """
    json_path = Path(json_path)
    
    # Read JSON file
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract data
    columns = data.get('_order', [])
    values_dict = data.get('data', {})
    date_string = data.get('last_modification_date', [])

    date_string_clean = date_string.replace('Z', '+00:00')
    date_obj = datetime.fromisoformat(date_string_clean)

    modified_datetime = [date(date_obj.year, date_obj.month,  date_obj.day), 
                         time(date_obj.hour, date_obj.minute,  date_obj.second)]
    
    if not columns or not values_dict or not modified_datetime:
        raise ValueError("JSON file missing '_order' or 'data' keys or 'last_modification_date'.")
    
    # Create DataFrame
    # df = pd.read_excel(output_path, sheet_name=sheet_name)
    # df = pd.DataFrame()
    # for col in columns:
    #     if col in values_dict:
    #         df[col] = values_dict[col]
    #     else:
    #         print(f"Warning: Column '{col}' not found in data")
    #         df[col] = []
    df = pd.DataFrame(values_dict)
    
    # Determine output path
    if output_path is None:
        output_path = json_path.parent / f"{json_path.stem}.xlsx"
    else:
        output_path = Path(output_path)
    
    # Save/Update Excel file
    if update_only and output_path.exists():
        # Update only the specified sheet in existing file
        with pd.ExcelWriter(output_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"✅ Updated sheet '{sheet_name}' in: {output_path.name}")
    else:
        # Create new file or overwrite entire file
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"✅ Created new file with sheet '{sheet_name}': {output_path.name}")
    
    return str(output_path)

def batch_json_to_excel(
    input_dir: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    pattern: str = "*.json"
) -> list:
    """
    Convert multiple JSON files in a directory to Excel files.
    
    Args:
        input_dir: Directory containing JSON files
        output_dir: Directory to save Excel files (optional, uses same as input)
        pattern: File pattern to match (default: "*.json")
    
    Returns:
        List of created Excel file paths
    """
    input_dir = Path(input_dir)
    
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    json_files = list(input_dir.glob(pattern))
    
    if not json_files:
        print(f"No JSON files found matching '{pattern}' in {input_dir}")
        return []
    
    excel_files = []
    for json_file in json_files:
        if output_dir:
            output_path = output_dir / f"{json_file.stem}.xlsx"
        else:
            output_path = None
        
        excel_path = json_to_excel_converter(json_file, output_path)
        excel_files.append(excel_path)
    
    print(f"\n✅ Converted {len(excel_files)} file(s)")
    return excel_files


def save_json_and_excel(module:str, saving_file:str):
    if module == 'factory':
        if saving_file == "factory":
            saving_path = session.get("facs_path")
        elif saving_file == "factory_details":
            saving_path = session.get("fac_path")
        elif saving_file == "subfield":
            print(session.items())
            saving_path = session.get("sub_path")
        else:
            return jsonify({"error": f"Invalid saving_file: {saving_file}"}), 400
    
        
# json_path = "B:\Courses\Maktabkhooneh\Python-Bigdeli\Web_App\cost_determination_app\Data\Overall\material_costs.json"
# json_path = Path(json_path)

# # Read JSON file
# with open(json_path, 'r', encoding='utf-8') as f:
#     data = json.load(f)

# # Extract data
# from datetime import datetime, date, time

# columns = data.get('_order', [])
# values_dict = data.get('data', {})
# date_string = data.get('last_modification_date', [])

# date_string_clean = date_string.replace('Z', '+00:00')
# date_obj = datetime.fromisoformat(date_string_clean)

# modified_date = date(date_obj.year, date_obj.month,  date_obj.day)
# modified_time = time(date_obj.hour, date_obj.minute,  date_obj.second)

# print(f"Day is: {modified_date}\nand time is: {modified_time}")

# print(modification_date)





def product_adder(product_name, factory, category, subcategory):
    file_path = f"{parent_path}\\Factories\\{factory}\\{category}\\{subcategory}"
    template_path = f"{parent_path}\\Overall\\sample_product.json"
    # os.makedirs(file_path, exist_ok=True)
    copy2(template_path, file_path+f"\\{product_name}.json")

def category_adder(factory, category_name):
    file_path = f"{parent_path}\\Factories\\{factory}\\{category_name}"
    os.makedirs(file_path, exist_ok=True)

def subcategory_adder(factory, category_name, subcategory_name):
    file_path = f"{parent_path}\\Factories\\{factory}\\{category_name}\\{subcategory_name}"
    os.makedirs(file_path, exist_ok=True)

def category_weights_updater(factory, category):
    file_path = Path(parent_path) / "Factories" / factory / "category_weights.json"
    category_weights = load_json(file_path)
    if category not in category_weights['data']["category"]:
        category_weights['data']["category"].append(category)
        category_weights['data']["selling_share_of_category"].append(0)
        to_json(file_path, category_weights)







def directory_tracer(root_path, output_metadata=True, return_data=True, verbose=False, factory_keys=None):
    """Build product hierarchy metadata from semantic product namespaces."""
    root_path = Path(root_path).resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(f"Directory does not exist: {root_path}")
    structure = build_product_hierarchy(root_path, factory_keys)
    level1 = list(structure)
    level2 = [category for categories in structure.values() for category in categories]
    level3 = [subcategory for categories in structure.values() for children in categories.values() for subcategory in children]
    parents = {factory: root_path.name for factory in structure}
    for factory, categories in structure.items():
        for category, subcategories in categories.items():
            parents[category] = factory
            parents.update({subcategory: category for subcategory in subcategories})
    metadata = {
        "root_directory": str(root_path), "analysis_date": datetime.now().isoformat(),
        "product_hierarchy": structure,
        "folders_by_level": {"level_1": sorted(level1), "level_2": sorted(level2), "level_3": sorted(level3)},
        "parent_relationships": parents,
        "statistics": {"total_folders": len(level1) + len(level2) + len(level3),
                       "level1_count": len(level1), "level2_count": len(level2), "level3_count": len(level3)},
    }
    metadata_file = root_path / "__metadata.json" if output_metadata else None
    if metadata_file:
        metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if verbose:
        print(f"Product hierarchy contains {len(level1)} factories and excludes system namespaces.")
    if return_data:
        return {"structure": structure, "level1": level1, "level2": level2, "level3": level3,
                "parents": parents, "metadata": metadata,
                "metadata_file": str(metadata_file) if metadata_file else None}
    return None


# Alternative: Direct function that produces exactly the format you showed
def create_product_metadata(parent_path, output_path, factories_folder="Factories",
                            file_extension=".json", verbose=False, factory_keys=None):
    """Regenerate ProductsLater using canonical semantic product discovery."""
    factories_dir = Path(parent_path) / factories_folder
    if not factories_dir.is_dir():
        raise FileNotFoundError(f"Directory not found: {factories_dir}")
    result = product_catalog_document(factories_dir, factory_keys)
    Path(f"{output_path}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if verbose:
        print(f"Saved {len(result['Product_Name'])} products to {output_path}.json")
    return result


def capacity_reader(prd_name, rel_path):
    capacity = load_json(f"{parent_path}\\Factories\\{rel_path}\\{prd_name}_meta.json")
    capacity = capacity["capacity"]
    return capacity

def capacity_writer(product_name, factory, category, subcategory, capacity):
    data = {"capacity": capacity}
    file_path = f"{parent_path}\\Factories\\{factory}\\{category}\\{subcategory}\\{product_name}_meta.json"
    to_json(file_path, data)

#__________________________________________________________________#
##################------------MATERILAS-----------##################
#__________________________________________________________________#

def material_data_updater(updating_payload):
    added_materials = updating_payload["added"]
    modified_materials = updating_payload["edited"]
    deleted_materials = updating_payload["deleted"]
    modification_date = updating_payload["last_modification_date"]

    __material_history_updater(added_materials, modified_materials, modification_date)
    __current_material_updater(added_materials, modified_materials, deleted_materials, modification_date)

    pass

# added_materials = load_json(material_path+'.json')
# modified_materials = load_json(material_path+'.json')
# deleted_materials = load_json(material_path+'.json')

# print(updating_payload)
def __material_history_updater(added_materials, modified_materials, modification_date):
    data = load_json(material_path+"_history.json")
    # for material in added_materials:
    #     material["modification_date"] = modification_date
    #     for key in list(data['data'].keys()):
    #         data['data'][key].append(material[key])
    
    data["data"] = __process_material_list(data["data"], added_materials, modification_date)
    # for material in modified_materials:
    #     material["modification_date"] = modification_date
    #     for key in list(data['data'].keys()):
    #         data['data'][key].append(material[key])
    data["data"] = __process_material_list(data["data"], added_materials, modification_date)
    to_json(material_path+"_history.json", data)
# __material_history_updater(added_materials, modified_materials)

def __current_material_updater(added_materials, modified_materials, deleted_materials, modification_date):
    data = load_json(material_path+".json")

    #added materials
    # for material in added_materials:
    #     for key in list(data['data'].keys()):
    #         data['data'][key].append(material[key])
    data["data"] = __process_material_list(data["data"], added_materials, modification_date)
    # print(f"Added materials, are added to the current file:\n {data}")

    #edited materials
    data["data"] = __update_multiple_materials(data["data"], modified_materials)
    # print(f"Modified materials, are modified to the current file:\n {data}")

    #deleted materials
    for material_index in deleted_materials:
        for key in list(data['data'].keys()):
            del data['data'][key][material_index]
    # print(f"Deleted materials, are deleted to the current file:\n {data}")

    

    data["last_modification_date"] = modification_date

    # print("__current_material_updater worked completely.")

    to_json(material_path+".json", data)

def __process_material_list(data, materials, modification_date):
    for material in materials:
        material["modification_date"] = modification_date
        for key in list(data.keys()):
            data[key].append(material[key])
    return data

def __update_multiple_materials(data, updates):
    """
    Update multiple rows
    updates: list of dicts with 'index' and values to update
    """
    for update in updates:
        index = update['_originalIndex']
        for key in list(data.keys()):
            if key in update:
                data[key][index] = update[key]
    # print("__update_multiple_materials worked completely.")
    return data

# __current_material_updater(added_materials, modified_materials, deleted_materials)

def product_cost_recalculation(material_name:str, product_name:str):
    pass
