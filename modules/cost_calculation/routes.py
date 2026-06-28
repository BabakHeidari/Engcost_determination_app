from flask import Blueprint, render_template, request, jsonify
import json
from pathlib import Path
from utils.auth import login_required
from utils.paths import product_path
from utils.localization import DISPLAY_MAPPINGS
from utils.cost_determiners import cost_aggregator


cost_calculation_bp = Blueprint("cost_calculation", __name__)


# ------------------------------------------------------------
# 1. PAGE RENDERING – serves the HTML with the product table
# ------------------------------------------------------------
@cost_calculation_bp.route("/cost_calculation")
@login_required
def cost_cal():
    """Render the main product catalogue page with the cost‑calculation section."""
    product_catalog_path = Path((product_path + ".json").replace("\\", "/"))
    with open(product_catalog_path, "r", encoding="utf-8") as product_file:
        products = json.load(product_file)
    return render_template(
        "cost/calculation.html",
        table_json=products,
        display_mappings=DISPLAY_MAPPINGS,
    )

# ------------------------------------------------------------
# 2. SINGLE PRODUCT COST – called by the “Calculate Cost” button
# ------------------------------------------------------------
@cost_calculation_bp.route("/get_cost", methods=["POST"])
@login_required
def get_cost():
    """
    Expects JSON:
    {
        "Product_Name": "...",
        "Factory": "...",
        "Category": "...",
        "Subcategory": "..."
    }
    Returns JSON with cost breakdown.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON payload"}), 400

    cost = cost_aggregator(
        product=data.get("Product_Name", ""),
        fac=data.get("Factory", ""),
        cat=data.get("Category", ""),
        subc=data.get("Subcategory", "")
    )
    return jsonify(cost)


# ------------------------------------------------------------
# 3. BULK COST – called by the “Download CSV Report” button
# ------------------------------------------------------------
@cost_calculation_bp.route("/get_costs_bulk", methods=["POST"])
@login_required
def get_costs_bulk():
    """
    Expects JSON list of product objects (each with Product_Name, Factory, Category, Subcategory).
    Returns JSON object mapping product name -> cost breakdown.
    """
    products = request.get_json()
    if not isinstance(products, list):
        return jsonify({"error": "Expected a list of products"}), 400

    result = {}
    for prod in products:
        name = prod.get("Product_Name", "")
        cost = cost_aggregator(
            product=name,
            fac=prod.get("Factory", ""),
            cat=prod.get("Category", ""),
            subc=prod.get("Subcategory", "")
        )
        result[name] = cost
    return jsonify(result)