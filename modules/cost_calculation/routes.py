from flask import Blueprint, abort, g, render_template, request, jsonify
import json
from pathlib import Path
from utils.auth import get_profile_store, login_required
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
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
    service = FactoryService(get_profile_store())
    factories = service.get_accessible_factories(g.current_user, "COST_CALCULATION")
    if not factories:
        abort(403)
    product_catalog_path = Path((product_path + ".json").replace("\\", "/"))
    with open(product_catalog_path, "r", encoding="utf-8") as product_file:
        products = json.load(product_file)
    allowed = {service.operational_key(factory) for factory in factories}
    if isinstance(products, dict) and isinstance(products.get("Factory"), dict):
        indexes = [key for key, value in products["Factory"].items() if value in allowed]
        products = {column: {str(i): values[key] for i, key in enumerate(indexes)} for column, values in products.items()}
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

    try:
        factory = FactoryService(get_profile_store()).require_access(data.get("Factory", ""), g.current_user, "COST_CALCULATION")
    except FactoryNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
        return jsonify({"error": str(exc)}), 403
    cost = cost_aggregator(
        product=data.get("Product_Name", ""),
        fac=FactoryService(get_profile_store()).operational_key(factory),
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

    # Validate the complete batch before loading/calculating any protected
    # factory data, so a later tampered item cannot produce a partial read.
    authorized_products = []
    for prod in products:
        if not isinstance(prod, dict):
            return jsonify({"error": "Invalid product entry"}), 400
        try:
            factory = FactoryService(get_profile_store()).require_access(prod.get("Factory", ""), g.current_user, "COST_CALCULATION")
        except FactoryNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
            return jsonify({"error": str(exc)}), 403
        authorized_products.append((prod, FactoryService(get_profile_store()).operational_key(factory)))

    result = {}
    for prod, operational_key in authorized_products:
        name = prod.get("Product_Name", "")
        cost = cost_aggregator(
            product=name,
            fac=operational_key,
            cat=prod.get("Category", ""),
            subc=prod.get("Subcategory", "")
        )
        result[name] = cost
    return jsonify(result)
