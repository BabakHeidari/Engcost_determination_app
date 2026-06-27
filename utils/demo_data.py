"""Development-only Persian demo-data selection helpers.

The helpers in this module only redirect reads when ENG_COST_DEMO_LOCALE=fa is set.
They never mutate canonical files under Data/Overall or Data/Factories.
"""

import os
from pathlib import Path

from utils.paths import parent_path

DEMO_LOCALE_ENV = "ENG_COST_DEMO_LOCALE"
PERSIAN_DEMO_LOCALE = "fa"

_DEMO_FILES = {
    "factories": Path(parent_path) / "Demo" / "fa" / "factories.json",
    "ProductsLater": Path(parent_path) / "Demo" / "fa" / "ProductsLater.json",
    "category_table_sample": Path(parent_path) / "Demo" / "fa" / "category_table_sample.json",
    "sample_data": Path(parent_path) / "Demo" / "fa" / "sample_data.json",
    "sample_product": Path(parent_path) / "Demo" / "fa" / "sample_product.json",
}


def persian_demo_enabled():
    """Return True only for explicit development/demo activation."""
    return os.environ.get(DEMO_LOCALE_ENV, "").strip().lower() == PERSIAN_DEMO_LOCALE


def demo_path_for(canonical_path):
    """Return a Persian demo path for known Overall fixtures, otherwise the original path."""
    path = Path(str(canonical_path))
    if not persian_demo_enabled():
        return path
    normalized_name = str(canonical_path).replace("\\", "/").rsplit("/", 1)[-1]
    stem = Path(normalized_name).stem
    demo_path = _DEMO_FILES.get(stem)
    if demo_path and demo_path.exists():
        return demo_path
    return path
