# PR-10 shipped-client boundary audit

The shipped PR-09A adapters accepted several malformed response extensions even
though the canonical API contracts already specify their identities, populations,
units and bounded work. The PR-10 changes reject those envelopes before mounting
charts or enabling CSV. No monetary formula, sum, allocation, percentage, impact
ranking or technical reconciliation is calculated in JavaScript.

## Verified fixes

- Canonical detail rows now validate independent BOM row IDs and Decimal fields,
  six known unique pool components, unavailable/null rows, row-specific issues,
  and mirrored calculated rows. Nested lineage/issues stay within the selected
  identities; coverage metadata agrees across the report. An exact product
  response must match the full category/subcategory/product path of the
  authorized selected option, including when both parent filters are ALL.
- Cost visual extensions validate the unique BOM/six-pool factor set, exact
  product/component references, excluded rows, hierarchy category/subcategory
  paths and complete unique leaves, and material references to every original
  independent BOM row. Units, populations, period, coverage, composition members
  and supported chart modes are checked. Unknown protected extension fields are
  rejected. Positive/zero/signed coordinate eligibility uses exact comparisons;
  authoritative aggregate amounts and reconciliation remain backend strings.
- Lab extensions preserve the existing PR-08 registry and grant redaction for
  both A/B results and reject unknown extension fields. Comparisons bind exact
  reference/target strings, direction, units and percentage denominators to their
  actual sides; a zero reference requires a null percentage. Waterfalls use the
  seven known unique factors, the technical component, declared meaning and
  backend positions. The client checks the position chain without calculating
  component changes or reconstructing amounts.
- Experiment points bind input/effective records to the authorized registry and
  supplied inputs, validate typed invalid/null points, source units, dense unique
  indices and Cartesian cell coverage, Tornado low/high pairs, ranking states,
  counts, and evaluation-budget reservations/execution limits. Repeated supplied
  values at distinct indices remain valid. Invalid reservations may consume an
  actual engine call; execution validation allows the contract's range rather
  than equating invalid state with an unexecuted call.
- Adapter failures are reported as invalid schema in Persian and clear accepted
  data/export. Chart shells start inactive when a late response arrives in a
  hidden tab. The Cost Analysis pagehide path aborts pending work and disposes
  report charts and shared exact-value listeners.

## Evidence

`tests/test_dashboard_release_model.py` uses real isolated Flask envelopes and
Node to exercise the shipped assets. Seven tests pass, including full/PARTIAL/
unavailable Cost envelopes; all experiment shapes and grants; two-factor maximum
124 reserved/executed evaluations; repeated points; actual zero unit/projected
amounts and null percentages; backend-generated finite Decimal residue; immutable
snapshots; and malformed nested identities, factors, positions, units, counts,
comparisons and redaction fields. Existing visual-model, sensitivity-model and
number checks also pass (15 tests). Dashboard JavaScript syntax and whitespace
checks pass.

The release browser suite owns live malformed-response behavior, chart/listener
churn, accessibility, screenshots and mobile verification. Those results are
reported separately; Node tests do not substitute for actual Chromium evidence.

The older browser fixtures construct synthetic canonical reports by editing
amounts and identities independently. Some retain original lineage/pool category
identities or calculated components on an excluded row. These are intentionally
not accepted as new shipped API envelopes; any compatibility fixture update must
preserve its existing assertions and produce the declared contract.
