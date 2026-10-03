"""Authorized Factory Configuration V2 pages and explicit save endpoints."""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, url_for

from utils.auth import get_profile_store, login_required
from utils.factory_configuration import (
    FactoryConfigurationError, POOL_IDS, derived_summary,
    ensure_factory_configuration_v2, load_pool, save_pool, validate_identifier,
    validate_pool_id,
)
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
from utils.paths import parent_path

factory_parameters_bp = Blueprint("factory_parameters", __name__)
POOL_LABELS = {
    "AdministrativeandResearch": "اداری و پژوهش", "Payroll": "حقوق و دستمزد",
    "Overhead": "سربار", "FinancialCosts": "هزینه‌های مالی", "Depriciation": "استهلاک",
    "NonOperationalCostsandIncomes": "هزینه‌ها و درآمدهای غیرعملیاتی",
}


def _authorized(factory_id, permission="READ"):
    try:
        service = FactoryService(get_profile_store())
        record = service.require_access(factory_id, g.current_user, "factory_parameters", permission)
        operational_key = service.operational_key(record)
        ensure_factory_configuration_v2(record["id"], operational_key, data_root=parent_path, persist=True)
        return record, Path(parent_path) / "Factories" / operational_key
    except FactoryNotFoundError as exc:
        return render_template("factory_parameters/unavailable.html", message=str(exc)), 404
    except (FactoryAccessDeniedError, FactoryInactiveError):
        abort(403)


def _error(exc):
    return jsonify({"status": "error", "code": exc.code, "message": str(exc)}), 400


def _atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


@factory_parameters_bp.route("/factory_parameters/", methods=["GET"])
@login_required
def factory_parameters():
    factories = FactoryService(get_profile_store()).get_accessible_factories(g.current_user, "factory_parameters")
    if not factories:
        abort(403)
    data = {"_order": ["factory_id", "factory name", "city"], "data": {
        "factory_id": [item["id"] for item in factories], "factory name": [item["name"] for item in factories],
        "city": [item.get("location") or "" for item in factories]}}
    return render_template("factory_parameters/factories.html", table_json=data)


@factory_parameters_bp.route("/factory_parameters/<factory_name>", methods=["GET", "POST"])
@login_required
def factory_details(factory_name):
    if request.method == "POST":
        return redirect(url_for("factory_parameters.factory_details", factory_name=factory_name), code=303)
    result = _authorized(factory_name)
    if isinstance(result, tuple) and isinstance(result[1], int):
        return result
    record, root = result
    summary = derived_summary(root)
    table = {"_order": ["Subfield", "Cost", "PercentageOfAll"], "data": {
        "Subfield": list(POOL_IDS), "Cost": [summary["pool_totals"][p] for p in POOL_IDS],
        "PercentageOfAll": [summary["percentages"][p] for p in POOL_IDS]}}
    config = root / "configuration"
    category = json.loads((config / "category_weights.json").read_text(encoding="utf-8"))
    prediction = json.loads((config / "production_prediction.json").read_text(encoding="utf-8"))
    return render_template("factory_parameters/factory_details.html", table_json=table,
        factory_name=record["id"], factory_display_name=record["name"], unconfigured=False,
        category_table=category, preditcionOfProductionPerCapitaData=prediction,
        pool_urls={p: url_for("factory_parameters.subfield", factory_name=record["id"], Subfield=p) for p in POOL_IDS})


@factory_parameters_bp.route("/factory_parameters/<factory_name>/<Subfield>", methods=["GET", "POST"])
@login_required
def subfield(factory_name, Subfield):
    if request.method == "POST":
        return redirect(url_for("factory_parameters.subfield", factory_name=factory_name, Subfield=Subfield), code=303)
    try:
        validate_pool_id(Subfield)
    except FactoryConfigurationError:
        abort(404)
    result = _authorized(factory_name)
    if isinstance(result, tuple) and isinstance(result[1], int):
        return result
    record, root = result
    document = load_pool(root, Subfield)
    total = sum(document["data"]["cost"])
    item_urls = {item_id: url_for("factory_parameters.cost_item", factory_name=record["id"],
                                  Subfield=Subfield, item_id=item_id) for item_id in document["data"]["id"]}
    return render_template("factory_parameters/factory_subfield.html", table_json=document,
        factory_name=record["id"], Subfield=Subfield, pool_label=POOL_LABELS[Subfield],
        pool_total=total, item_urls=item_urls,
        save_url=url_for("factory_parameters.save_cost_pool", factory_name=record["id"], pool_id=Subfield))


