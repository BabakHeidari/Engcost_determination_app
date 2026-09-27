"""Executable regression coverage for the Product/BOM browser calculator."""

import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "static" / "js" / "bom_costing.js"
TEMPLATE = ROOT / "templates" / "product" / "product_page.html"


def _node(expression):
    program = f"const c=require({json.dumps(str(SCRIPT))}); console.log(JSON.stringify({expression}));"
    completed = subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_browser_g1_golden_and_independent_percentage_cases():
    results = _node("["
        "c.calculateLineCost({usage:100,unitPrice:2,fxFactor:500000,lossPercentage:10,recyclabilityPercentage:20}),"
        "c.calculateLineCost({usage:100,unitPrice:1000,fxFactor:1,lossPercentage:10,recyclabilityPercentage:80}),"
        "c.calculateEfficiencyFactor(10,0),c.calculateEfficiencyFactor(0,80)"
        "]")
    assert results[0] == {"efficiencyFactor": 0.98, "grossCostInRial": 100000000, "liveCostInRial": 98000000}
    assert results[1]["efficiencyFactor"] == pytest.approx(0.92)
    assert results[1]["grossCostInRial"] == 100000
    assert results[1]["liveCostInRial"] == pytest.approx(92000)
    assert results[2:] == [1, 1]


def test_browser_accepts_boundaries_and_rejects_invalid_or_missing_values():
    assert _node("[c.calculateEfficiencyFactor(0,100),c.calculateEfficiencyFactor(100,100)]") == [1, 0]
    for expression in (
        "c.calculateEfficiencyFactor(-1,0)", "c.calculateEfficiencyFactor(0,101)",
        "c.calculateEfficiencyFactor('bad',0)",
        "c.calculateLineCost({usage:'',unitPrice:1,fxFactor:1,lossPercentage:0,recyclabilityPercentage:0})",
        "c.calculateLineCost({usage:1,unitPrice:'',fxFactor:1,lossPercentage:0,recyclabilityPercentage:0})",
        "c.calculateLineCost({usage:1,unitPrice:1,fxFactor:0,lossPercentage:0,recyclabilityPercentage:0})",
    ):
        result = _node(f"(()=>{{try{{{expression};return 'accepted'}}catch(e){{return e.name}}}})()")
        assert result in {"TypeError", "RangeError"}


def test_product_editor_uses_shared_browser_helper_without_legacy_clamp_or_cross_percentage_rule():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "js/bom_costing.js" in html
    assert "1 - (lost * rec)" not in html
    assert "Math.max(0, factor)" not in html
    assert "rec >= lost" not in html
    assert "recNum >= lost" not in html
    assert "99.999" not in html
    assert 'input.max = "100"' in html
