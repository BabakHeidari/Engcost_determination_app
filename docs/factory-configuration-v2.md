# Factory Configuration V2

Factory configuration is canonical under `Data/Factories/<operational_key>/configuration/`.
The directory contains `manifest.json`, `cost_structure.json`, six files under
`cost_pools/`, `category_weights.json`, and `production_prediction.json`.
The fixed root is `cost_structure`, fixed pools are depth 2, and cost items are
terminal depth 3 records with stable IDs. Pool totals and percentages are derived.

Migration first prefers a valid `Factory_Data_<Pool>.json`. If absent, one exact
`Factory_Data.json` match becomes `LegacyMigratedTotal` (including explicit zero).
If neither exists, the pool is `NEEDS_INPUT`. Detailed data wins over a conflicting
summary and records `LEGACY_SUMMARY_MISMATCH`. Legacy weights and predictions are
copied exactly when valid; otherwise known identities receive null values and
`NEEDS_INPUT`. Capacity is never used as a prediction.

Migration is locked, atomic, idempotent, and records fingerprints and results in
the manifest. Legacy files are retained as read-only migration/history artifacts;
there is no dual write after activation. Application startup migrates registered
factories automatically. Operators can preview with:

```bash
python scripts/migrate_factory_configuration_v2.py --all-factories
```

Add `--write` to mutate data manually.
