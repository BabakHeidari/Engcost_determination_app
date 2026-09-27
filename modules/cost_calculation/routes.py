"""Authorized catalogue and HTTP adapters for the approved costing engine."""

import json
import logging
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request

from utils.auth import get_profile_store, login_required
from utils.costing_engine import CostInputError, CostInputLoader, ProductIdentity, calculate_cost
from utils.factory_service import (
    FactoryAccessDeniedError,
    FactoryInactiveError,
    FactoryNotFoundError,
    FactoryService,
)
from utils.localization import DISPLAY_MAPPINGS
from utils.paths import product_path


cost_calculation_bp = Blueprint("cost_calculation", __name__)
LOGGER = logging.getLogger(__name__)
IDENTITY_FIELDS = ("Factory", "Category", "Subcategory", "Product_Name")

ERROR_MESSAGES = {
    "PERIOD_NOT_BOUND": "دوره برنامه‌ریزی برای این کارخانه پیکربندی یا توسط مالک تأیید نشده است.",
    "UNBOUND_LEGACY_SOURCE": "همه منابع لازم برای دوره برنامه‌ریزی توسط مالک تأیید نشده‌اند.",
    "SOURCE_UNAVAILABLE": "یکی از منابع داده تأییدشده در دسترس نیست.",
    "SOURCE_PARSE_ERROR": "ساختار یکی از منابع داده تأییدشده قابل خواندن نیست.",
    "INVALID_SOURCE_SCHEMA": "ساختار یکی از منابع داده کامل یا معتبر نیست.",
    "COLUMN_LENGTH_MISMATCH": "ستون‌های یکی از منابع داده هم‌اندازه نیستند.",
    "MATERIAL_PRICE_NOT_UNIQUE": "قیمت جاری ماده موردنیاز موجود یا یکتا نیست.",
    "AMBIGUOUS_FX_MAPPING": "نرخ تبدیل ارز به ریال موجود یا یکتا نیست.",
    "PREDICTION_NOT_UNIQUE": "پیش‌بینی تولید محصول موجود یا یکتا نیست.",
    "MISSING_PRODUCT_PREDICTION": "پیش‌بینی تولید محصول موجود نیست.",
    "CATEGORY_SHARE_NOT_UNIQUE": "سهم دسته محصول موجود یا یکتا نیست.",
    "INVALID_PERCENTAGE": "درصد ضایعات یا بازیافت باید بین صفر تا صد باشد.",
    "INVALID_PERIOD_BINDING": "تنظیمات دوره برنامه‌ریزی معتبر نیست.",
}


def _loader(service):
    options = {}
    if current_app.config.get("COSTING_DATA_ROOT"):
        options["data_root"] = Path(current_app.config["COSTING_DATA_ROOT"])
    if current_app.config.get("COSTING_PERIOD_BINDINGS_FILE"):
        options["period_bindings_path"] = Path(current_app.config["COSTING_PERIOD_BINDINGS_FILE"])
    return CostInputLoader(service, **options)


def _typed_error(exc):
    message = ERROR_MESSAGES.get(exc.detail.code, "ورودی‌های لازم برای محاسبه هزینه کامل یا معتبر نیستند.")
    detail = {"code": exc.detail.code, "message": message}
    if exc.detail.source:
        # A logical source name is useful; local paths are deliberately hidden.
        detail["source"] = Path(exc.detail.source).name
    return {"state": exc.state.value, "error": detail, "errors": [detail]}


def _request_identity(data):
    if not isinstance(data, dict):
        return None, (jsonify({"state": "INVALID_REQUEST", "error": {"code": "INVALID_JSON", "message": "بدنه درخواست باید JSON معتبر باشد."}}), 400)
    missing = [field for field in IDENTITY_FIELDS if not isinstance(data.get(field), str) or not data[field].strip()]
    if missing:
        return None, (jsonify({"state": "INVALID_REQUEST", "error": {"code": "MISSING_IDENTITY", "message": "هویت چهارگانه محصول کامل نیست.", "fields": missing}}), 400)
    identity = ProductIdentity(*(data[field].strip() for field in IDENTITY_FIELDS))
    return identity, None


def _identity_key(identity):
    return json.dumps([identity.factory_id, identity.category, identity.subcategory, identity.product], ensure_ascii=False, separators=(",", ":"))


def _calculate(loader, user, identity, period):
    inputs = loader.load(identity.factory_id, user, identity, period, module="cost_calculation")
    result = calculate_cost(inputs)
    payload = result.to_dict()
    for source in payload.get("source_metadata", []):
        source["source"] = Path(source["source"]).name
    if result.state.value != "OK":
        first = result.errors[0] if result.errors else None
        if first:
            message = ERROR_MESSAGES.get(first.code, "محاسبه هزینه با ورودی‌های فعلی امکان‌پذیر نیست.")
            payload["error"] = {"code": first.code, "message": message}
            payload["errors"] = [{"code": first.code, "message": message}]
    return payload


