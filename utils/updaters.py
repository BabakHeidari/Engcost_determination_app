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







def directory_tracer(root_path, output_metadata=True, return_data=True, verbose=False):
    """
    Analyzes directory structure and creates metadata JSON with hierarchy.
    
    This function traverses the directory structure and provides:
    - First, second, and third level folders separately
    - Parent relationships for each folder
    - JSON metadata file with complete hierarchy
    
    Args:
        root_path (str): Root directory path to analyze
        output_metadata (bool): Whether to save __metadata.json file (default: True)
        return_data (bool): Whether to return the metadata dictionary (default: True)
        verbose (bool): Whether to print analysis summary (default: False)
    
    Returns:
        dict: Dictionary containing:
            - structure: Hierarchical directory structure
            - level1: List of first level folders
            - level2: List of second level folders  
            - level3: List of third level folders
            - parents: Parent relationships dictionary
            - metadata_file: Path to saved metadata file (if output_metadata=True)
    """
    
    root_path = Path(root_path).resolve()
    
    # Validate root path
    if not root_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {root_path}")
    
    if not root_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root_path}")
    
    # Initialize data structures
    structure = {}
    level1_folders = []
    level2_folders = []
    level3_folders = []
    folder_parents = {}
    
    # Traverse directory structure
    for item in sorted(root_path.iterdir()):
        if item.is_dir():
            # Level 1
            level1_folders.append(item.name)
            structure[item.name] = {}
            folder_parents[item.name] = root_path.name
            
            # Level 2
            for subitem in sorted(item.iterdir()):
                if subitem.is_dir():
                    level2_folders.append(subitem.name)
                    structure[item.name][subitem.name] = []
                    folder_parents[subitem.name] = item.name
                    
                    # Level 3
                    for subsubitem in sorted(subitem.iterdir()):
                        if subsubitem.is_dir():
                            level3_folders.append(subsubitem.name)
                            structure[item.name][subitem.name].append(subsubitem.name)
                            folder_parents[subsubitem.name] = subitem.name
    
    # Prepare metadata
    metadata = {
        "root_directory": str(root_path),
        "analysis_date": datetime.now().isoformat(),
        "product_hierarchy": structure,
        "folders_by_level": {
            "level_1": sorted(level1_folders),
            "level_2": sorted(level2_folders),
            "level_3": sorted(level3_folders)
        },
        "parent_relationships": folder_parents,
        "statistics": {
            "total_folders": len(level1_folders) + len(level2_folders) + len(level3_folders),
            "level1_count": len(level1_folders),
            "level2_count": len(level2_folders),
            "level3_count": len(level3_folders)
        }
    }
    
    # Save metadata to JSON file
    metadata_file = None
    if output_metadata:
        metadata_file = root_path / "__metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        if verbose:
            print(f"✓ Metadata saved to: {metadata_file}")
    
    # Display summary if verbose
    if verbose:
        print("\n" + "="*60)
        print("DIRECTORY STRUCTURE ANALYSIS")
        print("="*60)
        print(f"\n📁 Root Directory: {root_path}")
        print(f"\n📊 Statistics:")
        print(f"   Total folders: {metadata['statistics']['total_folders']}")
        print(f"   Level 1 folders: {metadata['statistics']['level1_count']}")
        print(f"   Level 2 folders: {metadata['statistics']['level2_count']}")
        print(f"   Level 3 folders: {metadata['statistics']['level3_count']}")
        
        print("\n📁 First Level Folders:")
        for folder in metadata["folders_by_level"]["level_1"]:
            print(f"   ├── {folder}")
        
        if metadata["folders_by_level"]["level_2"]:
            print("\n📁 Second Level Folders (with parents):")
            for folder in metadata["folders_by_level"]["level_2"]:
                parent = folder_parents.get(folder, "Unknown")
                print(f"   ├── {folder} → parent: {parent}")
        
        if metadata["folders_by_level"]["level_3"]:
            print("\n📁 Third Level Folders (with parents):")
            for folder in metadata["folders_by_level"]["level_3"]:
                parent = folder_parents.get(folder, "Unknown")
                print(f"   ├── {folder} → parent: {parent}")
        
        print("\n" + "="*60)
        print("HIERARCHY VIEW:")
        print("="*60)
        
        for parent, children in structure.items():
            print(f"\n📂 {parent}/")
            if isinstance(children, dict):
                for idx, (child, grandchildren) in enumerate(children.items()):
                    is_last = idx == len(children) - 1
                    prefix = "   └──" if is_last else "   ├──"
                    print(f"{prefix} 📁 {child}/")
                    
                    if grandchildren:
                        for idx2, grandchild in enumerate(grandchildren):
                            is_last_child = idx2 == len(grandchildren) - 1
                            child_prefix = "       └──" if is_last_child else "       ├──"
                            print(f"{child_prefix} 📁 {grandchild}/")
        
        print("="*60 + "\n")
    
    # Return data if requested
    if return_data:
        result = {
            "structure": structure,
            "level1": level1_folders,
            "level2": level2_folders,
            "level3": level3_folders,
            "parents": folder_parents,
            "metadata": metadata,
            "metadata_file": str(metadata_file) if metadata_file else None
        }
        return result
    
    print("directory_tracer done its job.")
    return None


