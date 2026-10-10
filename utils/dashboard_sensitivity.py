"""Authorized, request-scoped what-if inputs for the shared costing engine.

Parameter identifiers are public identifiers, never grants or source selectors.
Only the private registry maps them onto the immutable engine snapshot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from types import MappingProxyType

from utils.costing_engine import (
    FORMULA_VERSION, CostInputError, CostInputLoader,
    CostOverrides, CostState, calculate_cost,
)
from utils.dashboard_analysis import DashboardAnalysisService, safe_issue
from utils.product_hierarchy_service import ALL, ProductHierarchyService, HierarchySelectionError
from utils.profile_authorization import has_access


VERSION = "1"
MAX_OVERRIDES = 64
MAX_DECIMAL_LENGTH = 128
DECIMAL_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z", re.ASCII)
IRR = "IRR - Iranian Rial"
ZERO = Decimal(0)
MODES = ("absolute", "percent_change")
POOL_LABELS = {
    "AdministrativeandResearch": "هزینه اداری و تحقیقاتی کل کارخانه (فرضی)",
    "Payroll": "حقوق و دستمزد کل کارخانه (فرضی)",
    "Overhead": "سربار کل کارخانه (فرضی)",
    "FinancialCosts": "هزینه مالی کل کارخانه (فرضی)",
    "Depriciation": "استهلاک کل کارخانه (فرضی)",
    "NonOperationalCostsandIncomes": "هزینه و درآمد غیرعملیاتی کل کارخانه (فرضی)",
}


class SensitivityRequestError(ValueError):
    """A safe request failure; never retain posted values or exception text."""

    def __init__(self, state, code, status=400):
        super().__init__("درخواست سناریو معتبر یا مجاز نیست.")
        self.state, self.code, self.status = state, code, status


def empty_sensitivity(state, *, issues=()):
    return {
        "version": VERSION, "formula_version": FORMULA_VERSION, "state": state,
        "identity": None, "period": None, "calculated_at": None,
        "source_lineage": [], "non_persistent": True, "permissions": {},
        "parameters": [], "unsupported_parameters": [],
        "baseline": None, "scenario": None, "delta": None,
        "effective_overrides": [], "issues": list(issues),
    }


def _identifier(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _period(period):
    return {"id": period.period_id, "start": period.start.isoformat(),
            "end": period.end.isoformat()}


def _group_for_id(parameter_id):
    prefix = parameter_id.partition(":")[0]
    if prefix in {"material", "fx"}:
        return "general_parameters"
    if prefix in {"pool", "category_share", "prediction"}:
        return "factory_parameters"
    return None


def _source_group(source):
    if source == "materials":
        return "general_parameters"
    if source in {"weights", "predictions", "configuration"} or source.startswith("pool:"):
        return "factory_parameters"
    return None


@dataclass(frozen=True)
class _Parameter:
    public: dict
    # Canonical document + numeric source coordinate; never serialized.
    source_key: tuple
    material_rows: tuple[str, ...] = ()
    currencies: tuple[str, ...] = ()
    pool_ids: tuple[str, ...] = ()
    category_share: bool = False
    prediction_identity: object | None = None


class DashboardSensitivityService:
    """One authorized identity, period and loader per HTTP request."""

    def __init__(self, factory_service, *, data_root=None, period_bindings_path=None):
        self.factory_service = factory_service
        self.loader = CostInputLoader(factory_service, data_root=data_root,
                                      period_bindings_path=period_bindings_path,
                                      read_only=True)

    def parameters(self, factory_id, user, *, category=None, subcategory=None,
                   product=None, period_id="", start=None, end=None):
        inputs, baseline, registry, unsupported, permissions = self._capture(
            factory_id, user, category, subcategory, product, period_id, start, end)
        return self._report(inputs, baseline, registry, unsupported, permissions)

    def scenario(self, factory_id, user, *, overrides, category=None,
                 subcategory=None, product=None, period_id="", start=None, end=None):
        # Authorization and syntactic group checks precede operational reads.
        self.factory_service.require_access(factory_id, user, "dashboard")
        permissions = self._permissions(factory_id, user)
        parsed = self._parse_overrides(overrides, permissions)
        inputs, baseline, registry, unsupported, permissions = self._capture(
            factory_id, user, category, subcategory, product, period_id, start, end)
        report = self._report(inputs, baseline, registry, unsupported, permissions)
        try:
            normalized, effective = self._normalize(inputs, parsed, registry)
            scenario = calculate_cost(inputs, normalized)
            if scenario.state is not CostState.OK:
                code = scenario.errors[0].code if scenario.errors else "SCENARIO_UNAVAILABLE"
                if scenario.state is CostState.CALCULATION_ERROR:
                    raise SensitivityRequestError("CALCULATION_ERROR", "SCENARIO_CALCULATION_FAILED", 500)
                raise SensitivityRequestError("INVALID_REQUEST", code)
            prediction = normalized.product_predictions.get(inputs.identity, inputs.product_prediction)
            report["scenario"] = self._result(scenario, prediction, permissions)
            amount = scenario.value - baseline.value
            report["delta"] = {
                "amount": amount, "percentage": amount / baseline.value * 100 if baseline.value else None,
                "percentage_state": "OK" if baseline.value else "NOT_APPLICABLE",
                "unit": "IRR/product", "direction": "scenario_minus_baseline",
            }
            report["effective_overrides"] = effective
        except SensitivityRequestError as exc:
            self._attach_scenario_failure(exc, report, inputs.identity, permissions)
            raise
        except (ArithmeticError, InvalidOperation):
            exc = SensitivityRequestError("CALCULATION_ERROR", "SCENARIO_CALCULATION_FAILED", 500)
            self._attach_scenario_failure(exc, report, inputs.identity, permissions)
            raise exc from None
        return report

    def _attach_scenario_failure(self, error, report, identity, permissions):
        state = "CALCULATION_ERROR" if error.status == 500 else "INVALID_INPUT"
        issue = safe_issue(state, error.code, identity)
        report.update(state=error.state, scenario=self._unavailable_result(state, issue, permissions),
                      effective_overrides=[], delta=None, issues=[issue])
        error.public_report = report

    @staticmethod
    def _permissions(factory_id, user):
        return {
            "general_parameters": has_access(user, "general_parameters", "READ", scope_type="GLOBAL"),
            "factory_parameters": has_access(user, "factory_parameters", "READ", factory_id,
                                             scope_type="FACTORY"),
        }

    def _capture(self, factory_id, user, category, subcategory, product, period_id, start, end):
        factory = self.factory_service.require_access(factory_id, user, "dashboard")
        permissions = self._permissions(factory_id, user)
        selections = (category, subcategory, product, period_id)
        if any(value is None or value == "" for value in selections):
            raise SensitivityRequestError("NOT_SELECTED", "EXPLICIT_SELECTION_REQUIRED")
        if any(not isinstance(value, str) or value != value.strip() or len(value) > 2048
               or any(ord(char) < 32 for char in value) for value in selections):
            raise SensitivityRequestError("INVALID_SELECTION", "MALFORMED_SELECTION")
        if ALL in selections or factory_id == ALL:
            raise SensitivityRequestError("INVALID_SELECTION", "ONE_CONFIGURATION_REQUIRED")
        operational = self.factory_service.operational_key(factory)
        identity, period, inputs = None, None, None
        try:
            population = self.loader.snapshot_population(factory_id, user, module="dashboard")
            hierarchy = ProductHierarchyService(self.loader.data_root / "Factories", catalog=population)
            options = hierarchy.options(operational, category=category, subcategory=subcategory, product=product)
            references = {item["id"]: item for item in options["options"]["products"]}
            selected = references.get(product)
            if selected is None:
                raise HierarchySelectionError("پیکربندی انتخاب‌شده معتبر نیست.")
            identities = [item for item in population if item.category == category
                          and item.subcategory == subcategory and item.product == selected["label"]]
            if len(identities) != 1:
                raise HierarchySelectionError("انتخاب باید به یک پیکربندی یکتا برسد.")
            identity = identities[0]
            period = self.loader.resolve_period(factory_id, period_id, start=start, end=end)
            inputs = self.loader.load(factory_id, user, identity, period.period_id, module="dashboard")
            if len({line.row_id for line in inputs.bom_lines}) != len(inputs.bom_lines):
                raise CostInputError(CostState.AMBIGUOUS_INPUT, "BOM_ROW_ID_NOT_UNIQUE",
                                     "هویت ردیف‌های ورودی یکتا نیست.", "bom")
            baseline = calculate_cost(inputs)
            if baseline.state is not CostState.OK:
                code = baseline.errors[0].code if baseline.errors else "BASELINE_UNAVAILABLE"
                raise CostInputError(baseline.state, code, "خط‌مبنا قابل محاسبه نیست.")
            registry, unsupported = self._registry(inputs, operational, permissions, baseline)
        except CostInputError as exc:
            source = exc.detail.source or ""
            group = _source_group(source)
            if not group:
                code = exc.detail.code
                if "MATERIAL" in code or "FX" in code:
                    group = "general_parameters"
                elif "PREDICTION" in code or "SHARE" in code or "CONFIGURATION" in code:
                    group = "factory_parameters"
            # A typed availability state is shared; protected validation details
            # and exception source references are never echoed to another group.
            period_codes = {"PERIOD_NOT_BOUND", "PERIOD_MISMATCH", "INVALID_PERIOD_BINDING",
                            "INVALID_PERIOD", "INVALID_PERIOD_RANGE"}
            code = exc.detail.code if ((group and permissions[group])
                                       or source in {"bom", "period_binding"}
                                       or exc.detail.code in period_codes) else "BASELINE_UNAVAILABLE"
            public_error = CostInputError(exc.state, code, "ورودی معتبر برای خط‌مبنا در دسترس نیست.")
            issue = safe_issue(exc.state.value, code, identity)
            report = empty_sensitivity(exc.state.value, issues=[issue])
            report.update(identity=asdict(identity) if identity else None,
                          period=_period(period) if period else None, permissions=permissions,
                          calculated_at=self.loader._loaded_at.isoformat())
            report["baseline"] = self._unavailable_result(exc.state.value, issue, permissions)
            sources = inputs.provenance if inputs is not None else ()
            lineage = {source.source: source for source in sources}
            for source in self.loader.snapshot_lineage():
                if source.source in {"period_binding", "configuration"}:
                    lineage[source.source] = source
            report["source_lineage"] = [DashboardAnalysisService._lineage(source)
                                        for name, source in lineage.items()
                                        if _source_group(name) is None or permissions[_source_group(name)]]
            public_error.public_report = report
            raise public_error from None
        return inputs, baseline, registry, unsupported, permissions

    def _registry(self, inputs, operational, permissions, baseline):
        result = {}
        unsupported = [{"parameter_type": "historical_bom_cost", "reason": "NOT_A_LIVE_INPUT",
                        "message": "هزینه تاریخی ذخیره‌شده ورودی بازمحاسبه نیست."}]
        paths = self.loader._source_paths(operational, inputs.identity)
        provenance = {source.source: source for source in inputs.provenance}
        period = _period(inputs.period)

        def add(parameter_id, group, label, unit, baseline, source_key, source, dependencies,
                *, minimum=ZERO, minimum_exclusive=False, maximum=None, zero_effect=False,
                scope="selected_configuration", **targets):
            metadata = {
                "parameter_id": parameter_id, "group": group, "label": label,
                "unit": unit, "numeric_type": "decimal", "baseline_value": baseline,
                "supported_modes": list(MODES),
                "domain": {"minimum": minimum, "minimum_exclusive": minimum_exclusive,
                           "maximum": maximum, "maximum_exclusive": False},
                "constraints": ["FINITE_DECIMAL", "VALID_BASELINE_REQUIRED"],
                "applicable": True, "editable": True, "reason": None,
                "effect_state": "MATHEMATICAL_ZERO" if zero_effect else "CONNECTED",
                "effect_context": "baseline_inputs_other_parameters_fixed",
                "scope": scope, "period": period,
                "source_reference": {"source": source, "record_id": parameter_id},
                "provenance": DashboardAnalysisService._lineage(provenance[source]),
                "dependencies": dependencies,
            }
            result[parameter_id] = _Parameter(metadata, source_key, **targets)

        if permissions["general_parameters"]:
            unsupported.append({"parameter_type": "irr_fx", "group": "general_parameters",
                                "reason": "FIXED_IRR_CONVERSION",
                                "message": "تبدیل ریال ثابت و غیرقابل تغییر است."})
            materials = sorted({line.material for line in inputs.bom_lines})
            currencies = sorted({line.price.currency for line in inputs.bom_lines if line.price.currency != IRR})
            for kind, names in (("material", materials), ("fx", currencies)):
                for name in names:
                    price_lines = tuple(line for line in inputs.bom_lines if line.material == name)
                    fx_lines = tuple(line for line in inputs.bom_lines if line.price.currency == name)
                    if kind == "material":
                        value = price_lines[0].price.unit_price
                        unit = f"{price_lines[0].price.currency}/{price_lines[0].price.unit}"
                        label = f"قیمت واحد ماده {name}"
                    else:
                        value = fx_lines[0].price.fx_rate
                        unit, label = f"IRR/{name}", f"نرخ تبدیل {name} به ریال"
                    # A currency row can itself occur as a material. Both public
                    # names map to that one source price and all its dependents.
                    if any(line.price.unit_price != value for line in price_lines) or any(line.price.fx_rate != value for line in fx_lines):
                        raise CostInputError(CostState.AMBIGUOUS_INPUT, "AMBIGUOUS_PARAMETER_MAPPING",
                                             "منبع پارامتر یکتا نیست.", "materials")
                    row_ids = tuple(line.row_id for line in price_lines)
                    fx_targets = (name,) if fx_lines else ()
                    dependencies = []
                    if row_ids:
                        dependencies.append({"kind": "material_unit_prices", "row_ids": list(row_ids)})
                    if fx_targets:
                        dependencies.append({"kind": "fx_rates", "currency": name,
                                             "row_ids": [line.row_id for line in fx_lines]})
                    def active_usage(line):
                        return line.usage > ZERO and not (
                            line.loss_percentage == 100 and line.recyclability_percentage == 100)

                    zero_effect = not (any(active_usage(line) for line in price_lines)
                                       or any(active_usage(line) and line.price.unit_price > ZERO
                                              for line in fx_lines))
                    add(f"{kind}:{_identifier(name)}", "general_parameters", label, unit, value,
                        (paths["materials"], "cost_per_unit_in_currency", name), "materials", dependencies,
                        minimum_exclusive=bool(fx_lines), zero_effect=zero_effect,
                        material_rows=row_ids, currencies=fx_targets)

        if permissions["factory_parameters"]:
            unsupported.append({"parameter_type": "v2_item_level_parameters", "group": "factory_parameters",
                                "reason": "UNAPPROVED_MAPPING",
                                "message": "پارامترهای ریز اقلام نسخه دوم نگاشت و معنای مصوب ندارند."})
            for pool in inputs.factory_pools:
                aliases = tuple(other.pool_id for other in inputs.factory_pools
                                if paths[f"pool:{other.pool_id}"] == paths[f"pool:{pool.pool_id}"])
                add(f"pool:{pool.pool_id}", "factory_parameters", POOL_LABELS[pool.pool_id],
                    "IRR/period", pool.raw_amount,
                    (paths[f"pool:{pool.pool_id}"], "cost", "whole_factory_total"),
                    f"pool:{pool.pool_id}", [{"kind": "factory_pool_amounts", "pool_ids": list(aliases)}],
                    scope="whole_factory_simulated", pool_ids=aliases)
            add(f"category_share:{_identifier(inputs.identity.category)}", "factory_parameters",
                "سهم فروش دسته انتخاب‌شده", "percent", inputs.category_share,
                (paths["weights"], "selling_share_of_category", inputs.identity.category), "weights",
                [{"kind": "category_share", "category": inputs.identity.category}],
                minimum_exclusive=True, maximum=Decimal(100),
                zero_effect=all(pool.raw_amount == ZERO for pool in inputs.factory_pools),
                scope="selected_category", category_share=True)
            # The installed legacy prediction column is keyed by name across
            # the whole factory. Equal names in another category also alias
            # that same source cell; full identity cannot be invented here.
            matching = [identity for identity in self.loader._populations[inputs.identity.factory_id]
                        if identity.product == inputs.identity.product]
            if len(matching) != 1:
                unsupported.append({"parameter_type": "selected_prediction", "group": "factory_parameters",
                                    "reason": "AMBIGUOUS_PREDICTION_MAPPING",
                                    "message": "منبع پیش‌بینی برای پیکربندی انتخاب‌شده مستقل و یکتا نیست."})
            else:
                identity_json = json.dumps(asdict(inputs.identity), sort_keys=True, ensure_ascii=False,
                                           separators=(",", ":"))
                add(f"prediction:{_identifier(identity_json)}", "factory_parameters",
                    "تعداد تولید پیش‌بینی‌شده پیکربندی انتخاب‌شده", "product/period", inputs.product_prediction,
                    (paths["predictions"], "Predicted Production", inputs.identity.product), "predictions",
                    [{"kind": "product_predictions", "identity": asdict(inputs.identity),
                      "allocation_population": "full_category_predictions"}],
                    zero_effect=all(pool.raw_amount == ZERO for pool in inputs.factory_pools)
                    and baseline.bom_total == ZERO,
                    prediction_identity=inputs.identity)
                result[f"prediction:{_identifier(identity_json)}"].public["constraints"].append(
                    "POSITIVE_FULL_CATEGORY_PREDICTION_DENOMINATOR")
        return result, unsupported

    @staticmethod
    def _parse_overrides(overrides, permissions):
        if not isinstance(overrides, list) or len(overrides) > MAX_OVERRIDES:
            raise SensitivityRequestError("INVALID_REQUEST", "INVALID_OVERRIDES_LIST")
        result, seen = [], set()
        for item in overrides:
            if not isinstance(item, dict) or set(item) != {"parameter_id", "mode", "value"}:
                raise SensitivityRequestError("INVALID_REQUEST", "INVALID_OVERRIDE_SCHEMA")
            parameter_id, mode, value = item["parameter_id"], item["mode"], item["value"]
            if not isinstance(parameter_id, str) or not parameter_id or len(parameter_id) > 256:
                raise SensitivityRequestError("INVALID_REQUEST", "INVALID_PARAMETER_ID")
            group = _group_for_id(parameter_id)
            if group is not None and not permissions[group]:
                raise SensitivityRequestError("FORBIDDEN", "PARAMETER_GROUP_FORBIDDEN", 403)
            if parameter_id in seen:
                raise SensitivityRequestError("INVALID_REQUEST", "DUPLICATE_PARAMETER_ID")
            seen.add(parameter_id)
            if not isinstance(mode, str) or mode not in MODES:
                raise SensitivityRequestError("INVALID_REQUEST", "UNSUPPORTED_OVERRIDE_MODE")
            if not isinstance(value, str) or len(value) > MAX_DECIMAL_LENGTH or not DECIMAL_PATTERN.fullmatch(value):
                raise SensitivityRequestError("INVALID_REQUEST", "INVALID_DECIMAL_VALUE")
            parsed = Decimal(value)
            if not parsed.is_finite():
                raise SensitivityRequestError("INVALID_REQUEST", "INVALID_DECIMAL_VALUE")
            result.append((parameter_id, mode, parsed))
        return result

    @staticmethod
    def _normalize(inputs, parsed, registry):
        prices, currencies, pools, predictions, effective = {}, {}, {}, {}, []
        share, sources = None, set()
        for parameter_id, mode, value in sorted(parsed):
            parameter = registry.get(parameter_id)
            if parameter is None:
                raise SensitivityRequestError("INVALID_REQUEST", "UNKNOWN_OR_UNAVAILABLE_PARAMETER")
            if parameter.source_key in sources:
                raise SensitivityRequestError("INVALID_REQUEST", "CONFLICTING_SOURCE_OVERRIDES")
            sources.add(parameter.source_key)
            metadata = parameter.public
            baseline = metadata["baseline_value"]
            try:
                final = value if mode == "absolute" else baseline * (Decimal(1) + value / Decimal(100))
            except (ArithmeticError, InvalidOperation):
                raise SensitivityRequestError("INVALID_REQUEST", "INVALID_FINAL_VALUE") from None
            domain = metadata["domain"]
            if not final.is_finite() or final < domain["minimum"] or (
                domain["minimum_exclusive"] and final == domain["minimum"]) or (
                domain["maximum"] is not None and final > domain["maximum"]):
                raise SensitivityRequestError("INVALID_REQUEST", "FINAL_VALUE_OUT_OF_DOMAIN")
            prices.update({row_id: final for row_id in parameter.material_rows})
            currencies.update({currency: final for currency in parameter.currencies})
            pools.update({pool_id: final for pool_id in parameter.pool_ids})
            if parameter.category_share:
                share = final
            if parameter.prediction_identity is not None:
                predictions[parameter.prediction_identity] = final
            effective.append({"parameter_id": parameter_id, "mode": mode, "value": value,
                              "baseline_value": baseline, "final_value": final,
                              "unit": metadata["unit"], "provenance_state": "HYPOTHETICAL_OVERRIDE"})
        denominator = sum((predictions.get(item.identity, item.quantity)
                           for item in inputs.category_predictions), ZERO)
        if denominator <= ZERO:
            raise SensitivityRequestError("INVALID_REQUEST", "INVALID_PREDICTION_DENOMINATOR")
        return CostOverrides(MappingProxyType(prices), MappingProxyType(currencies),
                             MappingProxyType(pools), share, MappingProxyType(predictions)), effective

    def _report(self, inputs, baseline, registry, unsupported, permissions):
        report = empty_sensitivity("OK")
        report.update(identity=asdict(inputs.identity), period=_period(inputs.period),
                      calculated_at=inputs.loaded_at.isoformat(), permissions=permissions,
                      parameters=[parameter.public for parameter in registry.values()],
                      unsupported_parameters=unsupported,
                      baseline=self._result(baseline, inputs.product_prediction, permissions))
        lineage = {source.source: source for source in inputs.provenance}
        for source in self.loader.snapshot_lineage():
            if source.source in {"configuration", "period_binding"}:
                lineage[source.source] = source
        report["source_lineage"] = [DashboardAnalysisService._lineage(source)
                                    for name, source in lineage.items()
                                    if _source_group(name) is None or permissions[_source_group(name)]]
        return report

    @staticmethod
    def _unavailable_result(state, issue, permissions):
        result = {
            "state": state, "unit_cost": None, "unit": "IRR/product",
            "projected_cost": None, "projected_cost_unit": "IRR/period",
            "projected_cost_scope": "single_configuration",
            "projected_cost_label": "هزینه پیش‌بینی‌شده همین پیکربندی",
            "bom_total": None, "driver_total": None,
            "breakdown": {"bom_components": [], "driver_components": []}, "issues": [issue],
        }
        if permissions["factory_parameters"]:
            result.update(prediction=None, prediction_unit="product/period")
        return result

    @staticmethod
    def _result(result, prediction, permissions):
        """Explicit exact whitelist; legacy to_dict and historical fields are absent."""
        drivers = []
        for item in result.driver_components:
            driver = {"pool_id": item.pool_id, "per_unit_contribution": item.per_unit_contribution,
                      "product_period_contribution": item.product_period_contribution}
            if permissions["factory_parameters"]:
                driver.update(raw_factory_pool=item.raw_factory_pool,
                              adjusted_category_pool=item.adjusted_category_pool,
                              category_prediction_total=item.category_prediction_total,
                              modeled_minus_raw=item.modeled_minus_raw)
            drivers.append(driver)
        output = {
            "state": result.state.value, "unit_cost": result.value, "unit": result.unit,
            "projected_cost": result.value * prediction,
            "projected_cost_unit": "IRR/period", "projected_cost_scope": "single_configuration",
            "projected_cost_label": "هزینه پیش‌بینی‌شده همین پیکربندی",
            "bom_total": result.bom_total, "driver_total": result.driver_total,
            "breakdown": {
                "bom_components": [{"row_id": item.row_id, "material": item.material,
                                    "live_cost_in_rial": item.live_cost_in_rial}
                                   for item in result.bom_components],
                "driver_components": drivers,
            },
            "issues": [],
        }
        if permissions["factory_parameters"]:
            output.update(prediction=prediction, prediction_unit="product/period")
        return output
