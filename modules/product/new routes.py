from flask import Blueprint, render_template, jsonify, request, session
from utils.auth import login_required
from utils.paths import product_path, material_path
from utils.load_data import load_json, load_bom
from utils.updaters import product_adder
import json
import os

product_bp = Blueprint("product", __name__)

@product_bp.route("/product/production_selection")
@login_required
def production_selection():
    with open(product_path+".json", "r") as f:
        product_data = json.load(f)
    return render_template("product/production_selection.html", 
                           table_json = product_data)


@product_bp.route("/api/product_options")
@login_required
def product_options():
    """Return lists of distinct factories, categories and subcategories."""
    with open(product_path + ".json", "r") as f:
        product_data = json.load(f)
    
    # Extract unique values from the product data
    factories = sorted(list(set(item["Factory"] for item in product_data)))
    categories = sorted(list(set(item["Category"] for item in product_data)))
    subcategories = sorted(list(set(item["Subcategory"] for item in product_data)))

    return jsonify({
        "factories": factories,
        "categories": categories,
        "subcategories": subcategories
    })


@product_bp.route("/api/categories_by_factory")
@login_required
def categories_by_factory():
    """Return categories for a specific factory."""
    factory = request.args.get("factory", "")
    if not factory:
        return jsonify({"categories": []})
    
    with open(product_path + ".json", "r") as f:
        product_data = json.load(f)
    
    # Get unique categories for the specified factory
    categories = sorted(list(set(
        item["Category"] for item in product_data if item["Factory"] == factory
    )))
    
    return jsonify({"categories": categories})


@product_bp.route("/add_product", methods=["POST"])
@login_required
def add_product():
    data = request.get_json()
    product_name = data.get("product_name", "").strip()
    factory = data.get("factory", "").strip()
    category = data.get("category", "").strip()
    subcategory = data.get("subcategory", "").strip()

    if not all([product_name, factory, category, subcategory]):
        return jsonify({"status": "error", "message": "All fields are required."}), 400

    try:
        product_adder(product_name, factory, category, subcategory)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@product_bp.route("/add_category", methods=["POST"])
@login_required
def add_category():
    """Add a new category to the product data."""
    data = request.get_json()
    factory = data.get("factory", "").strip()
    category_name = data.get("category_name", "").strip()
    
    if not all([factory, category_name]):
        return jsonify({"status": "error", "message": "Factory and category name are required."}), 400
    
    try:
        category_adder(factory, category_name)
        return jsonify({"status": "ok", "message": f"Category '{category_name}' added successfully."})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@product_bp.route("/add_subcategory", methods=["POST"])
@login_required
def add_subcategory():
    """Add a new subcategory to the product data."""
    data = request.get_json()
    factory = data.get("factory", "").strip()
    category = data.get("category", "").strip()
    subcategory_name = data.get("subcategory_name", "").strip()
    
    if not all([factory, category, subcategory_name]):
        return jsonify({"status": "error", "message": "Factory, category, and subcategory name are required."}), 400
    
    try:
        subcategory_adder(factory, category, subcategory_name)
        return jsonify({"status": "ok", "message": f"Subcategory '{subcategory_name}' added successfully."})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@product_bp.route("/product/configuration")
@login_required
def configuration():
    return render_template("product/configuration.html")


@product_bp.route("/product/<product_name>", methods=["POST"])
@login_required
def product_page(product_name):
    factory = request.form["factory"]
    category = request.form["category"]
    subcategory = request.form["subcategory"]
    bom_json, recipe_path = load_bom(factory, category, subcategory, product_name)
    session["recipe_path"] = str(recipe_path)
    material_data = load_json(material_path+".json")
    return render_template("product/product_page.html", 
                           product_name=product_name, bom_json=bom_json,
                           materials_data=material_data)


@product_bp.route("/save_bom", methods=["POST"])
def save_bom():
    bom_path = session.get("recipe_path")
    payload = request.get_json(force=True)

    final_bom = {
        "_order": payload["_order"],
        "data": payload["data"]
    }

    with open(bom_path, "w", encoding="utf-8") as f:
        json.dump(final_bom, f, ensure_ascii=False, indent=4)

    return jsonify({"status": "ok"})


# ==============================
# CATEGORY ADDER FUNCTION
# ==============================
def category_adder(factory, category_name):
    """
    Add a new category to the product data structure.
    The product data is stored as a list of dictionaries with keys:
    Product_Name, Factory, Category, Subcategory
    """
    product_file = product_path + ".json"
    
    # Load existing product data
    with open(product_file, "r") as f:
        product_data = json.load(f)
    
    # Check if category already exists for this factory
    existing_categories = set(
        item["Category"] for item in product_data if item["Factory"] == factory
    )
    
    if category_name in existing_categories:
        raise ValueError(f"Category '{category_name}' already exists for factory '{factory}'")
    
    # Since categories are just metadata, we don't need to add a new product entry
    # Just return success - the UI will refresh and show the new category in dropdowns
    # Alternatively, you might want to log this addition for tracking purposes
    
    # Optionally, you can create a separate metadata file to track categories
    # For now, we'll just return success as the category will appear when products are added
    
    return True


# ==============================
# SUBCATEGORY ADDER FUNCTION
# ==============================
def subcategory_adder(factory, category, subcategory_name):
    """
    Add a new subcategory to the product data structure.
    The product data is stored as a list of dictionaries with keys:
    Product_Name, Factory, Category, Subcategory
    """
    product_file = product_path + ".json"
    
    # Load existing product data
    with open(product_file, "r") as f:
        product_data = json.load(f)
    
    # Check if subcategory already exists for this factory and category
    existing_subcategories = set(
        item["Subcategory"] for item in product_data 
        if item["Factory"] == factory and item["Category"] == category
    )
    
    if subcategory_name in existing_subcategories:
        raise ValueError(
            f"Subcategory '{subcategory_name}' already exists for factory '{factory}' and category '{category}'"
        )
    
    # Since subcategories are just metadata, we don't need to add a new product entry
    # Just return success - the UI will refresh and show the new subcategory in dropdowns
    
    return True