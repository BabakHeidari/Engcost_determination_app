"""Request-scoped, non-persistent Dashboard analysis using the shared engine."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from utils.costing_engine import (
    FACTORY_POOL_IDS, FORMULA_VERSION, CostInputError, CostInputLoader, CostState,
    calculate_cost,
)
from utils.product_hierarchy_service import ALL, ProductHierarchyService


VERSION = "1"
ZERO = Decimal(0)
SAFE_MESSAGES = {
    "ALIASED_EXPERIMENT_PARAMETERS": "عامل‌های آزمایش یک منبع مشترک را کنترل می‌کنند و مستقل نیستند؛ دو پارامتر با منبع متفاوت انتخاب کنید.",
    "DUPLICATE_PARAMETER_ID": "یک پارامتر نباید در همان سناریو یا محور آزمایش تکرار شود.",
    "CONFLICTING_SOURCE_OVERRIDES": "دو تغییر پیشنهادی به یک منبع مشترک اشاره دارند؛ یکی را حذف کنید.",
    "SAMPLE_OUT_OF_DOMAIN": "نقطه آزمایش خارج از دامنه معتبر ورودی است و صفر محسوب نمی‌شود.",
    "PERIOD_NOT_BOUND": "دوره معتبر و فعال برای این کارخانه موجود نیست.",
    "PERIOD_MISMATCH": "بازه درخواست با دوره ثبت‌شده مطابقت ندارد.",
    "INVALID_PERIOD_BINDING": "تنظیمات دوره برنامه‌ریزی معتبر نیست.",
    "SOURCE_UNAVAILABLE": "یکی از منابع لازم در دسترس نیست.",
    "CONFIGURATION_NOT_INSTALLED": "پیکربندی نسخه دوم کارخانه نصب نشده است.",
}


def safe_issue(state, code, identity=None):
    """Never serialize loader diagnostics, exception text or filesystem paths."""
    result = {"state": state, "code": code,
              "message": SAFE_MESSAGES.get(code, "ورودی لازم برای محاسبه کامل یا معتبر نیست.")}
    if identity is not None:
        result["identity"] = asdict(identity)
    return result


def serialize(value):
    """Keep engine Decimal precision at the JSON boundary."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    return value


def empty_report(state, *, scope=None, period=None, calculated_at=None, issues=()):
    return {
        "version": VERSION, "formula_version": FORMULA_VERSION, "state": state,
        "scope": scope, "period": period, "calculated_at": calculated_at,
        "source_lineage": [],
        "coverage": {"configured": 0, "calculated": 0, "excluded": 0, "percentage": None},
        "kpis": {
            "matched_configuration_count": 0, "projected_total": None,
            "partial_total": None, "partial_total_label": None,
            "units": {"matched_configuration_count": "configuration",
                      "projected_total": "IRR/period", "partial_total": "IRR/period"},
            "weighted_average": {"state": state, "value": None, "numerator": None,
                                 "denominator": None, "unit": "IRR/product",
                                 "population": "selected_calculated_configurations"},
            "top_cost_driver": {"state": state, "id": None, "value": None,
                                "share": None, "tie": None, "tied_ids": []},
        },
        "breakdowns": {"products": [], "drivers": [], "factory_pools": []},
        "arithmetic_reconciliation": None,
        "detail_rows": [], "issues": list(issues),
    }


