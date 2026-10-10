"""Exact string presentation is independent of chart coordinates and exports."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def formatted():
    node = shutil.which("node")
    if not node:
        pytest.skip("Formatter checks require Node")
    script = r"""
const fs = require('fs');
const vm = require('vm');
const context = {window: {}};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const n = context.window.DashboardNumbers;
const monetary = raw => n.format(raw, {unit:'IRR'});
const result = {
  required: monetary('156039333333'),
  large: monetary('9007199254740993.12345678901234567890'),
  largeExact: n.exact('9007199254740993.12345678901234567890', 'IRR'),
  negative: monetary('-156039333333'),
  quantity: n.format('12345.678901', {unit:'product/period'}),
  halfUp: n.format('1.005'),
  negativeHalfUp: n.format('-1.005'),
  halfDown: n.format('1.004999999999999999999'),
  zero: monetary('0.0000'),
  signedZero: monetary('-0.0000'),
  null: monetary(null),
  notApplicable: n.format(null, {state:'NOT_APPLICABLE'}),
  positiveTiny: monetary('0.000000000000000000001'),
  negativeTiny: monetary('-0.000000000000000000001'),
  nearHundredth: n.format('0.0099999999999999'),
  millionBoundary: monetary('999999.995'),
  billionBoundary: monetary('999999995'),
  trillionBoundary: monetary('999999999995'),
  belowBoundary: monetary('999999.994999999999999'),
  noCompact: n.format('156039333333', {unit:'IRR',compact:false}),
  noUnit: n.format('156039333333', {unit:'IRR',showUnit:false}),
  coverage: n.format('99.999999999999999999999', {unit:'percentage',coverage:true}),
  completeCoverage: n.format('100.0000', {unit:'percentage',coverage:true}),
  shareOverHundred: n.format('156.99999', {unit:'percentage'}),
  negativeShare: n.format('-200.001', {unit:'percentage'}),
  exactSignAndZeros: n.exact('+0001234.50000', 'IRR/product'),
  unknownUnit: n.format('50', {unit:'<script>alert(1)</script>'}),
  compare: [
    n.compare('9007199254740993.12345678901234567890','9007199254740993.12345678901234567889'),
    n.compare('-9007199254740993.12345678901234567890','-9007199254740993.12345678901234567889'),
    n.compare('0001.00000','+1'),
    n.compare('-0.0000','+0'),
    n.compare('-0.000000000001','0'),
    n.compare('9.9999999999999999999','10'),
    n.compare('0.10','0.1000000000000000000001')
  ]
};
try { n.compare(null, '0'); result.rejectsInvalid = false; }
catch (error) { result.rejectsInvalid = error.name === 'TypeError'; }
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run([node, "-e", script, str(ROOT / "static/js/dashboard-numbers.js")],
                            check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def test_readable_monetary_and_quantity_formats(formatted):
    assert formatted["required"] == "۱۵۶٫۰۴ میلیارد ریال"
    assert formatted["large"] == "۹٬۰۰۷٫۲ تریلیون ریال"
    assert formatted["negative"] == "−۱۵۶٫۰۴ میلیارد ریال"
    assert formatted["quantity"] == "۱۲٬۳۴۵٫۶۸ محصول / دوره"
    assert formatted["noCompact"] == "۱۵۶٬۰۳۹٬۳۳۳٬۳۳۳ ریال"
    assert formatted["noUnit"] == "۱۵۶٫۰۴ میلیارد"


def test_string_rounding_and_scale_boundary_promotion(formatted):
    assert formatted["halfUp"] == "۱٫۰۱"
    assert formatted["negativeHalfUp"] == "−۱٫۰۱"
    assert formatted["halfDown"] == "۱"
    assert formatted["millionBoundary"] == "۱ میلیون ریال"
    assert formatted["billionBoundary"] == "۱ میلیارد ریال"
    assert formatted["trillionBoundary"] == "۱ تریلیون ریال"
    assert formatted["belowBoundary"] == "۹۹۹٬۹۹۹٫۹۹ ریال"


def test_zero_missing_and_signed_tiny_values_remain_distinct(formatted):
    assert formatted["zero"] == "۰ ریال"
    assert formatted["signedZero"] == "−۰ ریال"
    assert formatted["null"] == "در دسترس نیست"
    assert formatted["notApplicable"] == "قابل اعمال نیست"
    assert formatted["positiveTiny"] == "کمتر از ۰٫۰۱ ریال"
    assert formatted["negativeTiny"] == "بیشتر از −۰٫۰۱ ریال"
    assert formatted["nearHundredth"] == "کمتر از ۰٫۰۱"


def test_incomplete_coverage_and_valid_signed_shares(formatted):
    assert formatted["coverage"] == "بیش از ۹۹٫۹۹٪"
    assert formatted["completeCoverage"] == "۱۰۰٪"
    assert formatted["shareOverHundred"] == "۱۵۷٪"
    assert formatted["negativeShare"] == "−۲۰۰٪"


def test_exact_display_retains_all_digits_sign_and_trailing_zeros(formatted):
    assert formatted["largeExact"] == "۹٬۰۰۷٬۱۹۹٬۲۵۴٬۷۴۰٬۹۹۳٫۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵۶۷۸۹۰ ریال"
    assert formatted["exactSignAndZeros"] == "+۰٬۰۰۱٬۲۳۴٫۵۰۰۰۰ ریال / محصول"
    assert formatted["unknownUnit"] == "۵۰"


def test_decimal_sorting_retains_precision_and_signed_order(formatted):
    assert formatted["compare"] == [1, -1, 0, 0, -1, -1, -1]
    assert formatted["rejectsInvalid"]