@factory_parameters_bp.route("/factory_parameters/<factory_name>/<Subfield>/<item_id>", methods=["GET"])
@login_required
def cost_item(factory_name, Subfield, item_id):
    try:
        validate_pool_id(Subfield); validate_identifier(item_id, "item id")
    except FactoryConfigurationError:
        abort(404)
    result = _authorized(factory_name)
    if isinstance(result, tuple) and isinstance(result[1], int):
        return result
    record, root = result
    document = load_pool(root, Subfield)
    matches = [i for i, value in enumerate(document["data"]["id"]) if value == item_id]
    if len(matches) != 1:
        abort(404)
    index = matches[0]
    return render_template("factory_parameters/factory_cost_item.html", factory_id=record["id"],
        factory_name=record["name"], pool_id=Subfield, pool_label=POOL_LABELS[Subfield], item_id=item_id,
        subject=document["data"]["subject"][index], cost=document["data"]["cost"][index],
        save_url=url_for("factory_parameters.save_cost_item", factory_name=record["id"], pool_id=Subfield, item_id=item_id))


@factory_parameters_bp.route("/factory_parameters/<factory_name>/cost-pools/<pool_id>", methods=["PUT"])
@login_required
def save_cost_pool(factory_name, pool_id):
    try:
        validate_pool_id(pool_id)
        result = _authorized(factory_name, "MODIFY")
        if isinstance(result, tuple) and isinstance(result[1], int): return result
        _, root = result
        document = save_pool(root, pool_id, request.get_json(force=True))
        return jsonify({"status": "success", "pool_total": sum(document["data"]["cost"])})
    except FactoryConfigurationError as exc:
        return _error(exc)
    except ValueError as exc:
        return jsonify({"status": "error", "code": "INVALID_COST_POOL", "message": str(exc)}), 400


@factory_parameters_bp.route("/factory_parameters/<factory_name>/cost-pools/<pool_id>/<item_id>", methods=["PUT"])
@login_required
def save_cost_item(factory_name, pool_id, item_id):
    try:
        validate_pool_id(pool_id); validate_identifier(item_id, "item id")
        result = _authorized(factory_name, "MODIFY")
        if isinstance(result, tuple) and isinstance(result[1], int): return result
        _, root = result
        document = load_pool(root, pool_id)
        matches = [i for i, value in enumerate(document["data"]["id"]) if value == item_id]
        if len(matches) != 1: abort(404)
        payload = request.get_json(force=True); index = matches[0]
        document["data"]["subject"][index] = payload.get("subject")
        document["data"]["cost"][index] = payload.get("cost")
        save_pool(root, pool_id, document)
        return jsonify({"status": "success", "item_id": item_id})
    except FactoryConfigurationError as exc:
        return _error(exc)
    except ValueError as exc:
        return jsonify({"status": "error", "code": "INVALID_COST_ITEM", "message": str(exc)}), 400


@factory_parameters_bp.route("/factory_parameters/<factory_name>/cost-pools/<pool_id>/<item_id>/children", methods=["POST"])
@login_required
def reject_depth_four(factory_name, pool_id, item_id):
    result = _authorized(factory_name, "MODIFY")
    if isinstance(result, tuple) and isinstance(result[1], int): return result
    return jsonify({"status": "error", "code": "MAX_COST_DEPTH_EXCEEDED",
                    "message": "سطح سوم، سطح نهایی ساختار هزینه است."}), 400


@factory_parameters_bp.route("/factory_parameters/<factory_name>/category-weights", methods=["PUT"])
@login_required
def save_category_table(factory_name):
    result = _authorized(factory_name, "MODIFY")
    if isinstance(result, tuple) and isinstance(result[1], int): return result
    _, root = result; payload = request.get_json(force=True)
    _atomic_json(root / "configuration" / "category_weights.json", payload)
    return jsonify({"status": "success"})


@factory_parameters_bp.route("/factory_parameters/<factory_name>/production-prediction", methods=["PUT"])
@login_required
def save_prediction_production_per_capita(factory_name):
    result = _authorized(factory_name, "MODIFY")
    if isinstance(result, tuple) and isinstance(result[1], int): return result
    _, root = result; payload = request.get_json(force=True)
    _atomic_json(root / "configuration" / "production_prediction.json", payload)
    return jsonify({"status": "success"})
