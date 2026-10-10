"""Read-only public period choices for the authorized Dashboard page.

The analysis API already resolves installed bindings. This small presentation
adapter uses that same resolver (and its per-request read snapshot) so the page
does not invent periods or duplicate the costing lifecycle policy.
"""

from utils.costing_engine import CostInputError, CostInputLoader
from utils.dashboard_analysis import safe_issue


class DashboardPeriodMetadata:
    def __init__(self, factory_service, **loader_options):
        self.factory_service = factory_service
        self.loader = CostInputLoader(factory_service, read_only=True, **loader_options)

    def for_factory(self, factory_id, user):
        """Authorize before reading; expose only accepted IDs and date bounds."""
        self.factory_service.require_access(factory_id, user, "dashboard")
        result = {"options": [], "default_period_id": None,
                  "default_state": "MISSING_INPUT", "issues": []}
        try:
            default = self.loader.resolve_period(factory_id)
            result.update(default_period_id=default.period_id, default_state="OK")
        except CostInputError as exc:
            result["default_state"] = exc.state.value
            result["issues"].append(safe_issue(exc.state.value, exc.detail.code))

        # resolve_period above has already captured this exact binding document
        # or read failure. Do not independently reopen mutable binding data.
        try:
            document, _ = self.loader._read(self.loader.period_bindings_path)
        except CostInputError:
            return result
        bindings = document.get("bindings")
        if not isinstance(bindings, list) or any(not isinstance(item, dict) for item in bindings):
            return result
        identifiers = {
            item["period_id"] for item in bindings
            if item.get("factory_id") == factory_id
            and isinstance(item.get("period_id"), str) and item["period_id"]
        }
        for identifier in sorted(identifiers):
            try:
                period = self.loader.resolve_period(factory_id, identifier)
            except CostInputError:
                # Draft, unapproved, inactive, duplicate and malformed records
                # remain unavailable exactly as they do to the analysis API.
                continue
            result["options"].append({"id": period.period_id,
                                      "start": period.start.isoformat(),
                                      "end": period.end.isoformat()})
        return result
