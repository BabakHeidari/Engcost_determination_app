# DASH-0.2 Costing Characterization Baselines

> **CURRENT BEHAVIOR — NOT YET BUSINESS-APPROVED**
>
> This document and the associated tests describe what the costing code does
> today. They do not prove that a formula is correct, approve an accounting
> rule, or define desired future behavior. Production formulas and production
> data are unchanged by DASH-0.2.

## Scope and method

The focused tests call the existing `utils.cost_determiners.cost_aggregator`
directly. Each test receives a fresh temporary `Data` root containing only
test-owned JSON files with the schemas the implementation currently reads.
Both module-level path references are monkeypatched because the aggregator
reads factory files itself while its imported `load_bom` helper resolves the
BOM path in `utils.load_data`.

The fixtures contain integers selected so all expected divisions are exact in
binary floating point. Assertions therefore use exact equality; no accounting
tolerance or unapproved business tolerance is introduced. A SHA-256 snapshot
of every fixture file before and after the normal calculation also verifies
that this costing invocation does not mutate its inputs.

## Fixture CB-01 — normal multi-component baseline

**Purpose.** Freeze the ordinary current aggregation path with one factory,
category, subcategory and product; two BOM materials; two factory subfields;
and two detail rows in each subfield.

**Technical inputs.** The product is `fixture-product` in
`fixture-factory/fixture-category/fixture-subcategory`. Its stored
`cost_of_material_in_rial` values are `1200` and `800`. `Labor` detail costs
are `600` and `400`; `Energy` detail costs are `150` and `50`. The category
weight is `50`, and predicted production is `10`.

**Current observed output.** The stored BOM values produce BOM details of
`1200` and `800`, and `BOM = 2000`. The current denominator calculation
produces `Labor = 200.0` and `Energy = 40.0`, yielding
`Final_Production_Cost = 2240.0`. The fixture files have identical hashes
before and after the call.

**Relevant test.**
`test_current_cost_aggregator_characterization_normal_multicomponent_baseline_and_no_writes`.

**Unresolved business assumptions.** Whether category share belongs in the
denominator, whether predicted production is the correct allocation driver,
which costs belong in each subfield, and whether/when rounding is required all
remain unapproved.

## Fixture CB-02 — stored BOM cost lineage

**Purpose.** Identify which BOM values the current aggregator actually uses.

**Technical inputs.** CB-01 also stores deliberately unrelated values of
`999999` and `888888` for `cost_per_unit_in_currency`, plus usages `77` and
`66`, while retaining Rial values `1200` and `800`.

**Current observed output.** `BOM_Details` and `BOM` use only the two stored
`cost_of_material_in_rial` values. The raw-looking price and usage columns are
not recomputed or consumed by this path.

**Relevant test.**
`test_current_cost_aggregator_characterization_uses_precomputed_bom_rial_values`.

**Unresolved business assumptions.** The correctness, freshness, provenance,
units, and recalculation policy of the materialized Rial fields remain
unapproved.

## Fixture CB-03 — category-weight effect

**Purpose.** Make the category weight materially affect output.

**Technical inputs.** CB-01's category weight is changed from `50` to `25`;
all other values remain fixed.

**Current observed output.** `Labor = 400.0`, `Energy = 80.0`, and
`Final_Production_Cost = 2480.0`. Halving the positive weight doubles each
factory contribution under the current denominator formula.

**Relevant test.**
`test_current_cost_aggregator_characterization_category_weight_effect`.

**Required qualification.** **This test captures the current implementation
and does not approve the business semantics of category-weight allocation.**

**Unresolved business assumptions.** The meaning, scale, normalization, and
allocation direction of the weight require business approval.

## Fixture CB-04 — ProductionPrediction effect

**Purpose.** Make predicted production materially affect output.

**Technical inputs.** CB-01's prediction is changed from `10` to `20`; all
other values remain fixed.

**Current observed output.** `Labor = 100.0`, `Energy = 20.0`, and
`Final_Production_Cost = 2120.0`. Doubling positive predicted production
halves each factory contribution under the current denominator formula.