# Alternative: Direct function that produces exactly the format you showed
def create_product_metadata(parent_path, output_path, 
                                            factories_folder="Factories", 
                                            file_extension=".json",
                                            verbose=False):
    """
    Creates product metadata in column-oriented JSON format.
    """
    import json
    from pathlib import Path
    import os
    
    parent_path = Path(parent_path)
    output_path = Path(output_path)
    factories_dir = parent_path / factories_folder
    
    if not factories_dir.exists():
        raise FileNotFoundError(f"Directory not found: {factories_dir}")
    
    # Collect data
    products = []
    factories = []
    categories = []
    subcategories = []
    capacities = []
    
    for root, dirs, files in os.walk(factories_dir):
        for file in files:
            if file.endswith(file_extension):
                rel_path = Path(root).relative_to(factories_dir)
                depth = len(rel_path.parts) if rel_path != Path('.') else 0
                
                if depth == 3 and not file.replace(".json", "").endswith("_meta"):

                    path_parts = Path(root).parts
                    
                    try:
                        factories_idx = path_parts.index(factories_folder)
                    except ValueError:
                        factories_idx = -1
                    
                    product_name = file.replace(file_extension, "")
                    factory_name = path_parts[factories_idx + 1] if factories_idx >= 0 and len(path_parts) > factories_idx + 1 else ""
                    category_name = path_parts[factories_idx + 2] if factories_idx >= 0 and len(path_parts) > factories_idx + 2 else ""
                    subcategory_name = path_parts[factories_idx + 3] if factories_idx >= 0 and len(path_parts) > factories_idx + 3 else ""
                    # print(rel_path, file)
                    # try:
                    capacity = capacity_reader(file.replace(".json", ""), rel_path)
                    # except:
                        # capacity_writer(product_name, factory_name, category_name, subcategory_name, 50)
                        # capacity = capacity_reader(file.replace(".json", ""), rel_path)



                    products.append(product_name)
                    factories.append(factory_name)
                    categories.append(category_name)
                    subcategories.append(subcategory_name)
                    capacities.append(capacity)
                    
                    if verbose:
                        print(f"✓ Added: {product_name} -> {factory_name}/{category_name}/{subcategory_name} with capacity {capacity}.")
    
    # Create column-oriented structure
    column_oriented_data = {
        "Product_Name": {str(i): products[i] for i in range(len(products))},
        "Factory": {str(i): factories[i] for i in range(len(factories))},
        "Category": {str(i): categories[i] for i in range(len(categories))},
        "Subcategory": {str(i): subcategories[i] for i in range(len(subcategories))},
        "Capacity": {str(i): capacities[i] for i in range(len(capacities))}
    }
    
    # Save to JSON
    json_path = f"{output_path}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(column_oriented_data, f, indent=2, ensure_ascii=False)
    
    if verbose:
        print(f"\n✓ Saved column-oriented metadata to: {json_path}")
        print(f"   Total products: {len(products)}")
    
    return column_oriented_data


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