import logging
import json
from datetime import date
from pathlib import Path

from flask import Blueprint, abort, current_app, g, render_template, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge
from utils.auth import get_profile_store, login_required
from utils.costing_engine import CostInputError
from utils.dashboard_analysis import DashboardAnalysisService, empty_report, safe_issue, serialize
from utils.dashboard_periods import DashboardPeriodMetadata
from utils.dashboard_visuals import cost_visuals
from utils.dashboard_visual_sensitivity import DashboardVisualSensitivityService
from utils.dashboard_sensitivity import (
    DashboardSensitivityService, SensitivityRequestError, empty_sensitivity,
)
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
from utils.product_hierarchy_service import HierarchyMetadataError, HierarchySelectionError, ProductHierarchyService

dashboard_bp = Blueprint("dashboard", __name__)
LOGGER = logging.getLogger(__name__)

SENSITIVITY_SELECTION_FIELDS = frozenset({
    "factory", "category", "subcategory", "product", "period", "start", "end",
})
SENSITIVITY_MAX_BODY_BYTES = 64 * 1024


def _sensitivity_json_object(pairs):
    """Reject duplicate JSON keys, including duplicates in override objects."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _sensitivity_request(*, scenario, visual=False):
    if scenario:
        if request.args or not request.is_json:
            raise SensitivityRequestError("INVALID_REQUEST", "EXPECTED_SCENARIO_JSON")
        if request.content_length is not None and request.content_length > SENSITIVITY_MAX_BODY_BYTES:
            raise SensitivityRequestError("INVALID_REQUEST", "PAYLOAD_TOO_LARGE", status=413)
        # Preserve a stricter application limit and cached body reads performed
        # by authentication/CSRF middleware. Flask also bounds chunked bodies.
        existing_limit = request.max_content_length
        request.max_content_length = (
            min(existing_limit, SENSITIVITY_MAX_BODY_BYTES)
            if existing_limit is not None else SENSITIVITY_MAX_BODY_BYTES
        )
        raw = request.get_data(cache=True)
        if len(raw) > SENSITIVITY_MAX_BODY_BYTES:
            raise SensitivityRequestError("INVALID_REQUEST", "PAYLOAD_TOO_LARGE", status=413)
        try:
            payload = json.loads(raw, object_pairs_hook=_sensitivity_json_object,
                                 parse_constant=lambda _value: _reject_json_constant())
        except (ValueError, UnicodeError, RecursionError):
            raise SensitivityRequestError("INVALID_REQUEST", "MALFORMED_SCENARIO_JSON") from None
        allowed_extra = {"scenarios", "experiment"} if visual else {"overrides"}
        if not isinstance(payload, dict) or set(payload) - (SENSITIVITY_SELECTION_FIELDS | allowed_extra):
            raise SensitivityRequestError("INVALID_REQUEST", "UNEXPECTED_SCENARIO_INPUT")
        if not visual and ("overrides" not in payload or not isinstance(payload["overrides"], list)):
            raise SensitivityRequestError("INVALID_REQUEST", "EXPECTED_OVERRIDES_LIST")
    else:
        if (set(request.args) - SENSITIVITY_SELECTION_FIELDS
                or any(len(request.args.getlist(key)) != 1 for key in request.args)):
            raise SensitivityRequestError("INVALID_REQUEST", "UNEXPECTED_QUERY_INPUT")
        payload = request.args.to_dict()

    if any(key not in payload for key in ("factory", "category", "subcategory", "product", "period")):
        raise SensitivityRequestError("NOT_SELECTED", "EXPLICIT_SELECTION_REQUIRED")
    for key in SENSITIVITY_SELECTION_FIELDS & set(payload):
        value = payload[key]
        if (not isinstance(value, str) or not value or value != value.strip()
                or len(value) > 2048 or any(ord(char) < 32 or ord(char) == 127 for char in value)
                or value == "__ALL__"):
            raise SensitivityRequestError("INVALID_SELECTION", "ONE_CONFIGURATION_REQUIRED")
    if ("start" in payload) != ("end" in payload):
        raise SensitivityRequestError("INVALID_REQUEST", "INCOMPLETE_PERIOD_RANGE")
    if "start" in payload:
        try:
            start, end = (date.fromisoformat(payload[key]) for key in ("start", "end"))
            if start.isoformat() != payload["start"] or end.isoformat() != payload["end"] or start > end:
                raise ValueError("invalid date range")
        except ValueError:
            raise SensitivityRequestError("INVALID_REQUEST", "INVALID_PERIOD_RANGE") from None
    return payload


def _reject_json_constant():
    raise ValueError("non-finite JSON constant")


def _sensitivity_response(*, scenario, visual=False):
    """Keep the established login/JSON POST lifecycle and typed HTTP outcomes."""
    try:
        payload = _sensitivity_request(scenario=scenario, visual=visual)

        class RegistrySnapshot:
            def __init__(self, factories):
                self.factories = factories

            def list_factories(self):
                return self.factories

        service = FactoryService(RegistrySnapshot(get_profile_store().list_factories()))
        service.require_access(payload["factory"], g.current_user, "dashboard")
        options = {}
        if current_app.config.get("COSTING_DATA_ROOT"):
            options["data_root"] = Path(current_app.config["COSTING_DATA_ROOT"])
        if current_app.config.get("COSTING_PERIOD_BINDINGS_FILE"):
            options["period_bindings_path"] = Path(current_app.config["COSTING_PERIOD_BINDINGS_FILE"])
        service_type = DashboardVisualSensitivityService if visual else DashboardSensitivityService
        sensitivity = service_type(service, **options)
        action = sensitivity.visual_analysis if visual else (sensitivity.scenario if scenario else sensitivity.parameters)
        arguments = {"category": payload["category"], "subcategory": payload["subcategory"],
                     "product": payload["product"], "period_id": payload["period"],
                     "start": payload.get("start"), "end": payload.get("end")}
        if visual:
            arguments.update(scenarios=payload.get("scenarios"), experiment=payload.get("experiment"))
        elif scenario:
            arguments["overrides"] = payload["overrides"]
        report = action(payload["factory"], g.current_user, **arguments)
        status = 200 if report["state"] == "OK" else (500 if report["state"] == "CALCULATION_ERROR" else 422)
        return jsonify(serialize(report)), status
    except SensitivityRequestError as exc:
        report = getattr(exc, "public_report", None) or empty_sensitivity(
            exc.state, issues=[safe_issue("INVALID_INPUT", exc.code)])
        return jsonify(serialize(report)), exc.status
    except RequestEntityTooLarge:
        return jsonify(empty_sensitivity("INVALID_REQUEST", issues=[safe_issue(
            "INVALID_INPUT", "PAYLOAD_TOO_LARGE")])), 413
    except FactoryNotFoundError:
        return jsonify(empty_sensitivity("UNKNOWN_FACTORY", issues=[safe_issue(
            "INVALID_INPUT", "FACTORY_NOT_FOUND")])), 404
    except (FactoryAccessDeniedError, FactoryInactiveError):
        return jsonify(empty_sensitivity("FORBIDDEN", issues=[safe_issue(
            "INVALID_INPUT", "FACTORY_FORBIDDEN")])), 403
    except HierarchySelectionError:
        return jsonify(empty_sensitivity("INVALID_SELECTION", issues=[safe_issue(
            "INVALID_INPUT", "INVALID_HIERARCHY_SELECTION")])), 400
    except HierarchyMetadataError:
        return jsonify(empty_sensitivity("UNAVAILABLE", issues=[safe_issue(
            "MISSING_INPUT", "HIERARCHY_UNAVAILABLE")])), 503
    except CostInputError as exc:
        report = getattr(exc, "public_report", None) or empty_sensitivity(
            exc.state.value, issues=[safe_issue(exc.state.value, exc.detail.code)])
        return jsonify(serialize(report)), 500 if exc.state.value == "CALCULATION_ERROR" else 422
    except Exception:
        LOGGER.exception("Dashboard sensitivity failed")
        return jsonify(empty_sensitivity("CALCULATION_ERROR", issues=[safe_issue(
            "CALCULATION_ERROR", "SENSITIVITY_FAILED")])), 500


@dashboard_bp.route("/api/dashboard/sensitivity/parameters", methods=["GET"])
@login_required
def sensitivity_parameters():
    return _sensitivity_response(scenario=False)


@dashboard_bp.route("/api/dashboard/sensitivity/scenario", methods=["POST"])
@login_required
def sensitivity_scenario():
    return _sensitivity_response(scenario=True)

@dashboard_bp.route("/api/dashboard/sensitivity/visual-analysis", methods=["POST"])
@login_required
def sensitivity_visual_analysis():
    return _sensitivity_response(scenario=True, visual=True)


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    service = FactoryService(get_profile_store())
    factories = service.get_accessible_factories(g.current_user, "dashboard")
    if not factories:
        abort(403)
    loader_options = {}
    if current_app.config.get("COSTING_DATA_ROOT"):
        loader_options["data_root"] = Path(current_app.config["COSTING_DATA_ROOT"])
    if current_app.config.get("COSTING_PERIOD_BINDINGS_FILE"):
        loader_options["period_bindings_path"] = Path(current_app.config["COSTING_PERIOD_BINDINGS_FILE"])
    metadata = DashboardPeriodMetadata(service, **loader_options)
    return render_template("dashboard/dashboard.html",
                           filter_options={"factories": factories,
                                           "periods_by_factory": {
                                               factory["id"]: metadata.for_factory(factory["id"], g.current_user)
                                               for factory in factories}})


@dashboard_bp.route("/api/dashboard/filter-options")
@login_required
def filter_options():
    """Return v1 hierarchy options for one authorized canonical factory."""
    factory_id = request.args.get("factory")
    if not factory_id:
        return jsonify({"version": "1", "state": "NOT_SELECTED", "message": "انتخاب کارخانه الزامی است."}), 400
    service = FactoryService(get_profile_store())
    try:
        factory = service.require_access(factory_id, g.current_user, "dashboard")
        # Resolve operational data only after canonical existence, active-state,
        # and Dashboard-specific access checks have all succeeded.
        operational_key = service.operational_key(factory)
        result = ProductHierarchyService().options(
            operational_key,
            category=request.args.get("category"),
            subcategory=request.args.get("subcategory"),
            product=request.args.get("product"),
        )
    except FactoryNotFoundError as exc:
        return jsonify({"version": "1", "state": "UNKNOWN_FACTORY", "message": str(exc)}), 404
    except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
        return jsonify({"version": "1", "state": "FORBIDDEN", "message": str(exc)}), 403
    except HierarchySelectionError as exc:
        return jsonify({"version": "1", "state": "INVALID_SELECTION", "message": str(exc)}), 400
    except HierarchyMetadataError as exc:
        return jsonify({"version": "1", "state": "UNAVAILABLE", "message": str(exc)}), 503
    result.update({"version": "1", "factory": factory})
    return jsonify(result)

@dashboard_bp.route("/api/cost_analysis")
@login_required
def cost_analysis():
    return _cost_analysis_response()


@dashboard_bp.route("/api/dashboard/cost-analysis/visuals")
@login_required
def cost_analysis_visuals():
    return _cost_analysis_response(visual=True)


def _cost_analysis_response(*, visual=False):
    """Build canonical analysis once; chart derivation reads only this report."""
    def respond(report):
        payload = {"version": "1", "analysis": report, "visuals": cost_visuals(report)} if visual else report
        return jsonify(serialize(payload))
    allowed = {"factory", "category", "subcategory", "product", "period", "start", "end"}
    if set(request.args) - allowed or any(len(request.args.getlist(key)) != 1 for key in request.args):
        return respond(empty_report("INVALID_REQUEST", issues=[safe_issue(
            "INVALID_INPUT", "UNEXPECTED_QUERY_INPUT")])), 400
    factory_id = request.args.get("factory")
    if factory_id is None:
        return respond(empty_report("NOT_SELECTED")), 400
    if factory_id == "__ALL__":
        return respond(empty_report("INVALID_SELECTION", issues=[safe_issue(
            "INVALID_INPUT", "ONE_FACTORY_REQUIRED")])), 400
    if any(not value or value != value.strip() or len(value) > 2048 or any(ord(char) < 32 for char in value)
           for value in request.args.values()):
        return respond(empty_report("INVALID_SELECTION", issues=[safe_issue(
            "INVALID_INPUT", "EMPTY_OR_MALFORMED_SELECTION")])), 400
    if ("start" in request.args) != ("end" in request.args):
        return respond(empty_report("INVALID_REQUEST", issues=[safe_issue(
            "INVALID_INPUT", "INCOMPLETE_PERIOD_RANGE")])), 400
    if "start" in request.args:
        try:
            start, end = (date.fromisoformat(request.args[key]) for key in ("start", "end"))
            if start.isoformat() != request.args["start"] or end.isoformat() != request.args["end"] or start > end:
                raise ValueError("invalid date range")
        except ValueError:
            return respond(empty_report("INVALID_REQUEST", issues=[safe_issue(
                "INVALID_INPUT", "INVALID_PERIOD_RANGE")])), 400
    # Capture the registry once: repeated authorization inside the loader sees
    # exactly the same factories, without opening further mutable store reads.
    class RegistrySnapshot:
        def __init__(self, factories):
            self.factories = factories

        def list_factories(self):
            return self.factories

    try:
        service = FactoryService(RegistrySnapshot(get_profile_store().list_factories()))
        service.require_access(factory_id, g.current_user, "dashboard")
        options = {}
        if current_app.config.get("COSTING_DATA_ROOT"):
            options["data_root"] = Path(current_app.config["COSTING_DATA_ROOT"])
        if current_app.config.get("COSTING_PERIOD_BINDINGS_FILE"):
            options["period_bindings_path"] = Path(current_app.config["COSTING_PERIOD_BINDINGS_FILE"])
        report = DashboardAnalysisService(service, **options).analyze(
            factory_id, g.current_user, category=request.args.get("category"),
            subcategory=request.args.get("subcategory"), product=request.args.get("product"),
            period_id=request.args.get("period", ""), start=request.args.get("start"), end=request.args.get("end"),
        )
        status = 400 if report["state"] == "NOT_SELECTED" else (
            200 if report["state"] in {"OK", "PARTIAL", "NO_MATCH"} else 422)
        return respond(report), status
    except FactoryNotFoundError:
        return respond(empty_report("UNKNOWN_FACTORY", issues=[safe_issue(
            "INVALID_INPUT", "FACTORY_NOT_FOUND")])), 404
    except (FactoryAccessDeniedError, FactoryInactiveError):
        return respond(empty_report("FORBIDDEN", issues=[safe_issue(
            "INVALID_INPUT", "FACTORY_FORBIDDEN")])), 403
    except HierarchySelectionError:
        return respond(empty_report("INVALID_SELECTION", issues=[safe_issue(
            "INVALID_INPUT", "INVALID_HIERARCHY_SELECTION")])), 400
    except HierarchyMetadataError:
        return respond(empty_report("UNAVAILABLE", issues=[safe_issue(
            "MISSING_INPUT", "HIERARCHY_UNAVAILABLE")])), 503
    except CostInputError as exc:
        return respond(empty_report(exc.state.value, issues=[safe_issue(exc.state.value, exc.detail.code)])), 422
    except Exception:
        LOGGER.exception("Dashboard analysis failed")
        return respond(empty_report("CALCULATION_ERROR", issues=[safe_issue(
            "CALCULATION_ERROR", "ANALYSIS_FAILED")])), 500
