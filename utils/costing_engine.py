"""Typed, read-only costing inputs and deterministic V1 calculations.

File access belongs to :class:`CostInputLoader`; ``calculate_cost`` only
operates on immutable input records.  Monetary values remain ``Decimal``
throughout the domain layer and are not rounded here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from utils.factory_service import FactoryService
from utils.paths import parent_path


FORMULA_VERSION = "cost-v1-owner-approved-2026-09-27"
OWNER_LEGACY_BASELINE_DATE = date(2026, 9, 27)
FACTORY_POOL_IDS = (
    "AdministrativeandResearch",
    "Payroll",
    "Overhead",
    "FinancialCosts",
    "Depriciation",
    "NonOperationalCostsandIncomes",
)


class CostState(str, Enum):
    OK = "OK"
    MISSING_INPUT = "MISSING_INPUT"
    INVALID_INPUT = "INVALID_INPUT"
    AMBIGUOUS_INPUT = "AMBIGUOUS_INPUT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CALCULATION_ERROR = "CALCULATION_ERROR"


@dataclass(frozen=True)
class CostError:
    code: str
    message: str
    source: str | None = None


@dataclass(frozen=True)
class PlanningPeriod:
    period_id: str
    start: date
    end: date


@dataclass(frozen=True)
class SourceProvenance:
    source: str
    fingerprint: str
    actual_as_of: datetime | None = None
    owner_assigned_baseline: date | None = None
    business_version: str | None = None


@dataclass(frozen=True)
class ProductIdentity:
    factory_id: str
    category: str
    subcategory: str
    product: str


@dataclass(frozen=True)
class MaterialPrice:
    material: str
    unit: str
    currency: str
    unit_price: Decimal
    fx_rate: Decimal
    provenance: SourceProvenance


@dataclass(frozen=True)
class BomLineItem:
    row_id: str
    material: str
    usage: Decimal
    loss_percentage: Decimal
    recyclability_percentage: Decimal
    price: MaterialPrice
    historical_cost_in_rial: Decimal | None = None


@dataclass(frozen=True)
class FactoryPool:
    pool_id: str
    raw_amount: Decimal
    provenance: SourceProvenance


@dataclass(frozen=True)
class ProductPrediction:
    identity: ProductIdentity
    quantity: Decimal


@dataclass(frozen=True)
class CostInputs:
    identity: ProductIdentity
    period: PlanningPeriod
    bom_lines: tuple[BomLineItem, ...]
    factory_pools: tuple[FactoryPool, ...]
    category_share: Decimal
    product_prediction: Decimal
    category_predictions: tuple[ProductPrediction, ...]
    provenance: tuple[SourceProvenance, ...]
    loaded_at: datetime


@dataclass(frozen=True)
class CostOverrides:
    material_unit_prices: Mapping[str, Decimal] = field(default_factory=dict)
    fx_rates: Mapping[str, Decimal] = field(default_factory=dict)
    factory_pool_amounts: Mapping[str, Decimal] = field(default_factory=dict)
    category_share: Decimal | None = None
    product_predictions: Mapping[ProductIdentity, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class BomContribution:
    row_id: str
    material: str
    gross_cost_in_rial: Decimal
    adjustment_factor: Decimal
    live_cost_in_rial: Decimal
    historical_cost_in_rial: Decimal | None


@dataclass(frozen=True)
class DriverContribution:
    pool_id: str
    raw_factory_pool: Decimal
    adjusted_category_pool: Decimal
    category_prediction_total: Decimal
    per_unit_contribution: Decimal
    product_period_contribution: Decimal
    modeled_minus_raw: Decimal


@dataclass(frozen=True)
class CostResult:
    value: Decimal | None
    unit: str
    state: CostState
    bom_total: Decimal | None
    driver_total: Decimal | None
    bom_components: tuple[BomContribution, ...]
    driver_components: tuple[DriverContribution, ...]
    period: PlanningPeriod
    identity: ProductIdentity
    source_metadata: tuple[SourceProvenance, ...]
    formula_version: str
    calculated_at: datetime
    errors: tuple[CostError, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        def decimal(value: Decimal | None) -> str | None:
            return None if value is None else format(value, "f")

        def legacy_number(value: Decimal | None) -> int | float | None:
            if value is None:
                return None
            return int(value) if value == value.to_integral_value() else float(value)

        result = {
            "value": decimal(self.value), "unit": self.unit, "state": self.state.value,
            "bom_total": decimal(self.bom_total), "driver_total": decimal(self.driver_total),
            "period": {"id": self.period.period_id, "start": self.period.start.isoformat(), "end": self.period.end.isoformat()},
            "identity": self.identity.__dict__, "formula_version": self.formula_version,
            "calculated_at": self.calculated_at.isoformat(),
            "bom_components": [
                {"row_id": item.row_id, "material": item.material,
                 "gross_cost_in_rial": decimal(item.gross_cost_in_rial),
                 "adjustment_factor": decimal(item.adjustment_factor),
                 "live_cost_in_rial": decimal(item.live_cost_in_rial),
                 "historical_cost_in_rial": decimal(item.historical_cost_in_rial)}
                for item in self.bom_components
            ],
            "driver_components": [
                {key: (decimal(value) if isinstance(value, Decimal) else value)
                 for key, value in item.__dict__.items()} for item in self.driver_components
            ],
            "source_metadata": [
                {"source": item.source, "fingerprint": item.fingerprint,
                 "actual_as_of": item.actual_as_of.isoformat() if item.actual_as_of else None,
                 "owner_assigned_baseline": item.owner_assigned_baseline.isoformat() if item.owner_assigned_baseline else None,
                 "business_version": item.business_version}
                for item in self.source_metadata
            ],
            "errors": [item.__dict__ for item in self.errors],
        }
        # Compatibility fields keep the existing Cost Calculation UI working
        # while typed consumers use the explicit V1 fields above. Row IDs make
        # repeated material names lossless at this boundary.
        if self.state is CostState.OK:
            result.update({item.pool_id: legacy_number(item.per_unit_contribution) for item in self.driver_components})
            bom_details = {
                f"{item.row_id}:{item.material}": legacy_number(item.live_cost_in_rial)
                for item in self.bom_components
            }
            bom_details["Total_BOM_Cost"] = legacy_number(self.bom_total)
            result.update({
                "BOM": legacy_number(self.bom_total),
                "BOM_Details": bom_details,
                "Final_Production_Cost": legacy_number(self.value),
            })
        return result


class CostInputError(ValueError):
    def __init__(self, state: CostState, code: str, message: str, source: str | None = None,
                 diagnostic: dict[str, Any] | None = None):
        super().__init__(message)
        self.state, self.detail = state, CostError(code, message, source)
        self.diagnostic = diagnostic


def _decimal(value: Any, name: str, *, nonnegative: bool = True) -> Decimal:
    if isinstance(value, bool) or value in (None, ""):
        raise CostInputError(CostState.MISSING_INPUT, "MISSING_NUMERIC_INPUT", f"{name} is required")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_NUMBER", f"{name} must be numeric") from None
    if not result.is_finite() or (nonnegative and result < 0):
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_NUMBER", f"{name} is outside its valid range")
    return result


def calculate_live_bom_line(usage: Any, unit_price: Any, fx_rate: Any,
                            loss_percentage: Any, recyclability_percentage: Any) -> tuple[Decimal, Decimal, Decimal]:
    """Return gross cost, efficiency factor and live Rial cost for one row."""
    parsed_usage = _decimal(usage, "usage")
    price = _decimal(unit_price, "material unit price")
    fx = _decimal(fx_rate, "FX")
    loss = _decimal(loss_percentage, "loss percentage")
    recyclable = _decimal(recyclability_percentage, "recyclability percentage")
    if loss > 100 or recyclable > 100:
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_PERCENTAGE",
                             "loss and recyclability must be in [0, 100]")
    if fx <= 0:
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_FX_RATE", "applicable FX must be positive")
    gross = parsed_usage * price * fx
    factor = Decimal(1) - (loss / Decimal(100)) * (recyclable / Decimal(100))
    return gross, factor, gross * factor


def calculate_cost(inputs: CostInputs, overrides: CostOverrides | None = None) -> CostResult:
    """Calculate an approved V1 unit cost without reading or writing external state."""
    overrides = overrides or CostOverrides()
    try:
        share = _decimal(overrides.category_share if overrides.category_share is not None else inputs.category_share, "category share")
        if share <= 0 or share > 100:
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_CATEGORY_SHARE", "category share must be in (0, 100]")

        predictions = {
            item.identity: _decimal(overrides.product_predictions.get(item.identity, item.quantity), "prediction")
            for item in inputs.category_predictions
        }
        if inputs.identity not in predictions:
            raise CostInputError(CostState.MISSING_INPUT, "MISSING_PRODUCT_PREDICTION", "product prediction is absent")
        if not overrides.product_predictions and _decimal(inputs.product_prediction, "product prediction") != predictions[inputs.identity]:
            raise CostInputError(CostState.AMBIGUOUS_INPUT, "PREDICTION_DIVERGENCE",
                                 "resolved product prediction differs from category population")
        prediction_total = sum(predictions.values(), Decimal(0))
        if prediction_total <= 0:
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_PREDICTION_DENOMINATOR", "category prediction total must be positive")
        product_prediction = predictions[inputs.identity]

        bom_components = []
        for line in inputs.bom_lines:
            price = _decimal(overrides.material_unit_prices.get(line.row_id, line.price.unit_price), f"price[{line.row_id}]")
            fx = _decimal(overrides.fx_rates.get(line.price.currency, line.price.fx_rate), f"FX[{line.row_id}]")
            gross, factor, live = calculate_live_bom_line(
                line.usage, price, fx, line.loss_percentage, line.recyclability_percentage
            )
            bom_components.append(BomContribution(
                line.row_id, line.material, gross, factor, live, line.historical_cost_in_rial
            ))

        driver_components = []
        for pool in inputs.factory_pools:
            raw = _decimal(overrides.factory_pool_amounts.get(pool.pool_id, pool.raw_amount), f"pool[{pool.pool_id}]")
            adjusted = raw / (share / Decimal(100))
            per_unit = adjusted / prediction_total
            driver_components.append(DriverContribution(
                pool.pool_id, raw, adjusted, prediction_total, per_unit,
                per_unit * product_prediction, adjusted - raw,
            ))
        bom_total = sum((item.live_cost_in_rial for item in bom_components), Decimal(0))
        driver_total = sum((item.per_unit_contribution for item in driver_components), Decimal(0))
        return CostResult(bom_total + driver_total, "IRR/product", CostState.OK, bom_total, driver_total,
                          tuple(bom_components), tuple(driver_components), inputs.period, inputs.identity,
                          inputs.provenance, FORMULA_VERSION, inputs.loaded_at)
    except CostInputError as exc:
        return CostResult(None, "IRR/product", exc.state, None, None, (), (), inputs.period,
                          inputs.identity, inputs.provenance, FORMULA_VERSION, inputs.loaded_at, (exc.detail,))
    except (ArithmeticError, InvalidOperation) as exc:
        error = CostError("CALCULATION_FAILED", str(exc))
        return CostResult(None, "IRR/product", CostState.CALCULATION_ERROR, None, None, (), (), inputs.period,
                          inputs.identity, inputs.provenance, FORMULA_VERSION, inputs.loaded_at, (error,))


class CostInputLoader:
    """Resolve an authorized factory and create one stable, read-only snapshot."""

    def __init__(self, factory_service: FactoryService, *, data_root: Path | None = None,
                 period_bindings_path: Path | None = None):
        self.factory_service = factory_service
        self.data_root = Path(data_root or parent_path).resolve()
        self.period_bindings_path = Path(period_bindings_path or (self.data_root.parent / "instance" / "costing_period_bindings.json"))
        self._documents: dict[Path, tuple[dict, SourceProvenance]] = {}

    def load(self, factory_id: str, user: dict, identity: ProductIdentity, period_id: str,
             *, module: str = "cost_calculation") -> CostInputs:
        factory = self.factory_service.require_access(factory_id, user, module)
        operational_key = self.factory_service.operational_key(factory)
        factory_root = self._inside(self.data_root / "Factories" / operational_key)
        if identity.factory_id != factory_id:
            raise CostInputError(CostState.INVALID_INPUT, "FACTORY_ID_MISMATCH", "identity factory does not match authorized factory")
        period, approved_sources = self._period_binding(factory_id, period_id)
        paths = self._source_paths(operational_key, identity)
        missing_binding = sorted(set(paths) - approved_sources)
        if missing_binding:
            raise CostInputError(CostState.MISSING_INPUT, "UNBOUND_LEGACY_SOURCE",
                                 f"period binding does not approve sources: {', '.join(missing_binding)}")

        diagnostic = self._diagnostic(period, approved_sources, paths)
        missing = diagnostic["missing_sources"]
        if missing:
            first = missing[0]
            raise CostInputError(
                CostState.MISSING_INPUT, "SOURCE_UNAVAILABLE", first["reason"],
                first["expected_location"], diagnostic,
            )

        documents, provenance, provenance_by_name = {}, [], {}
        for name, path in paths.items():
            documents[name], source = self._read(path)
            provenance.append(source)
            provenance_by_name[name] = source
        materials = self._rows(documents["materials"], "materials", ("material", "unit", "currency", "cost_per_unit_in_currency"))
        by_material: dict[str, list[dict]] = {}
        for row in materials:
            by_material.setdefault(row["material"], []).append(row)

        bom_rows = self._rows(documents["bom"], "bom", ("materials", "usage", "lost_percentage", "recycability_percentage"))
        lines = []
        for index, row in enumerate(bom_rows):
            material = row["materials"]
            matches = by_material.get(material, [])
            if len(matches) != 1:
                state = CostState.MISSING_INPUT if not matches else CostState.AMBIGUOUS_INPUT
                raise CostInputError(state, "MATERIAL_PRICE_NOT_UNIQUE", f"material price must resolve exactly once: {material}")
            current = matches[0]
            currency = current["currency"]
            if currency == "IRR - Iranian Rial":
                fx = Decimal(1)
            else:
                fx_rows = by_material.get(currency, [])
                if len(fx_rows) != 1 or fx_rows[0]["currency"] != "IRR - Iranian Rial":
                    raise CostInputError(CostState.AMBIGUOUS_INPUT, "AMBIGUOUS_FX_MAPPING", f"FX mapping is not uniquely Rial-denominated: {currency}")
                fx = _decimal(fx_rows[0]["cost_per_unit_in_currency"], f"FX[{currency}]")
            historical = row.get("cost_of_material_in_rial")
            lines.append(BomLineItem(
                row_id=str(row.get("row_id") or f"row-{index + 1}"), material=material,
                usage=_decimal(row["usage"], f"usage[row-{index + 1}]"),
                loss_percentage=_decimal(row["lost_percentage"], f"loss[row-{index + 1}]"),
                recyclability_percentage=_decimal(row["recycability_percentage"], f"recyclability[row-{index + 1}]"),
                price=MaterialPrice(material, current["unit"], currency,
                                    _decimal(current["cost_per_unit_in_currency"], f"price[{material}]"), fx,
                                    provenance_by_name["materials"]),
                historical_cost_in_rial=None if historical in (None, "") else _decimal(historical, "historical cost"),
            ))

        weights = self._rows(documents["weights"], "weights", ("category", "selling_share_of_category"))
        matching_weights = [row for row in weights if row["category"] == identity.category]
        if len(matching_weights) != 1:
            raise CostInputError(CostState.AMBIGUOUS_INPUT, "CATEGORY_SHARE_NOT_UNIQUE", "category share must resolve exactly once")
        share = _decimal(matching_weights[0]["selling_share_of_category"], "category share")

        prediction_rows = self._rows(documents["predictions"], "predictions", ("Product Name", "Predicted Production"))
        category_products = self._category_products(factory_root / identity.category, factory_id, identity.category)
        predictions = []
        for product_identity in category_products:
            matches = [row for row in prediction_rows if row["Product Name"] == product_identity.product]
            if len(matches) != 1:
                raise CostInputError(CostState.AMBIGUOUS_INPUT, "PREDICTION_NOT_UNIQUE", f"prediction must resolve exactly once: {product_identity.product}")
            predictions.append(ProductPrediction(product_identity, _decimal(matches[0]["Predicted Production"], "prediction")))
        pools = []
        for pool_id in FACTORY_POOL_IDS:
            source_name = f"pool:{pool_id}"
            pool_rows = self._rows(documents[source_name], source_name, ("cost",))
            amount = sum((_decimal(row["cost"], f"pool[{pool_id}]") for row in pool_rows), Decimal(0))
            pools.append(FactoryPool(pool_id, amount, provenance_by_name[source_name]))
        target_prediction = next((item.quantity for item in predictions if item.identity == identity), None)
        if target_prediction is None:
            raise CostInputError(CostState.MISSING_INPUT, "MISSING_PRODUCT_PREDICTION", "requested product is outside category population")
        return CostInputs(identity, period, tuple(lines), tuple(pools), share, target_prediction, tuple(predictions),
                          tuple(provenance), datetime.now(timezone.utc))

    def diagnose_sources(self, factory_id: str, period_id: str = "",
                         identity: ProductIdentity | None = None) -> dict[str, Any]:
        """Compare active-period metadata with the exact paths the loader resolves."""
        factory = self.factory_service.get_factory(factory_id)
        if factory is None:
            raise CostInputError(CostState.MISSING_INPUT, "FACTORY_NOT_FOUND",
                                 "factory is absent from the canonical registry")
        period, approved_sources = self._period_binding(factory_id, period_id)
        paths = self._source_paths(self.factory_service.operational_key(factory), identity)
        return self._diagnostic(period, approved_sources, paths)

    def _source_paths(self, operational_key: str,
                      identity: ProductIdentity | None) -> dict[str, Path | tuple[Path, ...]]:
        factory_root = self._inside(self.data_root / "Factories" / operational_key)
        if identity is None:
            bom_path: Path | tuple[Path, ...] = tuple(sorted(
                path.resolve() for path in factory_root.glob("*/*/*.json")
                if not path.name.startswith("_")
            ))
        else:
            bom_path = self._inside(
                factory_root / identity.category / identity.subcategory / f"{identity.product}.json"
            )
        paths: dict[str, Path | tuple[Path, ...]] = {
            "materials": self._inside(self.data_root / "Overall" / "material_costs.json"),
            "bom": bom_path,
            "weights": self._inside(factory_root / "category_weights.json"),
            "predictions": self._inside(factory_root / "ProductionPrediction.json"),
        }
        for pool_id in FACTORY_POOL_IDS:
            paths[f"pool:{pool_id}"] = self._inside(factory_root / f"Factory_Data_{pool_id}.json")
        return paths

    def _display_path(self, path: Path) -> str:
        try:
            return str(Path(self.data_root.name) / path.relative_to(self.data_root))
        except ValueError:
            return str(path)

    def _diagnostic(self, period: PlanningPeriod, approved_sources: set[str],
                    paths: Mapping[str, Path | tuple[Path, ...]]) -> dict[str, Any]:
        resolutions = []
        for source_name in sorted(approved_sources):
            expected = paths.get(source_name)
            if isinstance(expected, tuple):
                found = [self._display_path(path) for path in expected if path.is_file()]
                expected_location = str(
                    Path(self.data_root.name) / "Factories" / "<operational-key>"
                    / "<category>" / "<subcategory>" / "<product>.json"
                )
            elif expected is not None:
                found = [self._display_path(expected)] if expected.is_file() else []
                expected_location = self._display_path(expected)
            else:
                found, expected_location = [], None
            if expected is None:
                reason = "source name is stored in the period but is not recognized by CostInputLoader"
            elif not found:
                reason = "file not found"
            else:
                reason = "file found"
            resolutions.append({
                "source_name": source_name,
                "expected_location": expected_location,
                "resolution_status": "AVAILABLE" if found else "MISSING",
                "actual_file_found": found[0] if len(found) == 1 else found or None,
                "reason": reason,
            })
        resolved = [item for item in resolutions if item["resolution_status"] == "AVAILABLE"]
        missing = [item for item in resolutions if item["resolution_status"] == "MISSING"]
        return {
            "active_period": {"period_id": period.period_id, "start": period.start.isoformat(),
                              "end": period.end.isoformat()},
            "required_sources": sorted(approved_sources),
            "loader_sources": sorted(paths),
            "resolved_sources": resolved,
            "missing_sources": missing,
            "source_resolutions": resolutions,
            "available_sources": [item["source_name"] for item in resolved],
        }

    def _period_binding(self, factory_id: str, period_id: str) -> tuple[PlanningPeriod, set[str]]:
        if not self.period_bindings_path.is_file():
            raise CostInputError(
                CostState.MISSING_INPUT, "PERIOD_NOT_BOUND",
                "owner-approved costing period configuration is not installed",
            )
        document, _ = self._read(self.period_bindings_path)
        matches = [
            item for item in document.get("bindings", [])
            if item.get("factory_id") == factory_id
            and item.get("approved") is True
            and item.get("status") == "ACTIVE"
            and item.get("active") is True
            and (item.get("period_id") == period_id if period_id else item.get("active") is True)
        ]
        if len(matches) != 1:
            raise CostInputError(CostState.MISSING_INPUT, "PERIOD_NOT_BOUND", "no unique owner-approved legacy period binding exists")
        item = matches[0]
        try:
            start, end = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
        except (KeyError, TypeError, ValueError):
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_PERIOD_BINDING", "period binding requires ISO start and end") from None
        if start > end:
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_PERIOD_BINDING", "period start must not follow end")
        return PlanningPeriod(item["period_id"], start, end), set(item.get("sources", []))

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved != self.data_root and self.data_root not in resolved.parents:
            raise CostInputError(CostState.INVALID_INPUT, "UNSAFE_SOURCE_PATH", "source path leaves the operational data root")
        return resolved

    def _read(self, path: Path) -> tuple[dict, SourceProvenance]:
        if path in self._documents:
            return self._documents[path]
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise CostInputError(CostState.MISSING_INPUT, "SOURCE_UNAVAILABLE", str(exc), str(path)) from None
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CostInputError(CostState.INVALID_INPUT, "SOURCE_PARSE_ERROR", str(exc), str(path)) from None
        if not isinstance(document, dict):
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_SOURCE_SCHEMA", "JSON root must be an object", str(path))
        actual = None
        raw_date = document.get("last_modification_date")
        if raw_date:
            try:
                actual = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
            except ValueError:
                raise CostInputError(CostState.INVALID_INPUT, "INVALID_SOURCE_DATE", "source date is malformed", str(path)) from None
        result = (document, SourceProvenance(str(path), hashlib.sha256(raw).hexdigest(), actual,
                                             None if actual else OWNER_LEGACY_BASELINE_DATE))
        self._documents[path] = result
        return result

    @staticmethod
    def _rows(document: dict, source: str, required: tuple[str, ...]) -> list[dict]:
        data = document.get("data")
        if not isinstance(data, dict) or any(not isinstance(data.get(key), list) for key in required):
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_SOURCE_SCHEMA", f"{source} has invalid column data")
        lengths = {len(data[key]) for key in required}
        if len(lengths) != 1:
            raise CostInputError(CostState.INVALID_INPUT, "COLUMN_LENGTH_MISMATCH", f"{source} columns have different lengths")
        optional = {key: value for key, value in data.items() if isinstance(value, list) and len(value) in lengths}
        return [{key: values[index] for key, values in optional.items()} for index in range(next(iter(lengths), 0))]

    @staticmethod
    def _category_products(category_root: Path, factory_id: str, category: str) -> tuple[ProductIdentity, ...]:
        products = []
        for path in sorted(category_root.glob("*/*.json")):
            if path.name.startswith("_"):
                continue
            products.append(ProductIdentity(factory_id, category, path.parent.name, path.stem))
        return tuple(products)


def validate_live_bom_payload(payload, material_document):
    """Validate BOM inputs and refresh historical preview fields before save."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_BOM_SCHEMA", "ساختار BOM معتبر نیست.")
    data = payload["data"]
    required = ("materials", "usage", "lost_percentage", "recycability_percentage")
    if any(not isinstance(data.get(key), list) for key in required):
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_BOM_SCHEMA", "ستون‌های الزامی BOM کامل نیستند.")
    lengths = {len(data[key]) for key in required}
    if len(lengths) != 1:
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_BOM_SCHEMA", "طول ستون‌های BOM یکسان نیست.")

    material_data = material_document.get("data", {}) if isinstance(material_document, dict) else {}
    material_fields = ("material", "unit", "currency", "cost_per_unit_in_currency")
    if any(not isinstance(material_data.get(key), list) for key in material_fields):
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_MATERIAL_SCHEMA", "منبع قیمت مواد معتبر نیست.")
    material_lengths = {len(material_data[key]) for key in material_fields}
    if len(material_lengths) != 1:
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_MATERIAL_SCHEMA", "ستون‌های منبع قیمت هم‌اندازه نیستند.")
    prices = {}
    for index, material in enumerate(material_data["material"]):
        prices.setdefault(material, []).append({key: material_data[key][index] for key in material_fields})

    row_count = next(iter(lengths), 0)
    refreshed = {key: list(values) if isinstance(values, list) else values for key, values in data.items()}
    for field in ("unit", "cost_per_unit_in_currency", "cost_currency",
                  "cost_of_material_in_its_currency", "cost_of_material_in_rial"):
        refreshed[field] = [None] * row_count

    def json_number(value):
        return int(value) if value == value.to_integral_value() else float(value)

    for index in range(row_count):
        material = data["materials"][index]
        matches = prices.get(material, [])
        if len(matches) != 1:
            state = CostState.MISSING_INPUT if not matches else CostState.AMBIGUOUS_INPUT
            raise CostInputError(state, "MATERIAL_PRICE_NOT_UNIQUE",
                                 f"ردیف {index + 1}: قیمت ماده باید دقیقاً یک رکورد معتبر داشته باشد.")
        current = matches[0]
        currency = current["currency"]
        if currency == "IRR - Iranian Rial":
            fx = 1
        else:
            fx_matches = prices.get(currency, [])
            if len(fx_matches) != 1 or fx_matches[0]["currency"] != "IRR - Iranian Rial":
                raise CostInputError(CostState.AMBIGUOUS_INPUT, "AMBIGUOUS_FX_MAPPING",
                                     f"ردیف {index + 1}: نرخ ارز معتبر و یکتا نیست.")
            fx = fx_matches[0]["cost_per_unit_in_currency"]
        _, _, live = calculate_live_bom_line(
            data["usage"][index], current["cost_per_unit_in_currency"], fx,
            data["lost_percentage"][index], data["recycability_percentage"][index],
        )
        refreshed["unit"][index] = current["unit"]
        refreshed["cost_per_unit_in_currency"][index] = current["cost_per_unit_in_currency"]
        refreshed["cost_currency"][index] = fx
        refreshed["cost_of_material_in_its_currency"][index] = json_number(live / Decimal(str(fx)))
        refreshed["cost_of_material_in_rial"][index] = json_number(live)
    return {"_order": payload.get("_order", []), "data": refreshed}
