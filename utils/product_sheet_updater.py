"""Regenerate the legacy product catalogue from canonical product discovery."""
from __future__ import annotations

import json
from pathlib import Path

from utils.paths import parent_path, product_path
from utils.product_catalog import product_catalog_document


def regenerate_product_catalog(factory_keys=None) -> dict:
    document = product_catalog_document(Path(parent_path) / "Factories", factory_keys)
    Path(f"{product_path}.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return document


if __name__ == "__main__":
    regenerate_product_catalog()
