"""Current-report visual datasets. Never open sources or alter canonical leaves."""
from decimal import Decimal

from utils.costing_engine import FACTORY_POOL_IDS

ZERO = Decimal(0)
FACTORS = ('BOM', *FACTORY_POOL_IDS)


def cost_visuals(report):
    rows = report['breakdowns']['products']
    drivers = report['breakdowns']['drivers']
    total = report['kpis']['partial_total'] if report['state'] == 'PARTIAL' else report['kpis']['projected_total']
    ordered = sorted(drivers, key=lambda r: (-abs(r['value']), r['id']))
    composition = [dict(r) for r in ordered[:4]]
    if len(ordered) > 4:
        rest = ordered[4:]
        composition.append({'id': 'OTHER', 'value': sum((r['value'] for r in rest), ZERO),
                            'share': sum((r['share'] for r in rest), ZERO) if total else None,
                            'unit': 'IRR/period', 'members': [r['id'] for r in rest]})
    products, materials, categories = [], {}, {}
    for row in rows:
        identity, prediction = row['identity'], row['prediction']
        unit = {'BOM': row['bom_total'], **{d['pool_id']: d['per_unit_contribution'] for d in row['driver_components']}}
        projected = {'BOM': row['bom_total'] * prediction,
                     **{d['pool_id']: d['product_period_contribution'] for d in row['driver_components']}}
        products.append({'identity': identity, 'unit_cost': row['unit_cost'], 'prediction': prediction,
                         'projected_cost': row['projected_cost'], 'unit_components': unit,
                         'projected_components': projected,
                         'reconciliation': row['projected_cost'] - sum(projected.values(), ZERO)})
        cat = categories.setdefault(identity['category'], {})
        sub = cat.setdefault(identity['subcategory'], [])
        sub.append({'identity': identity, 'value': row['projected_cost']})
        for item in row['bom_components']:
            material = materials.setdefault(item['material'], {'material': item['material'], 'value': ZERO, 'rows': []})
            value = item['live_cost_in_rial'] * prediction
            material['value'] += value
            material['rows'].append({'identity': identity, 'row_id': item['row_id'],
                                     'unit_contribution': item['live_cost_in_rial'], 'projected_contribution': value})
    hierarchy = []
    for category, subcategories in sorted(categories.items()):
        children = [{'name': subcategory, 'value': sum((r['value'] for r in leaves), ZERO), 'children': leaves}
                    for subcategory, leaves in sorted(subcategories.items())]
        hierarchy.append({'name': category, 'value': sum((r['value'] for r in children), ZERO), 'children': children})
    bom_total = next((r['value'] for r in drivers if r['id'] == 'BOM'), None)
    pareto = sorted(materials.values(), key=lambda r: (-r['value'], r['material']))
    cumulative = ZERO
    for item in pareto:
        cumulative += item['value']
        item['share'] = item['value'] / bom_total * 100 if bom_total else None
        item['cumulative_share'] = cumulative / bom_total * 100 if bom_total else None
    return {'version': '1', 'population': 'selected_calculated_configurations', 'coverage': report['coverage'],
            'period': report['period'], 'factor_ids': list(FACTORS), 'composition': composition,
            'composition_mode': 'donut' if total and total > ZERO and all(r['value'] >= ZERO for r in drivers) else 'bar',
            'products': products, 'hierarchy': hierarchy, 'hierarchy_unit': 'IRR/period',
            'treemap_available': all(r['projected_cost'] >= ZERO for r in products) and any(r['projected_cost'] > ZERO for r in products),
            'materials': pareto, 'pareto_denominator': bom_total, 'pareto_denominator_scope': 'selected_calculated_projected_BOM_total',
            'pareto_mode': 'pareto' if bom_total and bom_total > ZERO and all(r['value'] >= ZERO for r in pareto) else 'signed_bar',
            'material_reconciliation': bom_total - cumulative if bom_total is not None else None,
            'excluded': [r for r in report['detail_rows'] if r['state'] != 'OK']}
