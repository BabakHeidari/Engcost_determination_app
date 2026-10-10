"""Typed, read-only costing inputs and deterministic V1 calculations.

File access belongs to :class:`CostInputLoader`; ``calculate_cost`` only
operates on immutable input records.  Monetary values remain ``Decimal``
throughout the domain layer and are not rounded here.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from utils.factory_service import FactoryService
from utils.paths import parent_path
from utils.product_catalog import (
    RESERVED_FACTORY_NAMESPACES, RESERVED_FILE_NAMES, build_product_catalog,
)


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


def _source_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CostInputError(CostState.INVALID_INPUT, "INVALID_SOURCE_SCHEMA", f"{name} must be a nonempty string")
    return value


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
    """Resolve authorized inputs, with an explicit write-free analysis mode.

    The default retains the Cost Calculation migration contract. Dashboard
    callers use ``read_only=True`` and one loader per request; successful and
    failed reads, bindings, and the complete product population are snapshotted.
    """

    def __init__(self, factory_service: FactoryService, *, data_root: Path | None = None,
                 period_bindings_path: Path | None = None, read_only: bool = False):
        self.factory_service = factory_service
        self.data_root = Path(data_root or parent_path).resolve()
        self.period_bindings_path = Path(period_bindings_path or (self.data_root.parent / "instance" / "costing_period_bindings.json"))
        self.read_only = read_only
        self._documents: dict[Path, tuple[dict, SourceProvenance]] = {}
        self._read_errors: dict[Path, CostInputError] = {}
        self._source_names: dict[Path, str] = {}
        self._populations: dict[str, tuple[ProductIdentity, ...]] = {}
        self._operational_populations: dict[str, tuple[ProductIdentity, ...]] = {}
        self._factory_roots: dict[str, Path] = {}
        self._configuration_paths: dict[str, Path] = {}
        self._snapshot_paths: dict[tuple[str, ProductIdentity | None], dict[str, Path | tuple[Path, ...]]] = {}
        self._loaded_at = datetime.now(timezone.utc)

    def snapshot_population(self, factory_id: str, user: dict, *,
                            module: str = "dashboard") -> tuple[ProductIdentity, ...]:
        """Authorize, then capture a full factory population and its sources.

        Missing or malformed input documents are cached, rather than failing
        population discovery: individual ``load`` calls report their typed
        states and retain truthful configured/excluded counts.
        """
        factory = self.factory_service.require_access(factory_id, user, module)
        if module == "dashboard":
            self.read_only = True
        operational_key = self.factory_service.operational_key(factory)
        if self.read_only:
            return self._snapshot_factory(factory_id, operational_key)
        factory_root = self._inside(self.data_root / "Factories" / operational_key)
        return tuple(ProductIdentity(factory_id, item.category, item.subcategory, item.product)
                     for item in build_product_catalog(factory_root.parent, [operational_key]))

    def snapshot_lineage(self) -> tuple[SourceProvenance, ...]:
        """Return captured, logical source lineage, including the binding."""
        return tuple(source for _, source in self._documents.values())

    def _snapshot_factory(self, factory_id: str, operational_key: str) -> tuple[ProductIdentity, ...]:
        if factory_id in self._populations:
            return self._populations[factory_id]
        factory_root = self._readonly_factory_root(operational_key)
        self._factory_roots[factory_id] = factory_root
        # The catalog also reads optional product metadata. Check the trusted
        # directories and candidate files before allowing that discovery read.
        if factory_root.is_dir():
            for category in factory_root.iterdir():
                if not self._business_directory(category):
                    continue
                self._factory_source(category, factory_root)
                for subcategory in category.iterdir():
                    if not self._business_directory(subcategory):
                        continue
                    self._factory_source(subcategory, factory_root)
                    for candidate in subcategory.glob("*.json"):
                        if candidate.name not in RESERVED_FILE_NAMES and not candidate.name.startswith((".", "__")):
                            self._factory_source(candidate, factory_root)
        population = tuple(ProductIdentity(factory_id, item.category, item.subcategory, item.product)
                           for item in build_product_catalog(factory_root.parent, [operational_key]))
        self._operational_populations[operational_key] = population
        paths = self._source_paths(operational_key, None)
        for identity, bom_path in zip(population, paths["bom"]):
            self._snapshot_paths[(operational_key, identity)] = {**paths, "bom": bom_path}
        manifest_path = self._factory_source(factory_root / "configuration" / "manifest.json", factory_root)
        self._configuration_paths[factory_id] = manifest_path
        reads = [(self.period_bindings_path, "period_binding"),
                 (manifest_path, "configuration")]
        for name, path in paths.items():
            if isinstance(path, tuple):
                reads.extend((item, name) for item in path)
            else:
                reads.append((path, name))
        for path, name in reads:
            self._source_names[path] = name
            try:
                self._read(path)
            except CostInputError:
                # Error reads are also immutable within this request.
                pass
        self._populations[factory_id] = population
        return population

    def _installed_configuration(self, factory_id: str, factory_root: Path) -> None:
        manifest_path = self._configuration_paths[factory_id]
        manifest, _ = self._read(manifest_path)
        if manifest.get("schema_version") != 2:
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_FACTORY_CONFIGURATION",
                                 "installed factory configuration must use V2", "configuration")
        if manifest.get("migration_status") != "COMPLETED":
            raise CostInputError(CostState.MISSING_INPUT, "FACTORY_CONFIGURATION_INCOMPLETE",
                                 "canonical factory configuration is incomplete", "configuration")
        if manifest.get("factory_id") != factory_id or manifest.get("operational_key") != factory_root.name:
            raise CostInputError(CostState.INVALID_INPUT, "FACTORY_CONFIGURATION_MISMATCH",
                                 "canonical configuration does not match the authorized factory", "configuration")

    def resolve_period(self, factory_id: str, period_id: str = "", *,
                       start: str | date | None = None, end: str | date | None = None) -> PlanningPeriod:
        """Resolve an existing active binding and require an exact date match."""
        if not isinstance(period_id, str):
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_PERIOD", "period identifier must be a string")
        if (start is None) != (end is None):
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_PERIOD_RANGE", "both period dates are required")
        requested = None
        if start is not None:
            try:
                parsed_start = start if type(start) is date else date.fromisoformat(start)
                parsed_end = end if type(end) is date else date.fromisoformat(end)
            except (TypeError, ValueError):
                raise CostInputError(CostState.INVALID_INPUT, "INVALID_PERIOD_RANGE", "period dates must use ISO dates") from None
            if parsed_start > parsed_end:
                raise CostInputError(CostState.INVALID_INPUT, "INVALID_PERIOD_RANGE", "period start must not follow end")
            requested = (parsed_start, parsed_end)
        period, _ = self._period_binding(factory_id, period_id)
        if requested is not None and requested != (period.start, period.end):
            raise CostInputError(CostState.INVALID_INPUT, "PERIOD_MISMATCH", "requested dates do not match the existing period binding")
        return period

    def load(self, factory_id: str, user: dict, identity: ProductIdentity, period_id: str,
             *, module: str = "cost_calculation") -> CostInputs:
        factory = self.factory_service.require_access(factory_id, user, module)
        if module == "dashboard":
            self.read_only = True
        operational_key = self.factory_service.operational_key(factory)
        if identity.factory_id != factory_id:
            raise CostInputError(CostState.INVALID_INPUT, "FACTORY_ID_MISMATCH", "identity factory does not match authorized factory")
        if self.read_only:
            population = self._snapshot_factory(factory_id, operational_key)
            factory_root = self._factory_roots[factory_id]
            self._installed_configuration(factory_id, factory_root)
            if identity not in population:
                raise CostInputError(CostState.INVALID_INPUT, "PRODUCT_NOT_IN_POPULATION",
                                     "requested configuration is outside the factory product population")
        else:
            factory_root = self._inside(self.data_root / "Factories" / operational_key)
            from utils.factory_configuration import ensure_factory_configuration_v2
            ensure_factory_configuration_v2(factory_id, operational_key, data_root=self.data_root, persist=True)
        period, approved_sources = self._period_binding(factory_id, period_id)
        paths = self._source_paths(operational_key, identity)
        missing_binding = sorted(set(paths) - approved_sources)
        if missing_binding:
            raise CostInputError(CostState.MISSING_INPUT, "UNBOUND_LEGACY_SOURCE",
                                 f"period binding does not approve sources: {', '.join(missing_binding)}")

        diagnostic = self._diagnostic(period, approved_sources, paths) if not self.read_only else None
        missing = diagnostic["missing_sources"] if diagnostic is not None else []
        if missing:
            from utils.legacy_costing_migration import ensure_canonical_costing_sources

            migration = ensure_canonical_costing_sources(
                self.factory_service, factory_id, self.data_root, identity, persist=True,
            )
            diagnostic = self._diagnostic(period, approved_sources, paths)
            diagnostic["legacy_migration"] = migration
            if migration["conflicts"]:
                conflict_name = migration["conflicts"][0]
                conflict = next(item for item in migration["actions"]
                                if item["source_name"] == conflict_name and item["status"] == "CONFLICT")
                raise CostInputError(
                    CostState.AMBIGUOUS_INPUT, "LEGACY_SOURCE_CONFLICT",
                    "canonical and legacy costing sources conflict",
                    self._display_path(Path(conflict["canonical_path"])), diagnostic,
                )
            missing = diagnostic["missing_sources"]
            if missing:
                first = missing[0]
                raise CostInputError(
                    CostState.MISSING_INPUT, "SOURCE_UNAVAILABLE", first["reason"],
                    first["expected_location"], diagnostic,
                )

        incomplete = [item for item in (diagnostic["source_resolutions"] if diagnostic is not None else [])
                      if item.get("migration_status") in {"NEEDS_INPUT", "INVALID_LEGACY_SOURCE"}]
        if incomplete:
            first = incomplete[0]
            invalid = first.get("migration_status") == "INVALID_LEGACY_SOURCE"
            raise CostInputError(
                CostState.INVALID_INPUT if invalid else CostState.MISSING_INPUT,
                "INVALID_LEGACY_SOURCE" if invalid else "LEGACY_SOURCE_NEEDS_INPUT",
                "legacy source is invalid" if invalid else "generated canonical source requires business input",
                first["expected_location"], diagnostic,
            )

        documents, provenance, provenance_by_name = {}, [], {}
        for name, path in paths.items():
            documents[name], source = self._read(path)
            if self.read_only:
                # Several logical inputs may intentionally resolve to the
                # same same-factory file. Preserve each role in lineage while
                # sharing the immutable document/fingerprint snapshot.
                source = replace(source, source=name)
                status = documents[name].get("status")
                migration = documents[name].get("_migration")
                migration_status = migration.get("status") if isinstance(migration, dict) else None
                statuses = {str(status), str(migration_status)}
                if "INVALID_LEGACY_SOURCE" in statuses:
                    raise CostInputError(CostState.INVALID_INPUT, "INVALID_LEGACY_SOURCE",
                                         "installed source is invalid", name)
                if "NEEDS_INPUT" in statuses:
                    raise CostInputError(CostState.MISSING_INPUT, "LEGACY_SOURCE_NEEDS_INPUT",
                                         "installed source requires business input", name)
            provenance.append(source)
            provenance_by_name[name] = source
        materials = self._rows(documents["materials"], "materials", ("material", "unit", "currency", "cost_per_unit_in_currency"))
        by_material: dict[str, list[dict]] = {}
        for row in materials:
            material = row["material"]
            if self.read_only:
                material = _source_text(material, "material identity")
                _source_text(row["unit"], "material unit")
                _source_text(row["currency"], "material currency")
            by_material.setdefault(material, []).append(row)

        bom_rows = self._rows(documents["bom"], "bom", ("materials", "usage", "lost_percentage", "recycability_percentage"))
        lines = []
        for index, row in enumerate(bom_rows):
            material = (_source_text(row["materials"], "BOM material identity")
                        if self.read_only else row["materials"])
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
        if self.read_only:
            for row in weights:
                _source_text(row["category"], "category identity")
        matching_weights = [row for row in weights if row["category"] == identity.category]
        if len(matching_weights) != 1:
            raise CostInputError(CostState.AMBIGUOUS_INPUT, "CATEGORY_SHARE_NOT_UNIQUE", "category share must resolve exactly once")
        share = _decimal(matching_weights[0]["selling_share_of_category"], "category share")

        prediction_rows = self._rows(documents["predictions"], "predictions", ("Product Name", "Predicted Production"))
        if self.read_only:
            for row in prediction_rows:
                _source_text(row["Product Name"], "prediction product identity")
        category_products = (tuple(item for item in self._populations[factory_id] if item.category == identity.category)
                             if self.read_only else self._category_products(factory_root / identity.category, factory_id, identity.category))
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
                          tuple(provenance), self._loaded_at if self.read_only else datetime.now(timezone.utc))

    def diagnose_sources(self, factory_id: str, period_id: str = "",
                         identity: ProductIdentity | None = None) -> dict[str, Any]:
        """Compare active-period metadata with the exact paths the loader resolves."""
        factory = self.factory_service.get_factory(factory_id)
        if factory is None:
            raise CostInputError(CostState.MISSING_INPUT, "FACTORY_NOT_FOUND",
                                 "factory is absent from the canonical registry")
        operational_key = self.factory_service.operational_key(factory)
        if self.read_only:
            self._snapshot_factory(factory_id, operational_key)
        else:
            from utils.factory_configuration import ensure_factory_configuration_v2
            ensure_factory_configuration_v2(factory_id, operational_key, data_root=self.data_root, persist=True)
        period, approved_sources = self._period_binding(factory_id, period_id)
        paths = self._source_paths(operational_key, identity)
        if self.read_only:
            resolutions = []
            for name, path in paths.items():
                candidates = path if isinstance(path, tuple) else (path,)
                available = bool(candidates) and all(item in self._documents for item in candidates)
                resolutions.append({"source_name": name,
                                    "resolution_status": "AVAILABLE" if available else "MISSING"})
            return {"active_period": {"period_id": period.period_id, "start": period.start.isoformat(),
                                      "end": period.end.isoformat()},
                    "required_sources": sorted(approved_sources), "loader_sources": sorted(paths),
                    "source_resolutions": resolutions,
                    "resolved_sources": [item for item in resolutions if item["resolution_status"] == "AVAILABLE"],
                    "missing_sources": [item for item in resolutions if item["resolution_status"] == "MISSING"]}
        return self._diagnostic(period, approved_sources, paths)

    def _source_paths(self, operational_key: str,
                      identity: ProductIdentity | None) -> dict[str, Path | tuple[Path, ...]]:
        cache_key = (operational_key, identity)
        if self.read_only and cache_key in self._snapshot_paths:
            return self._snapshot_paths[cache_key]
        factory_root = (self._readonly_factory_root(operational_key) if self.read_only
                        else self._inside(self.data_root / "Factories" / operational_key))
        source_path = (lambda path: self._factory_source(path, factory_root)) if self.read_only else self._inside
        if identity is None:
            if self.read_only and operational_key in self._operational_populations:
                bom_path: Path | tuple[Path, ...] = tuple(
                    source_path(factory_root / item.category / item.subcategory / f"{item.product}.json")
                    for item in self._operational_populations[operational_key]
                )
            else:
                bom_path = tuple(sorted(source_path(item.bom_path)
                                        for item in build_product_catalog(factory_root.parent, [operational_key])))
        else:
            bom_path = source_path(
                factory_root / identity.category / identity.subcategory / f"{identity.product}.json"
            )
        material_path = self._inside(self.data_root / "Overall" / "material_costs.json")
        if self.read_only:
            overall = self.data_root / "Overall"
            if overall.resolve() != overall or overall not in material_path.parents:
                raise CostInputError(CostState.INVALID_INPUT, "UNSAFE_SOURCE_PATH", "shared source leaves its authorized namespace", "materials")
        paths: dict[str, Path | tuple[Path, ...]] = {
            "materials": material_path,
            "bom": bom_path,
            "weights": source_path(factory_root / "configuration" / "category_weights.json"),
            "predictions": source_path(factory_root / "configuration" / "production_prediction.json"),
        }
        for pool_id in FACTORY_POOL_IDS:
            paths[f"pool:{pool_id}"] = source_path(factory_root / "configuration" / "cost_pools" / f"{pool_id}.json")
        if self.read_only:
            self._snapshot_paths[cache_key] = paths
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
            resolution = {
                "source_name": source_name,
                "expected_location": expected_location,
                "resolution_status": "AVAILABLE" if found else "MISSING",
                "actual_file_found": found[0] if len(found) == 1 else found or None,
                "reason": reason,
            }
            if len(found) == 1 and expected is not None and not isinstance(expected, tuple):
                migration = self._migration_metadata(expected)
                if migration:
                    resolution["migration_status"] = migration.get("status")
                    resolution["canonicalization_status"] = "AUTO_MIGRATED"
                    resolution["legacy_source"] = migration.get("source")
                    resolution["calculation_ready"] = migration.get("status") == "READY"
                manifest_path = expected.parents[1] / "manifest.json" if expected.parent.name == "cost_pools" else expected.parent / "manifest.json"
                if manifest_path.is_file():
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        resolution["configuration_schema_version"] = manifest.get("schema_version")
                        resolution["configuration_migration_status"] = manifest.get("migration_status")
                    except (OSError, json.JSONDecodeError):
                        pass
            resolutions.append(resolution)
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

    @staticmethod
    def _migration_metadata(path: Path) -> dict | None:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        migration = document.get("_migration") if isinstance(document, dict) else None
        return migration if isinstance(migration, dict) else None

    def _period_binding(self, factory_id: str, period_id: str) -> tuple[PlanningPeriod, set[str]]:
        if not self.read_only and not self.period_bindings_path.is_file():
            raise CostInputError(
                CostState.MISSING_INPUT, "PERIOD_NOT_BOUND",
                "owner-approved costing period configuration is not installed",
            )
        if self.read_only:
            self._source_names[self.period_bindings_path] = "period_binding"
        try:
            document, _ = self._read(self.period_bindings_path)
        except CostInputError as exc:
            if exc.state is CostState.MISSING_INPUT:
                raise CostInputError(CostState.MISSING_INPUT, "PERIOD_NOT_BOUND",
                                     "costing period configuration is not installed", "period_binding") from None
            raise
        bindings = document.get("bindings")
        if not isinstance(bindings, list) or any(not isinstance(item, dict) for item in bindings):
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_PERIOD_BINDING",
                                 "period bindings must be an array of records", "period_binding")
        matches = [
            item for item in bindings
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
        identifier, sources = item.get("period_id"), item.get("sources", [])
        if (not isinstance(identifier, str) or not identifier
                or not isinstance(sources, list) or any(not isinstance(source, str) for source in sources)):
            raise CostInputError(CostState.INVALID_INPUT, "INVALID_PERIOD_BINDING",
                                 "period identity and source bindings are malformed", "period_binding")
        return PlanningPeriod(identifier, start, end), set(sources)

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved != self.data_root and self.data_root not in resolved.parents:
            raise CostInputError(CostState.INVALID_INPUT, "UNSAFE_SOURCE_PATH", "source path leaves the operational data root")
        return resolved

    @staticmethod
    def _business_directory(path: Path) -> bool:
        return path.is_dir() and not path.name.startswith((".", "__")) and path.name not in RESERVED_FACTORY_NAMESPACES

    def _readonly_factory_root(self, operational_key: str) -> Path:
        if not isinstance(operational_key, str) or Path(operational_key).name != operational_key or operational_key in {".", ".."}:
            raise CostInputError(CostState.INVALID_INPUT, "UNSAFE_SOURCE_PATH", "factory operational key is invalid")
        expected = self.data_root / "Factories" / operational_key
        resolved = self._inside(expected)
        if resolved != expected:
            raise CostInputError(CostState.INVALID_INPUT, "UNSAFE_SOURCE_PATH", "factory operational root is aliased")
        return resolved

    def _factory_source(self, path: Path, factory_root: Path) -> Path:
        resolved = self._inside(path)
        if resolved != factory_root and factory_root not in resolved.parents:
            raise CostInputError(CostState.INVALID_INPUT, "UNSAFE_SOURCE_PATH", "source leaves the authorized factory namespace")
        return resolved

    def _read(self, path: Path) -> tuple[dict, SourceProvenance]:
        if path in self._documents:
            return self._documents[path]
        if self.read_only and path in self._read_errors:
            raise self._read_errors[path]
        source_name = self._source_names.get(path, "source") if self.read_only else str(path)

        def fail(state: CostState, code: str, safe_message: str, exception: Exception | None = None):
            error = CostInputError(state, code,
                                   safe_message if self.read_only or exception is None else str(exception), source_name)
            if self.read_only:
                self._read_errors[path] = error
            raise error from None

        try:
            raw = path.read_bytes()
        except OSError as exc:
            fail(CostState.MISSING_INPUT, "SOURCE_UNAVAILABLE", "required source is unavailable", exc)
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail(CostState.INVALID_INPUT, "SOURCE_PARSE_ERROR", "required source is not valid JSON", exc)
        if not isinstance(document, dict):
            fail(CostState.INVALID_INPUT, "INVALID_SOURCE_SCHEMA", "JSON root must be an object")
        actual = None
        raw_date = document.get("last_modification_date")
        if raw_date:
            try:
                actual = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
            except ValueError:
                fail(CostState.INVALID_INPUT, "INVALID_SOURCE_DATE", "source date is malformed")
        metadata = self.read_only and source_name in {"period_binding", "configuration"}
        result = (document, SourceProvenance(source_name, hashlib.sha256(raw).hexdigest(), actual,
                                             None if actual or metadata else OWNER_LEGACY_BASELINE_DATE))
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
        factory_root = category_root.parent
        return tuple(
            ProductIdentity(factory_id, item.category, item.subcategory, item.product)
            for item in build_product_catalog(factory_root.parent, [factory_root.name])
            if item.category == category
        )


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
