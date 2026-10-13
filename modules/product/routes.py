from flask import Blueprint, abort, current_app, g, render_template, jsonify, request, session
from utils.auth import get_profile_store, login_required
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
from utils.costing_engine import CostInputError, validate_live_bom_payload
from utils.paths import material_path, parent_path
from utils.load_data import load_json, load_bom
from utils.updaters import directory_tracer
from utils.product_creation import CreationConflict, business_name, create
from utils.file_lock import FileLockTimeout
from utils.product_catalog import build_product_hierarchy, product_catalog_document
import json
from pathlib import Path

product_bp = Blueprint("product", __name__)


def _registered_operational_keys(service):
    return [service.operational_key(factory) for factory in service.list_factories()]

@product_bp.route("/product/production_selection")
@login_required
def production_selection():
    service = FactoryService(get_profile_store())
    factories = service.get_accessible_factories(g.current_user, "product")
    if not factories:
        abort(403)
    operational_to_id = {service.operational_key(factory): factory["id"] for factory in factories}
    product_data = product_catalog_document(
        Path(parent_path) / "Factories", operational_to_id,
    )
    # Browser forms submit canonical registry IDs; operational keys never act
    # as authorization identities.
    product_data["Factory"] = {
        index: operational_to_id[value] for index, value in product_data["Factory"].items()
    }
    return render_template("product/production_selection.html", 
                           table_json = product_data)


@product_bp.route("/api/product_options")
@login_required
def product_options():
    """Return lists of distinct factories, categories and subcategories."""
    service = FactoryService(get_profile_store())
    factories = service.get_accessible_factories(g.current_user, "product")
    if not factories:
        abort(403)
    operational_to_id = {service.operational_key(factory): factory["id"] for factory in factories}
    raw_hierarchy = build_product_hierarchy(Path(parent_path) / "Factories", operational_to_id)
    product_hierarchy = {}
    categories = set()
    subcategories = set()
    for factory in factories:
        hierarchy = raw_hierarchy.get(service.operational_key(factory), {})
        product_hierarchy[factory["id"]] = hierarchy
        categories.update(hierarchy)
        for children in hierarchy.values():
            if isinstance(children, list):
                subcategories.update(children)


    return jsonify({
        "factories": factories,
        "categories": sorted(categories),
        "subcategories": sorted(subcategories),
        "product_hierarchy": product_hierarchy
    })

def _create(kind, fields):
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("درخواست باید یک شیء JSON معتبر باشد.")
        factory_id = data.get("factory")
        if not isinstance(factory_id, str) or not factory_id.strip():
            raise ValueError("کارخانه باید انتخاب شود.")
        service = FactoryService(get_profile_store())
        record = service.require_access(factory_id.strip(), g.current_user, "product", "WRITE")
        names = [business_name(data.get(field), product=field == "product_name") for field in fields]
        create(parent_path, service.operational_key(record), kind, names,
               capacity=data.get("capacity"),
               refresh=lambda: directory_tracer(
                   Path(parent_path) / "Factories", factory_keys=_registered_operational_keys(service)))
        return jsonify({"status": "ok", "message": "ایجاد با موفقیت انجام شد."})
    except FactoryNotFoundError:
        return jsonify({"status": "error", "message": "کارخانه در رجیستری سامانه وجود ندارد."}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError):
        return jsonify({"status": "error", "message": "دسترسی به کارخانه فعال مجاز نیست."}), 403
    except CreationConflict as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409
    except ValueError:
        # Decoder/resource details stay server-side.
        current_app.logger.info("Invalid product creation request", exc_info=True)
        return jsonify({"status": "error", "message": "اطلاعات یا مسیر انتخاب‌شده معتبر نیست."}), 400
    except FileLockTimeout:
        return jsonify({"status": "error", "message": "سامانه مشغول است؛ دوباره تلاش کنید."}), 503
    except Exception:
        current_app.logger.exception("Product %s creation failed for factory %s", kind, data.get("factory") if isinstance(data, dict) else None)
        return jsonify({"status": "error", "message": "ایجاد انجام نشد؛ برای بررسی با پشتیبانی تماس بگیرید."}), 500


@product_bp.route("/add_product", methods=["POST"])
@login_required
def add_product():
    return _create("product", ("category", "subcategory", "product_name"))


@product_bp.route("/add_category", methods=["POST"])
@login_required
def add_category():
    return _create("category", ("category_name",))


@product_bp.route("/add_subcategory", methods=["POST"])
@login_required
def add_subcategory():
    return _create("subcategory", ("category", "subcategory_name"))


@product_bp.route("/product/configuration")
@login_required
def configuration():
    if not FactoryService(get_profile_store()).get_accessible_factories(g.current_user, "product"):
        abort(403)
    return render_template("product/configuration.html")

@product_bp.route("/product/<product_name>", methods=["POST"])
@login_required
def product_page(product_name):
    try:
        factory_record = FactoryService(get_profile_store()).require_access(request.form["factory"], g.current_user, "product")
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
        FactoryService(get_profile_store()).require_access(factory_id, g.current_user, "product", "MODIFY")
    except FactoryNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    payload = request.get_json(force=True)

    try:
        payload = validate_live_bom_payload(payload, load_json(material_path + ".json"))
    except CostInputError as exc:
        return jsonify({
            "status": "error",
            "state": exc.state.value,
            "message": f"ورودی BOM معتبر نیست ({exc.detail.code}).",
        }), 400

    final_bom = {
        "_order": payload["_order"],
        "data": payload["data"]
    }

    with open(bom_path, "w", encoding="utf-8") as f:
        json.dump(final_bom, f, ensure_ascii=False, indent=4)

    return jsonify({"status": "ok"})