class DashboardAnalysisService:
    """One authorized factory, one binding, one population and one source snapshot."""

    def __init__(self, factory_service, *, data_root=None, period_bindings_path=None):
        self.factory_service = factory_service
        self.loader = CostInputLoader(factory_service, data_root=data_root,
                                      period_bindings_path=period_bindings_path, read_only=True)

    def analyze(self, factory_id, user, *, category=None, subcategory=None,
                product=None, period_id="", start=None, end=None):
        factory = self.factory_service.require_access(factory_id, user, "dashboard")
        scope = {"factory": factory, "selection": {
            "category": category, "subcategory": subcategory, "product": product},
            "population": "selected_configurations", "allocation_population": "full_category_predictions"}
        if any(item is None for item in (category, subcategory, product)):
            return empty_report("NOT_SELECTED", scope=scope)
        operational_key = self.factory_service.operational_key(factory)
        # Catalog and file reads occur only after factory-specific authorization.
        population = self.loader.snapshot_population(factory_id, user, module="dashboard")
        hierarchy = ProductHierarchyService(self.loader.data_root / "Factories", catalog=population)
        options = hierarchy.options(operational_key, category=category,
                                    subcategory=subcategory, product=product)
        references = {item["id"]: item for item in options["options"]["products"]}
        selected_paths = {(item["category"], item["subcategory"], item["label"])
                          for ref, item in references.items() if product == ALL or ref == product}
        selected = [item for item in population
                    if (item.category, item.subcategory, item.product) in selected_paths]
        now = datetime.now(timezone.utc).isoformat()
        report = empty_report("NO_MATCH", scope=scope, calculated_at=now)
        report["coverage"]["configured"] = len(selected)
        report["kpis"]["matched_configuration_count"] = len(selected)
        try:
            period = self.loader.resolve_period(factory_id, period_id, start=start, end=end)
        except CostInputError as exc:
            report["state"] = exc.state.value
            for key in ("weighted_average", "top_cost_driver"):
                report["kpis"][key]["state"] = report["state"]
            report["issues"] = [safe_issue(exc.state.value, exc.detail.code)]
            report["coverage"]["excluded"] = len(selected)
            report["coverage"]["percentage"] = ZERO if selected else None
            report["detail_rows"] = [self._excluded(item, exc.state.value, exc.detail.code) for item in selected]
            return report
        report["period"] = {"id": period.period_id, "start": period.start.isoformat(),
                            "end": period.end.isoformat()}
        if not selected:
            return report

        results, rows, lineage = [], [], {}
        for identity in selected:
            try:
                inputs = self.loader.load(factory_id, user, identity, period.period_id, module="dashboard")
                for source in inputs.provenance:
                    metadata = self._lineage(source)
                    if source.source == "bom":
                        metadata["identity"] = asdict(identity)
                    lineage[(source.source, source.fingerprint, identity if source.source == "bom" else None)] = metadata
                result = calculate_cost(inputs)
                if result.state is not CostState.OK:
                    first = result.errors[0]
                    rows.append(self._excluded(identity, result.state.value, first.code))
                    continue
                row = {
                    "identity": asdict(identity), "state": "OK", "unit_cost": result.value,
                    "unit": result.unit, "prediction": inputs.product_prediction,
                    "prediction_unit": "product/period",
                    "projected_cost": result.value * inputs.product_prediction,
                    "projected_cost_unit": "IRR/period",
                    "bom_total": result.bom_total,
                    "bom_components": [asdict(item) for item in result.bom_components],
                    "driver_components": [asdict(item) for item in result.driver_components],
                    "issues": [],
                }
                rows.append(row)
                results.append((inputs, result, row))
            except CostInputError as exc:
                rows.append(self._excluded(identity, exc.state.value, exc.detail.code))
        # Binding and configuration fingerprints describe installed metadata,
        # independently of the source as-of and request calculation timestamp.
        for source in self.loader.snapshot_lineage():
            if source.source in {"period_binding", "configuration"}:
                lineage[(source.source, source.fingerprint, None)] = self._lineage(source)
        report["source_lineage"] = list(lineage.values())
        report["detail_rows"] = rows
        report["issues"] = [issue for row in rows for issue in row["issues"]]
        calculated, configured = len(results), len(selected)
        report["coverage"] = {"configured": configured, "calculated": calculated,
                              "excluded": configured - calculated,
                              "percentage": Decimal(calculated) * 100 / configured}
        if not results:
            states = {row["state"] for row in rows}
            report["state"] = next(iter(states)) if len(states) == 1 else "UNAVAILABLE"
            for key in ("weighted_average", "top_cost_driver"):
                report["kpis"][key]["state"] = report["state"]
            return report

        report["state"] = "OK" if calculated == configured else "PARTIAL"
        total = sum((row["projected_cost"] for _, _, row in results), ZERO)
        quantity = sum((inputs.product_prediction for inputs, _, _ in results), ZERO)
        kpis = report["kpis"]
        if report["state"] == "OK":
            kpis["projected_total"] = total
        else:
            kpis["partial_total"], kpis["partial_total_label"] = total, "مجموع جزئی"
        kpis["weighted_average"] = {
            "state": report["state"] if quantity else "NOT_APPLICABLE",
            "value": total / quantity if quantity else None,
            "numerator": total, "denominator": quantity, "unit": "IRR/product",
            "population": "selected_calculated_configurations",
            "coverage": report["coverage"],
        }
        driver_values = {"BOM": sum((result.bom_total * inputs.product_prediction
                                    for inputs, result, _ in results), ZERO)}
        pools = []
        for pool_id in FACTORY_POOL_IDS:
            components = [(inputs, next(item for item in result.driver_components if item.pool_id == pool_id))
                          for inputs, result, _ in results]
            modeled_selected = sum((item.product_period_contribution for _, item in components), ZERO)
            categories = {inputs.identity.category: item for inputs, item in components}
            raw = components[0][1].raw_factory_pool
            modeled_category = sum((item.adjusted_category_pool for item in categories.values()), ZERO)
            pools.append({
                "id": pool_id, "raw_total": raw, "raw_scope": "whole_factory",
                "modeled_selected_total": modeled_selected,
                "selected_minus_raw": modeled_selected - raw,
                "modeled_selected_scope": "selected_calculated_configurations",
                "modeled_category_total": modeled_category,
                "category_minus_raw": modeled_category - raw,
                "modeled_category_scope": "full_prediction_population_of_reported_categories",
                "categories": [{"category": name, "adjusted_pool": item.adjusted_category_pool,
                                "prediction_denominator": item.category_prediction_total}
                               for name, item in sorted(categories.items())],
                "unit": "IRR/period", "coverage": report["coverage"],
            })
            driver_values[pool_id] = modeled_selected
        report["breakdowns"] = {
            "products": [row for _, _, row in results],
            "drivers": [{"id": key, "value": value, "share": value / total * 100 if total else None,
                         "unit": "IRR/period", "population": "selected_calculated_configurations"}
                        for key, value in driver_values.items()],
            "factory_pools": pools,
        }
        # Owner clarification of decision 005 (2026-10-10): BOM is one driver
        # alongside the six exact pool IDs, ranked on this same population.
        maximum = max(abs(value) for value in driver_values.values())
        tied = sorted(key for key, value in driver_values.items() if abs(value) == maximum)
        winner = tied[0]
        kpis["top_cost_driver"] = {
            "state": report["state"], "id": winner, "value": driver_values[winner],
            "share": driver_values[winner] / total * 100 if total else None,
            "tie": len(tied) > 1, "tied_ids": tied, "unit": "IRR/period",
            "population": "selected_calculated_configurations", "coverage": report["coverage"],
        }
        # Repeating Decimal division and differing sum order can leave a final
        # context-digit residue. Report it explicitly; never reconcile raw pools
        # or change a calculated monetary contribution to conceal that residue.
        component_total = sum(driver_values.values(), ZERO)
        report["arithmetic_reconciliation"] = {
            "projected_rows_total": total, "driver_components_total": component_total,
            "difference": total - component_total, "unit": "IRR/period",
        }
        return report

    @staticmethod
    def _excluded(identity, state, code):
        return {"identity": asdict(identity), "state": state, "unit_cost": None,
                "unit": "IRR/product", "prediction": None, "prediction_unit": "product/period",
                "projected_cost": None, "projected_cost_unit": "IRR/period",
                "bom_total": None, "bom_components": [], "driver_components": [],
                "issues": [safe_issue(state, code, identity)]}

    @staticmethod
    def _lineage(source):
        return {"source": source.source, "fingerprint": source.fingerprint,
                "actual_as_of": source.actual_as_of.isoformat() if source.actual_as_of else None,
                "owner_assigned_baseline": source.owner_assigned_baseline.isoformat() if source.owner_assigned_baseline else None,
                "business_version": source.business_version}
