from flask import Blueprint, abort, g, render_template, jsonify, request
from utils.auth import get_profile_store, login_required
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
from utils.product_hierarchy_service import HierarchyMetadataError, HierarchySelectionError, ProductHierarchyService

dashboard_bp = Blueprint("dashboard", __name__)

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
    """Return an honest empty report until canonical transactional data exists."""
    factory_id = request.args.get("factory")
    if factory_id:
        try:
            FactoryService(get_profile_store()).require_access(factory_id, g.current_user, "dashboard")
        except FactoryNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
            return jsonify({"error": str(exc)}), 403
    else:
        return jsonify({"state": "NOT_SELECTED", "message": "انتخاب یک کارخانه الزامی است."}), 400
    return jsonify({
        "state": "NOT_IMPLEMENTED",
        "message": "محاسبه هزینه در این نسخه فعال نیست.",
        "kpis": None,
        "breakdown_by_category": [],
        "breakdown_by_subcategory": [],
        "detail_breakdown": [],
    }), 501