**Relevant test.**
`test_current_cost_aggregator_characterization_prediction_effect`.

**Unresolved business assumptions.** Prediction period, unit, product identity,
and its suitability as this allocation denominator remain unapproved.

## Fixture CB-05 — swallowed subfield failures

**Purpose.** Freeze the broad subfield fallback without endorsing it.

**Technical inputs.** In separate cases, the Energy file is absent, contains
invalid JSON, or has `data` but no `cost` field. Labor remains valid.

**Current observed output.** Every case silently produces `Energy = 0.0` and
`Final_Production_Cost = 2200.0`. The output does not distinguish these input
failures from a genuine zero subfield.

**Relevant test.**
`test_current_cost_aggregator_characterization_subfield_failures_become_zero`.

**Unresolved business assumptions.** Whether calculation should fail, warn,
return an unavailable state, or substitute zero is not decided. This fallback
is technically risky because it can understate a cost without signaling why.

## Fixture CB-06 — zero-valued baseline

**Purpose.** Record behavior for a zero BOM and empty subfield cost arrays.

**Technical inputs.** One material has stored Rial cost `0`; both subfields
have empty `cost` lists. Category weight and prediction stay nonzero.

**Current observed output.** BOM, both factory contributions, and
`Final_Production_Cost` are numeric zero (`0`/`0.0`) without an exception.

**Relevant test.**
`test_current_cost_aggregator_characterization_zero_bom_and_empty_subfield_costs`.

**Unresolved business assumptions.** The UI/reporting distinction between a
real zero, missing data, and not-yet-calculated data remains undefined.

## Required edge-case inventory

All entries below remain descriptions of the current implementation, not
desired behavior.

| Case | Current observed/expected-to-observe behavior | Automated coverage |
|---|---|---|
| Category weight zero | The first subfield division by `weight / 100` raises `ZeroDivisionError`. | `test_current_cost_aggregator_characterization_category_failures` |
| Missing category | Exact list lookup raises `ValueError`. | same test |
| ProductionPrediction zero | The first allocated subfield raises `ZeroDivisionError`. | `test_current_cost_aggregator_characterization_prediction_failures` |
| Missing predicted product | Exact product-list lookup raises `ValueError`. | same test |
| Non-numeric prediction | Division raises `TypeError`. | same test |
| Missing prediction file | Loading raises `FileNotFoundError`. | `test_current_cost_aggregator_characterization_missing_prediction_file` |
| Missing BOM | BOM loading happens first and raises `FileNotFoundError`. | `test_current_cost_aggregator_characterization_bom_file_failures` |
| Malformed BOM JSON | BOM loading raises `json.JSONDecodeError`. | same test |
| Missing subfield file | Broad subfield exception handling substitutes zero. | `test_current_cost_aggregator_characterization_subfield_failures_become_zero` |
| Malformed subfield JSON | Broad subfield exception handling substitutes zero. | same test |
| Missing subfield `cost` field | Broad subfield exception handling substitutes zero. | same test |
| Zero BOM | Stored zero is summed and returned as zero. | `test_current_cost_aggregator_characterization_zero_bom_and_empty_subfield_costs` |
| Empty subfield costs | `sum([])` becomes zero and allocation remains zero. | same test |

Additional unapproved current behavior recorded by the earlier DASH-0.1 audit
includes duplicate BOM material collapse through dictionary keys/first-index
lookup and duplicate subfield collapse through output keys. Those cases are
not expanded here because the requested focused baselines cover the primary
calculation and failure boundaries without redefining those semantics.

## Risk and interpretation

The most surprising characterized behaviors are the inverse category-weight
effect, silent conversion of any subfield read/parse/schema/sum failure to
zero, exception propagation for analogous BOM/weight/prediction failures, and
exclusive reliance on precomputed BOM Rial values. These observations are
regression signals for future refactoring. They are explicitly **not business
approval**, and future changes should update a baseline only after the intended
business behavior has been separately decided and approved.
