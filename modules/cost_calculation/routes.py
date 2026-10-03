"""Authorized catalogue and HTTP adapters for the approved costing engine."""

import json
import logging
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request

from utils.auth import get_profile_store, login_required, require_top_level_admin
from utils.costing_engine import CostInputError, CostInputLoader, ProductIdentity, calculate_cost
from utils.factory_service import (
    FactoryAccessDeniedError,
    FactoryInactiveError,
    FactoryNotFoundError,
    FactoryService,
)
from utils.localization import DISPLAY_MAPPINGS
from utils.paths import product_path
from utils.planning_periods import approve_initial_period, discover_initial_period


cost_calculation_bp = Blueprint("cost_calculation", __name__)
LOGGER = logging.getLogger(__name__)
IDENTITY_FIELDS = ("Factory", "Category", "Subcategory", "Product_Name")

ERROR_MESSAGES = {
    "PERIOD_NOT_BOUND": "دوره برنامه‌ریزی برای این کارخانه پیکربندی یا توسط مالک تأیید نشده است.",
    "UNBOUND_LEGACY_SOURCE": "همه منابع لازم برای دوره برنامه‌ریزی توسط مالک تأیید نشده‌اند.",
    "SOURCE_UNAVAILABLE": "منبع مورد نیاز برای محاسبه پیدا نشد.",
    "LEGACY_SOURCE_NEEDS_INPUT": "ساختار منبع از داده‌های قدیمی ایجاد شد، اما مقدارهای کسب‌وکار باید تکمیل شوند.",
    "LEGACY_SOURCE_CONFLICT": "داده قدیمی با منبع فعلی تعارض دارد و تطبیق خودکار مجاز نیست.",
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
    "INITIAL_FACTORY_DATA_MISSING": "اطلاعات کارخانه برای ایجاد دوره اولیه کافی نیست.",
    "INITIAL_COSTING_DATA_MISSING": "برای شروع محاسبه، هیچ داده معتبر هزینه‌ای برای این کارخانه پیدا نشد.",
}


def _loader(service):
    options = {}
    if current_app.config.get("COSTING_DATA_ROOT"):
        options["data_root"] = Path(current_app.config["COSTING_DATA_ROOT"])
    if current_app.config.get("COSTING_PERIOD_BINDINGS_FILE"):
        options["period_bindings_path"] = Path(current_app.config["COSTING_PERIOD_BINDINGS_FILE"])
    return CostInputLoader(service, **options)


def _costing_paths():
    data_root = Path(current_app.config.get("COSTING_DATA_ROOT") or Path(product_path).resolve().parents[1])
    binding = Path(current_app.config.get("COSTING_PERIOD_BINDINGS_FILE") or (data_root.parent / "instance" / "costing_period_bindings.json"))
    return data_root, binding


def _typed_error(exc):
    message = ERROR_MESSAGES.get(exc.detail.code, "ورودی‌های لازم برای محاسبه هزینه کامل یا معتبر نیستند.")
    detail = {"code": exc.detail.code, "message": message}
    if exc.detail.source:
        detail["expected_path"] = exc.detail.source
    if exc.diagnostic:
        missing = exc.diagnostic.get("missing_sources", [])
        if not missing and exc.detail.code == "LEGACY_SOURCE_NEEDS_INPUT":
            missing = [item for item in exc.diagnostic.get("source_resolutions", [])
                       if item.get("migration_status") == "NEEDS_INPUT"]
        if missing:
            detail["missing_source"] = missing[0]["source_name"]
            if exc.detail.code == "LEGACY_SOURCE_NEEDS_INPUT" and missing[0]["source_name"] == "predictions":
                detail["message"] = "ساختار پیش‌بینی تولید از داده‌های قدیمی ایجاد شد، اما مقدار پیش‌بینی تولید باید تکمیل شود."
        detail["available_sources"] = exc.diagnostic.get("available_sources", [])
        detail["source_diagnostic"] = exc.diagnostic
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
    try:
        inputs = loader.load(identity.factory_id, user, identity, period, module="cost_calculation")
    except CostInputError as exc:
        if exc.detail.code != "PERIOD_NOT_BOUND" or period not in ("", "INITIAL"):
            raise
        data_root, binding = _costing_paths()
        try:
            discover_initial_period(loader.factory_service, identity.factory_id, data_root, binding)
        except ValueError as initialization_error:
            message = str(initialization_error)
            if "canonical factory" in message:
                code, localized = "INITIAL_FACTORY_DATA_MISSING", ERROR_MESSAGES["INITIAL_FACTORY_DATA_MISSING"]
            elif "no valid costing data" in message:
                code, localized = "INITIAL_COSTING_DATA_MISSING", ERROR_MESSAGES["INITIAL_COSTING_DATA_MISSING"]
            else:
                raise exc from initialization_error
            raise CostInputError(exc.state, code, localized) from initialization_error
        inputs = _loader(loader.factory_service).load(
            identity.factory_id, user, identity, period, module="cost_calculation"
        )
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


@cost_calculation_bp.route("/planning-period/initial/discover", methods=["POST"])
@login_required
@require_top_level_admin
def discover_initial_planning_period():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("factory_id"), str):
        return jsonify({"state": "INVALID_REQUEST", "error": {"code": "MISSING_FACTORY_ID", "message": "شناسه canonical کارخانه الزامی است."}}), 400
    store = get_profile_store()
    try:
        data_root, binding = _costing_paths()
        initial = discover_initial_period(FactoryService(store), data["factory_id"], data_root, binding)
        return jsonify({"state": "ACTIVE", "period": initial}), 200
    except ValueError as exc:
        return jsonify({"state": "INVALID_REQUEST", "error": {"code": "INITIAL_PERIOD_DISCOVERY_REJECTED", "message": str(exc)}}), 422


@cost_calculation_bp.route("/planning-period/initial/approve", methods=["POST"])
@login_required
@require_top_level_admin
def approve_initial_planning_period():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("factory_id"), str) or not isinstance(data.get("end"), str) or not isinstance(data.get("sources"), list):
        return jsonify({"state": "INVALID_REQUEST", "error": {"code": "INVALID_APPROVAL", "message": "کارخانه، پایان دوره و منابع تأییدشده الزامی هستند."}}), 400
    store = get_profile_store()
    try:
        _, binding = _costing_paths()
        active = approve_initial_period(store, binding, data["factory_id"], g.current_user["id"], data["end"], data["sources"])
        return jsonify({"state": "ACTIVE", "period": active}), 200
    except (ValueError, PermissionError) as exc:
        return jsonify({"state": "INVALID_REQUEST", "error": {"code": "INITIAL_PERIOD_APPROVAL_REJECTED", "message": str(exc)}}), 422
