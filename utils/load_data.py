import json
from pathlib import Path
from utils.paths import parent_path
from utils.xlsxTojson import xlsx_to_json_convertor, to_json
from shutil import copy2
import logging

#### Now it just handles not existed products with sample. it should contain all in the future.

def load_json(file_path:str):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        logging.log(level=5 ,msg=f"Error when loading the json from the path:{file_path}\n{e}")
        raise e
    # except FileNotFoundError:
    #     data = None
    #     raise(FileNotFoundError)
    #     # sample_path = sample_path + ".json"
    #     # with open(sample_path, "r", encoding="utf-8") as f:
    #     #     data = json.load(f)

def load_bom(factory, category, subcategory, product_name):
    recipe_path = Path(parent_path) / "Factories" / factory / category / subcategory / f"{product_name}.json"
    data = load_json(recipe_path)
    return data, recipe_path

def load_factory_summery(factory):
    fmt = ['json', 'xlsx']
    fac_json_path = str(Path(parent_path) / "Factories" / factory / f"Factory_Data.{fmt[0]}")
    fac_xlsx_path = str(Path(parent_path) / "Factories" / factory / f"Factory_Data.{fmt[1]}")
    fac_xlsx_path_template = str(Path(parent_path) / "Overall" / f"Factory_Data_Template.{fmt[1]}")

    try:
        xlsx_to_json_convertor(excel_path=fac_xlsx_path, if_sheet=True, sheet_name='Summery')
        data = load_json(fac_json_path)
    except:
        copy2(fac_xlsx_path_template, fac_xlsx_path)
        xlsx_to_json_convertor(excel_path=fac_xlsx_path, if_sheet=True, sheet_name='Summery')
        data = load_json(fac_json_path)
    return data, fac_json_path

def load_factory_subfield(factory_name:str, subfield:str):
    fmt = ['json', 'xlsx']
    subf_json_path = str(Path(parent_path) / "Factories" / factory_name / f"Factory_Data_{subfield}.{fmt[0]}")
    subf_xlsx_path = str(Path(parent_path) / "Factories" / factory_name / f"Factory_Data.{fmt[1]}")
    xlsx_to_json_convertor(excel_path=subf_xlsx_path, if_sheet=True, sheet_name=subfield, if_subfield=True)
    data = load_json(subf_json_path)
    return data, subf_json_path

def load_category_weights_of_costs(factory):
    file_path = f"{parent_path}\\Factories\\{factory}\\category_weights.json"
    try:
        data = load_json(file_path)
    except:
        template_path = f"{parent_path}\\Overall\\category_table_sample.json"
        copy2(template_path, file_path)
        data = load_json(file_path)
        fat_cats = load_json(f"{parent_path}\\Factories\\__metadata.json")
        fat_cats = list(fat_cats["product_hierarchy"][factory].keys())
        data["data"]["category"] = fat_cats
        data["data"]["selling_share_of_category"] = len(fat_cats)*[100/len(fat_cats)]
        to_json(file_path, data)
    return data

# load_factory_subfield('HajAmini', "AdministrativeandResearch")