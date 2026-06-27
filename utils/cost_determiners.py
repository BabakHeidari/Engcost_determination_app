from utils.paths import parent_path
from pathlib import Path
import pandas as pd
from utils.load_data import load_bom, load_json

def __BOM_coster(product:str, fac, cat, subc):
    bom_data, recipe_path = load_bom(fac, cat, subc, product)
    bom_data = bom_data['data']
    bom_cost = dict()
    for material in bom_data['materials']:
        bom_cost[material] = bom_data['cost_of_material_in_rial'][bom_data['materials'].index(material)]
    bom_cost['Total_BOM_Cost']= sum(bom_cost.values())
    return bom_cost

def __subfield_coster(fac, subfield):
    factory_path = Path(parent_path) / "Factories" / fac / f"Factory_Data_{subfield}.json"
    try:
        subfield_data = load_json(factory_path)
        subfield_cost = sum(subfield_data['data']['cost'])
    except:
        subfield_cost = 0
    return subfield_cost

def __all_subfields_coster(product, fac, cat):
    all_subfields_costs = dict()

    factory_path = Path(parent_path) / "Factories" / fac / "Factory_Data.json"
    factory_data = load_json(factory_path)
    subfields = factory_data["data"]["Subfield"]

    category_weights_path = Path(parent_path) / "Factories" / fac / "category_weights.json"
    category_weights = load_json(category_weights_path)['data']
    category_cost_weight = category_weights["selling_share_of_category"][category_weights["category"].index(cat)]

    ProductionPrediction_path = Path(parent_path) / "Factories" / fac / "ProductionPrediction.json"
    ProductionPrediction = load_json(ProductionPrediction_path)["data"]
    ProductionPrediction = ProductionPrediction["Predicted Production"][ProductionPrediction["Product Name"].index(product)]
    # print(f"for product {product}, production prediction is {ProductionPrediction}.")

    for subfield in subfields:
        all_subfields_costs[subfield] = (__subfield_coster(fac, subfield)/(category_cost_weight/100))/ProductionPrediction
    return all_subfields_costs


def cost_aggregator(product:str, fac, cat, subc):
    bom_cost = __BOM_coster(product, fac, cat, subc)
    all_costs = __all_subfields_coster(product, fac, cat)
    
    all_costs["BOM"] = bom_cost['Total_BOM_Cost']
    all_costs["BOM_Details"] = bom_cost

    # Sum all values except the "BOM_Details" key
    all_costs["Final_Production_Cost"] = sum(
        value for key, value in all_costs.items() 
        if key != "BOM_Details"
    )    
    
    return all_costs

# c = cost_aggregator("B3N47", "DinMohamadpour", "IKCO", "LithiumIon")
# print(c)