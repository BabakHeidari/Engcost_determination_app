"""Read-only presentation rows for identities added after V2 activation."""
from copy import deepcopy

from utils.product_catalog import build_product_catalog, build_product_hierarchy


def with_catalog_rows(document, identities, identity_column, value_column):
    """Keep source values/metadata, append only identities with blank cells."""
    if not isinstance(document, dict):
        raise ValueError('invalid financial document')
    result = deepcopy(document)
    data, order = result.get('data'), result.get('_order')
    if (not isinstance(data, dict) or not isinstance(order, list)
            or any(not isinstance(key, str) for key in order)
            or len(order) != len(set(order))
            or identity_column not in order or value_column not in order
            or any(not isinstance(data.get(key), list) for key in order)
            or len({len(column) for column in data.values() if isinstance(column, list)}) != 1):
        raise ValueError('invalid financial columns')
    for identity in sorted(set(identities), key=str.casefold):
        if identity not in data[identity_column]:
            for key, column in data.items():
                if isinstance(column, list):
                    column.append(identity if key == identity_column else None)
    return result


def editor_documents(factory_root, weights, predictions):
    root, key = factory_root.parent, factory_root.name
    categories = build_product_hierarchy(root, [key]).get(key, {})
    products = build_product_catalog(root, [key])
    return (
        with_catalog_rows(weights, categories, 'category', 'selling_share_of_category'),
        with_catalog_rows(predictions, [item.product for item in products], 'Product Name', 'Predicted Production'),
    )
