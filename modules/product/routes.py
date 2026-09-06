from flask import Blueprint, g, render_template, jsonify, request, session
from utils.auth import get_profile_store, login_required
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
from utils.paths import product_path, material_path, parent_path
from utils.load_data import load_json, load_bom
from utils.updaters import create_product_metadata, category_adder, subcategory_adder, product_adder, directory_tracer, category_weights_updater, capacity_writer
import json

product_bp = Blueprint("product", __name__)

@product_bp.route("/product/production_selection")
@login_required
def production_selection():
    create_product_metadata(parent_path, product_path,"Factories", ".json")
    product_data = load_json(product_path+".json")
    service = FactoryService(get_profile_store())
    allowed = {service.operational_key(factory) for factory in service.get_accessible_factories(g.current_user, "PRODUCT")}
    if isinstance(product_data, dict) and isinstance(product_data.get("Factory"), dict):
        indexes = [key for key, value in product_data["Factory"].items() if value in allowed]
        product_data = {column: {str(i): values[key] for i, key in enumerate(indexes)} for column, values in product_data.items()}
    return render_template("product/production_selection.html", 
                           table_json = product_data)


@product_bp.route("/api/product_options")
@login_required
def product_options():
    """Return lists of distinct factories, categories and subcategories."""
    __meta_data = load_json(f"{parent_path}\\Factories\\__metadata.json")
    service = FactoryService(get_profile_store())
    factories = service.get_accessible_factories(g.current_user, "PRODUCT")
    raw_hierarchy = __meta_data["product_hierarchy"]
    product_hierarchy = {}
    categories = set()
    subcategories = set()
    for factory in factories:
        hierarchy = raw_hierarchy.get(service.operational_key(factory), {})
        product_hierarchy[factory["id"]] = hierarchy
        categories.update(hierarchy)
        for children in hierarchy.values():
            if isinstance(children, dict):
                subcategories.update(children)


    return jsonify({
        "factories": factories,
        "categories": sorted(categories),
        "subcategories": sorted(subcategories),
        "product_hierarchy": product_hierarchy
    })

@product_bp.route("/add_product", methods=["POST"])
@login_required
def add_product():
    data = request.get_json()
    product_name = data.get("product_name", "").strip()
    factory_id = data.get("factory", "").strip()
    category = data.get("category", "").strip()
    subcategory = data.get("subcategory", "").strip()
    capacity = data.get("capacity", "")

    if not all([product_name, factory_id, category, subcategory]):
        return jsonify({"status": "error", "message": "All fields are required."}), 400

    try:
        factory_record = FactoryService(get_profile_store()).require_access(factory_id, g.current_user, "PRODUCT", "WRITE")
        factory = FactoryService(get_profile_store()).operational_key(factory_record)
        product_adder(product_name, factory, category, subcategory)
        capacity_writer(product_name, factory, category, subcategory, capacity)
        directory_tracer(f"{parent_path}\\Factories")
        product_options()
        category_weights_updater(factory, category)
        return jsonify({"status": "ok"})
    except FactoryNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as e:
        return jsonify({"status": "error", "message": str(e)}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@product_bp.route("/add_category", methods=["POST"])
@login_required
def add_category():
    """Add a new category to the product data."""
    data = request.get_json()
    factory_id = data.get("factory", "").strip()
    category_name = data.get("category_name", "").strip()
    
    if not all([factory_id, category_name]):
        return jsonify({"status": "error", "message": "Factory and category name are required."}), 400
    
    try:
        factory_record = FactoryService(get_profile_store()).require_access(factory_id, g.current_user, "PRODUCT", "WRITE")
        factory = FactoryService(get_profile_store()).operational_key(factory_record)
        category_adder(factory, category_name)
        directory_tracer(f"{parent_path}\\Factories")
        product_options()
        return jsonify({"status": "ok", "message": f"Category '{category_name}' added successfully."})
    except FactoryNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as e:
        return jsonify({"status": "error", "message": str(e)}), 403
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@product_bp.route("/add_subcategory", methods=["POST"])
@login_required
def add_subcategory():
    """Add a new subcategory to the product data."""
    data = request.get_json()
    factory_id = data.get("factory", "").strip()
    category = data.get("category", "").strip()
    subcategory_name = data.get("subcategory_name", "").strip()
    
    if not all([factory_id, category, subcategory_name]):
        return jsonify({"status": "error", "message": "Factory, category, and subcategory name are required."}), 400
    
    try:
        factory_record = FactoryService(get_profile_store()).require_access(factory_id, g.current_user, "PRODUCT", "WRITE")
        factory = FactoryService(get_profile_store()).operational_key(factory_record)
        subcategory_adder(factory, category, subcategory_name)
        directory_tracer(f"{parent_path}\\Factories")
        product_options()
        return jsonify({"status": "ok", "message": f"Subcategory '{subcategory_name}' added successfully."})
    except FactoryNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as e:
        return jsonify({"status": "error", "message": str(e)}), 403
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
    try:
        factory_record = FactoryService(get_profile_store()).require_access(request.form["factory"], g.current_user, "PRODUCT")
    except FactoryNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    factory = FactoryService(get_profile_store()).operational_key(factory_record)
    category = request.form["category"]
    subcategory = request.form["subcategory"]
    bom_json, recipe_path = load_bom(factory, category, subcategory, product_name)
    session["recipe_path"] = str(recipe_path)
    session["recipe_factory_id"] = factory_record["id"]
    material_data = load_json(material_path+".json")
    return render_template("product/product_page.html", 
                           product_name=product_name, bom_json=bom_json,
                            materials_data = material_data)


@product_bp.route("/save_bom", methods=["POST"])
@login_required
def save_bom():
    # build bom_path however you do now, e.g. using a default factory/category/etc.
    bom_path = session.get("recipe_path")
    factory_id = session.get("recipe_factory_id")
    if not isinstance(bom_path, str) or not isinstance(factory_id, str):
        return jsonify({"status": "error", "message": "زمینه کارخانه معتبر نیست."}), 400
    try:
        FactoryService(get_profile_store()).require_access(factory_id, g.current_user, "PRODUCT", "WRITE")
    except FactoryNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    payload = request.get_json(force=True)

    final_bom = {
        "_order": payload["_order"],
        "data": payload["data"]
    }

    with open(bom_path, "w", encoding="utf-8") as f:
        json.dump(final_bom, f, ensure_ascii=False, indent=4)

    return jsonify({"status": "ok"})
