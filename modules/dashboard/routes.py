import logging
from datetime import date
from pathlib import Path

from flask import Blueprint, abort, current_app, g, render_template, jsonify, request
from utils.auth import get_profile_store, login_required
from utils.costing_engine import CostInputError
from utils.dashboard_analysis import DashboardAnalysisService, empty_report, safe_issue, serialize
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
from utils.product_hierarchy_service import HierarchyMetadataError, HierarchySelectionError, ProductHierarchyService

dashboard_bp = Blueprint("dashboard", __name__)
LOGGER = logging.getLogger(__name__)

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    factories = FactoryService(get_profile_store()).get_accessible_factories(g.current_user, "dashboard")
    if not factories:
        abort(403)
    return render_template("dashboard/dashboard.html",
                           filter_options={"factories": factories})


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
    """Analyze existing sources for one authorized factory without persistence."""
    allowed = {"factory", "category", "subcategory", "product", "period", "start", "end"}
    if set(request.args) - allowed or any(len(request.args.getlist(key)) != 1 for key in request.args):
        return jsonify(empty_report("INVALID_REQUEST", issues=[safe_issue(
            "INVALID_INPUT", "UNEXPECTED_QUERY_INPUT")])), 400
    factory_id = request.args.get("factory")
    if factory_id is None:
        return jsonify(empty_report("NOT_SELECTED")), 400
    if factory_id == "__ALL__":
        return jsonify(empty_report("INVALID_SELECTION", issues=[safe_issue(
            "INVALID_INPUT", "ONE_FACTORY_REQUIRED")])), 400
    if any(not value or value != value.strip() or len(value) > 2048 or any(ord(char) < 32 for char in value)
           for value in request.args.values()):
        return jsonify(empty_report("INVALID_SELECTION", issues=[safe_issue(
            "INVALID_INPUT", "EMPTY_OR_MALFORMED_SELECTION")])), 400
    if ("start" in request.args) != ("end" in request.args):
        return jsonify(empty_report("INVALID_REQUEST", issues=[safe_issue(
            "INVALID_INPUT", "INCOMPLETE_PERIOD_RANGE")])), 400
    if "start" in request.args:
        try:
            start, end = (date.fromisoformat(request.args[key]) for key in ("start", "end"))
            if start.isoformat() != request.args["start"] or end.isoformat() != request.args["end"] or start > end:
                raise ValueError("invalid date range")
        except ValueError:
            return jsonify(empty_report("INVALID_REQUEST", issues=[safe_issue(
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
        return jsonify(serialize(report)), status
    except FactoryNotFoundError:
        return jsonify(empty_report("UNKNOWN_FACTORY", issues=[safe_issue(
            "INVALID_INPUT", "FACTORY_NOT_FOUND")])), 404
    except (FactoryAccessDeniedError, FactoryInactiveError):
        return jsonify(empty_report("FORBIDDEN", issues=[safe_issue(
            "INVALID_INPUT", "FACTORY_FORBIDDEN")])), 403
    except HierarchySelectionError:
        return jsonify(empty_report("INVALID_SELECTION", issues=[safe_issue(
            "INVALID_INPUT", "INVALID_HIERARCHY_SELECTION")])), 400
    except HierarchyMetadataError:
        return jsonify(empty_report("UNAVAILABLE", issues=[safe_issue(
            "MISSING_INPUT", "HIERARCHY_UNAVAILABLE")])), 503
    except CostInputError as exc:
        return jsonify(empty_report(exc.state.value, issues=[safe_issue(exc.state.value, exc.detail.code)])), 422
    except Exception:
        LOGGER.exception("Dashboard analysis failed")
        return jsonify(empty_report("CALCULATION_ERROR", issues=[safe_issue(
            "CALCULATION_ERROR", "ANALYSIS_FAILED")])), 500
