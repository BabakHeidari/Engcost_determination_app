from flask import Blueprint, abort, g, render_template, request, jsonify
import json
from pathlib import Path
from utils.auth import get_profile_store, login_required
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
from utils.paths import product_path
from utils.localization import DISPLAY_MAPPINGS
from utils.costing_engine import (
    CostInputError,
    CostInputLoader,
    ProductIdentity,
    calculate_cost,
)


cost_calculation_bp = Blueprint("cost_calculation", __name__)


# ------------------------------------------------------------
# 1. PAGE RENDERING – serves the HTML with the product table
# ------------------------------------------------------------
@cost_calculation_bp.route("/cost_calculation")
@login_required
def cost_cal():
    """Render the main product catalogue page with the cost‑calculation section."""
    service = FactoryService(get_profile_store())
    factories = service.get_accessible_factories(g.current_user, "cost_calculation")
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
        "Subcategory": "...",
        "Period": "..."  // optional only when one owner binding is active
    }
    Returns JSON with cost breakdown.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON payload"}), 400

    service = FactoryService(get_profile_store())
    factory_id = data.get("Factory", "")
    identity = ProductIdentity(
        factory_id, data.get("Category", ""), data.get("Subcategory", ""), data.get("Product_Name", "")
    )
    try:
        inputs = CostInputLoader(service).load(
            factory_id, g.current_user, identity, data.get("Period", ""), module="cost_calculation"
        )
    except FactoryNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
        return jsonify({"error": str(exc)}), 403
    except CostInputError as exc:
        return jsonify({"state": exc.state.value, "errors": [exc.detail.__dict__]}), 422
    result = calculate_cost(inputs)
    return jsonify(result.to_dict()), 200 if result.state.value == "OK" else 422


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
    service = FactoryService(get_profile_store())
    loader = CostInputLoader(service)
    authorized_products = []
    for prod in products:
        if not isinstance(prod, dict):
            return jsonify({"error": "Invalid product entry"}), 400
        try:
            factory = service.require_access(prod.get("Factory", ""), g.current_user, "cost_calculation")
        except FactoryNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
            return jsonify({"error": str(exc)}), 403
        authorized_products.append((prod, factory))

    result = {}
    for prod, factory in authorized_products:
        name = prod.get("Product_Name", "")
        identity = ProductIdentity(factory["id"], prod.get("Category", ""), prod.get("Subcategory", ""), name)
        key = json.dumps(
            [identity.factory_id, identity.category, identity.subcategory, identity.product],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            inputs = loader.load(factory["id"], g.current_user, identity, prod.get("Period", ""), module="cost_calculation")
            result[key] = calculate_cost(inputs).to_dict()
        except CostInputError as exc:
            result[key] = {"state": exc.state.value, "errors": [exc.detail.__dict__], "identity": identity.__dict__}
    return jsonify(result)
