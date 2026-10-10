import json
from concurrent.futures import ThreadPoolExecutor

from utils.factory_configuration import POOL_IDS, derived_summary, ensure_factory_configuration_v2


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_migration_precedence_incomplete_idempotence_and_concurrency(tmp_path):
    root = tmp_path / "Data"; factory = root / "Factories" / "op"; factory.mkdir(parents=True)
    summary = {"_order": ["Subfield", "Cost", "PercentageOfAll"], "data": {
        "Subfield": list(POOL_IDS), "Cost": [10, 0, 999, 40, 0, 60], "PercentageOfAll": [0] * 6}}
    write(factory / "Factory_Data.json", summary)
    write(factory / "Factory_Data_Overhead.json", {"data": {"subject": ["Gas"], "cost": [420]}})
    legacy = (factory / "Factory_Data.json").read_bytes()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: ensure_factory_configuration_v2("factory-1", "op", data_root=root), range(4)))
    assert {r["status"] for r in results} <= {"COMPLETED", "ALREADY_V2"}
    overhead = json.loads((factory / "configuration/cost_pools/Overhead.json").read_text())
    assert overhead["data"] == {"id": ["Gas"], "subject": ["Gas"], "cost": [420]}
    assert overhead["_migration"]["warnings"] == ["LEGACY_SUMMARY_MISMATCH"]
    depreciation = json.loads((factory / "configuration/cost_pools/Depriciation.json").read_text())
    assert depreciation["data"]["cost"] == [0]
    assert depreciation["data"]["id"] == ["LegacyMigratedTotal"]
    predictions = json.loads((factory / "configuration/production_prediction.json").read_text())
    assert predictions["status"] == "NEEDS_INPUT" and 0 not in predictions["data"]["Predicted Production"]
    assert (factory / "Factory_Data.json").read_bytes() == legacy
    before = (factory / "configuration/manifest.json").stat().st_mtime_ns
    assert ensure_factory_configuration_v2("factory-1", "op", data_root=root)["status"] == "ALREADY_V2"
    assert (factory / "configuration/manifest.json").stat().st_mtime_ns == before
    totals = derived_summary(factory)
    assert totals["pool_totals"]["Overhead"] == 420
    assert totals["factory_total"] == 530


def test_missing_pool_is_needs_input_not_zero(tmp_path):
    root = tmp_path / "Data"; (root / "Factories/op").mkdir(parents=True)
    ensure_factory_configuration_v2("factory-1", "op", data_root=root)
    pool = json.loads((root / "Factories/op/configuration/cost_pools/Payroll.json").read_text())
    assert pool["status"] == "NEEDS_INPUT"
    assert pool["data"]["cost"] == []
