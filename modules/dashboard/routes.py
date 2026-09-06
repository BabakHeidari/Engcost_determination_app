from flask import Blueprint, g, render_template, jsonify, request
from utils.auth import get_profile_store, login_required
from utils.factory_service import FactoryAccessDeniedError, FactoryInactiveError, FactoryNotFoundError, FactoryService
from utils.localization import display_value

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    factories = FactoryService(get_profile_store()).get_accessible_factories(g.current_user, "DASHBOARD")
    filter_options = {
        "factories": factories,
        "categories": [display_value(v, "categories") for v in ["کاتد", "آند", "الکترولیت", "جداکننده", "بسته‌بندی"]]
    }

    return render_template("dashboard/dashboard.html",
                           filter_options=filter_options)

@dashboard_bp.route("/api/cost_analysis")
@login_required
def cost_analysis():
    """Return an honest empty report until canonical transactional data exists."""
    factory_id = request.args.get("factory")
    if factory_id:
        try:
            FactoryService(get_profile_store()).require_access(factory_id, g.current_user, "DASHBOARD")
        except FactoryNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except (FactoryAccessDeniedError, FactoryInactiveError) as exc:
            return jsonify({"error": str(exc)}), 403
    return jsonify({
        "kpis": {"total_cost": 0, "avg_cost_per_product": 0, "product_count": 0, "top_cost_driver": "—"},
        "breakdown_by_category": [],
        "breakdown_by_subcategory": [],
        "detail_breakdown": [],
    })
