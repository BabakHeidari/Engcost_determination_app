from utils.product_sheet_updater import parent_path
import json
from pathlib import Path
from utils.load_data import load_json

def load_bom(factory, category, subcategory, product_name):
    recipe_path = Path(parent_path) / "Factories" / factory / category / subcategory / f"{product_name}.json"
    
    data = load_json(recipe_path)
    
    return data, recipe_path