@cost_calculation_bp.route("/cost_calculation")
@login_required
def cost_cal():
    """Render only products whose operational key resolves uniquely in the user's scope."""
    service = FactoryService(get_profile_store())
    factories = service.get_accessible_factories(g.current_user, "cost_calculation")
    if not factories:
        abort(403)
    operational = {}
    for factory in factories:
        operational.setdefault(service.operational_key(factory), []).append(factory)

    product_catalog_path = Path((product_path + ".json").replace("\\", "/"))
    with product_catalog_path.open("r", encoding="utf-8") as product_file:
        catalogue = json.load(product_file)
    rows = []
    if isinstance(catalogue, dict) and isinstance(catalogue.get("Factory"), dict):
        for index, legacy_key in catalogue["Factory"].items():
            matches = operational.get(legacy_key, [])
            if len(matches) != 1:
                continue
            row = {column: values.get(index, "") for column, values in catalogue.items() if isinstance(values, dict)}
            row["Factory"] = matches[0]["id"]
            row["Factory_Label"] = matches[0]["name"]
            rows.append(row)
    return render_template("cost/calculation.html", table_json=rows, display_mappings=DISPLAY_MAPPINGS)


@cost_calculation_bp.route("/get_cost", methods=["POST"])
@login_required
def get_cost():
    data = request.get_json(silent=True)
    identity, error = _request_identity(data)
    if error:
        return error
    if "Period" in data and not isinstance(data["Period"], str):
        return jsonify({"state": "INVALID_REQUEST", "error": {"code": "INVALID_PERIOD", "message": "شناسه دوره باید متن باشد."}}), 400
    service = FactoryService(get_profile_store())
    try:
        payload = _calculate(_loader(service), g.current_user, identity, data.get("Period", ""))
        return jsonify(payload), 200 if payload["state"] == "OK" else 422
    except FactoryNotFoundError:
        return jsonify({"state": "NOT_FOUND", "error": {"code": "FACTORY_NOT_FOUND", "message": "کارخانه درخواست‌شده یافت نشد."}}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError):
        return jsonify({"state": "FORBIDDEN", "error": {"code": "FACTORY_FORBIDDEN", "message": "دسترسی به کارخانه درخواست‌شده مجاز نیست."}}), 403
    except CostInputError as exc:
        return jsonify(_typed_error(exc)), 422
    except Exception:
        request_id = uuid4().hex
        LOGGER.exception("Unexpected cost calculation failure request_id=%s", request_id)
        return jsonify({"state": "SERVER_ERROR", "error": {"code": "COST_SERVER_ERROR", "message": "خطای داخلی در محاسبه هزینه رخ داد.", "request_id": request_id}}), 500


@cost_calculation_bp.route("/get_costs_bulk", methods=["POST"])
@login_required
def get_costs_bulk():
    products = request.get_json(silent=True)
    if not isinstance(products, list):
        return jsonify({"state": "INVALID_REQUEST", "error": {"code": "EXPECTED_PRODUCT_LIST", "message": "فهرست محصولات معتبر نیست."}}), 400
    service, validated = FactoryService(get_profile_store()), []
    # Authorize the entire batch before protected reads; never return a partial
    # response following a global identity/authorization failure.
    for product in products:
        identity, error = _request_identity(product)
        if error:
            return error
        if "Period" in product and not isinstance(product["Period"], str):
            return jsonify({"state": "INVALID_REQUEST", "error": {"code": "INVALID_PERIOD", "message": "شناسه دوره باید متن باشد."}}), 400
        try:
            service.require_access(identity.factory_id, g.current_user, "cost_calculation")
        except FactoryNotFoundError:
            return jsonify({"state": "NOT_FOUND", "error": {"code": "FACTORY_NOT_FOUND", "message": "کارخانه درخواست‌شده یافت نشد."}}), 404
        except (FactoryAccessDeniedError, FactoryInactiveError):
            return jsonify({"state": "FORBIDDEN", "error": {"code": "FACTORY_FORBIDDEN", "message": "دسترسی به کارخانه درخواست‌شده مجاز نیست."}}), 403
        validated.append((product, identity))

    loader, results = _loader(service), {}
    for product, identity in validated:
        key = _identity_key(identity)
        try:
            results[key] = _calculate(loader, g.current_user, identity, product.get("Period", ""))
        except CostInputError as exc:
            results[key] = {**_typed_error(exc), "identity": identity.__dict__}
        except Exception:
            request_id = uuid4().hex
            LOGGER.exception("Unexpected bulk cost failure request_id=%s", request_id)
            results[key] = {"state": "SERVER_ERROR", "identity": identity.__dict__, "error": {"code": "COST_SERVER_ERROR", "message": "خطای داخلی در محاسبه این محصول رخ داد.", "request_id": request_id}}
    states = [item.get("state") for item in results.values()]
    coverage = {"configured": len(results), "calculated": states.count("OK"), "excluded": len(results) - states.count("OK")}
    return jsonify({"state": "OK" if not coverage["excluded"] else "PARTIAL", "coverage": coverage, "results": results})
