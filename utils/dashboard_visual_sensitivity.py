"""Bounded A/B and controlled experiments against one fresh immutable capture."""
from decimal import Decimal
from itertools import product

from utils.costing_engine import CostState, calculate_cost
from utils.dashboard_sensitivity import DashboardSensitivityService, SensitivityRequestError
from utils.dashboard_visuals import FACTORS

ZERO = Decimal(0)
DOMAIN_ERRORS = {'FINAL_VALUE_OUT_OF_DOMAIN', 'INVALID_PREDICTION_DENOMINATOR', 'INVALID_FINAL_VALUE'}


def difference(target, reference, unit, direction):
    amount = target - reference
    return {'amount': amount, 'reference': reference, 'target': target, 'unit': unit,
            'direction': direction, 'percentage_denominator': reference,
            'percentage': amount / reference * 100 if reference else None,
            'percentage_state': 'OK' if reference else 'NOT_APPLICABLE'}


def components(result):
    return {'BOM': result['bom_total'], **{r['pool_id']: r['per_unit_contribution']
                                        for r in result['breakdown']['driver_components']}}


def comparison(reference, target, direction):
    start, end = components(reference), components(target)
    delta = difference(target['unit_cost'], reference['unit_cost'], 'IRR/product', direction)
    changes = [{'id': factor, 'value': end[factor] - start[factor]} for factor in FACTORS]
    residue = delta['amount'] - sum((r['value'] for r in changes), ZERO)
    cursor = reference['unit_cost']
    for bar in [*changes, {'id': 'TECHNICAL_RECONCILIATION', 'value': residue}]:
        bar['start'], bar['end'] = cursor, cursor + bar['value']
        cursor = bar['end']
        bar['offset'], bar['size'] = min(bar['start'], bar['end']), abs(bar['value'])
        if bar['id'] == 'TECHNICAL_RECONCILIATION':
            technical = bar
    return {'unit_cost': delta,
            'projected_cost': difference(target['projected_cost'], reference['projected_cost'], 'IRR/period', direction),
            'waterfall': {'reference': reference['unit_cost'], 'target': target['unit_cost'],
                          'components': changes, 'technical_reconciliation': technical,
                          'reconciliation': residue, 'unit': 'IRR/product',
                          'direction': direction, 'meaning': 'output_component_differences_not_independent_input_effects'}}


class DashboardVisualSensitivityService(DashboardSensitivityService):
    def _experiment(self, spec, permissions):
        """Validate shape, grammar, authorization and work bounds before capture."""
        if spec is None:
            return None, []
        if not isinstance(spec, dict):
            raise SensitivityRequestError('INVALID_REQUEST', 'INVALID_EXPERIMENT_SCHEMA')
        kind = spec.get('type')
        points = []
        if kind == 'tornado' and set(spec) == {'type', 'ranges'}:
            ranges = spec['ranges']
            if not isinstance(ranges, list) or not 1 <= len(ranges) <= 10:
                raise SensitivityRequestError('INVALID_REQUEST', 'TORNADO_RANGE_LIMIT')
            for r in ranges:
                if not isinstance(r, dict) or set(r) != {'parameter_id', 'mode', 'low', 'high'}:
                    raise SensitivityRequestError('INVALID_REQUEST', 'INVALID_EXPERIMENT_SCHEMA')
                for side in ('low', 'high'):
                    points.append(([{'parameter_id': r['parameter_id'], 'mode': r['mode'], 'value': r[side]}], {'side': side}))
        elif kind in {'one_factor', 'two_factor'} and set(spec) == {'type', 'axes'}:
            axes = spec['axes']
            if not isinstance(axes, list) or len(axes) != (1 if kind == 'one_factor' else 2):
                raise SensitivityRequestError('INVALID_REQUEST', 'INVALID_EXPERIMENT_AXES')
            for axis in axes:
                if not isinstance(axis, dict) or set(axis) != {'parameter_id', 'mode', 'values'}:
                    raise SensitivityRequestError('INVALID_REQUEST', 'INVALID_EXPERIMENT_SCHEMA')
                values = axis['values']
                if not isinstance(values, list) or not 1 <= len(values) <= (41 if kind == 'one_factor' else 11):
                    raise SensitivityRequestError('INVALID_REQUEST', 'EXPERIMENT_POINT_LIMIT')
            for indices in product(*(range(len(axis['values'])) for axis in axes)):
                points.append(([{'parameter_id': axis['parameter_id'], 'mode': axis['mode'], 'value': axis['values'][i]}
                                for axis, i in zip(axes, indices)], {'indices': list(indices)}))
        else:
            raise SensitivityRequestError('INVALID_REQUEST', 'INVALID_EXPERIMENT_SCHEMA')
        parsed = [(self._parse_overrides(overrides, permissions), position) for overrides, position in points]
        if kind == 'tornado':
            for low, high in zip(parsed[::2], parsed[1::2]):
                if low[0][0][2] > high[0][0][2]:
                    raise SensitivityRequestError('INVALID_REQUEST', 'INVALID_RANGE_ORDER')
        return kind, parsed

    def visual_analysis(self, factory_id, user, *, scenarios, experiment=None, category=None,
                        subcategory=None, product=None, period_id='', start=None, end=None):
        self.factory_service.require_access(factory_id, user, 'dashboard')
        permissions = self._permissions(factory_id, user)
        if (not isinstance(scenarios, list) or len(scenarios) != 2
                or any(not isinstance(s, dict) or set(s) != {'id', 'overrides'} for s in scenarios)
                or {s['id'] for s in scenarios if isinstance(s['id'], str)} != {'A', 'B'}):
            raise SensitivityRequestError('INVALID_REQUEST', 'EXACTLY_A_B_REQUIRED')
        drafts = {s['id']: self._parse_overrides(s['overrides'], permissions) for s in scenarios}
        kind, samples = self._experiment(experiment, permissions)
        budget = 3 + len(samples)  # baseline + A + B + every sample, including invalid reservations
        if budget > 200:
            raise SensitivityRequestError('INVALID_REQUEST', 'EVALUATION_LIMIT')
        inputs, baseline, registry, unsupported, permissions = self._capture(
            factory_id, user, category, subcategory, product, period_id, start, end)
        report = self._report(inputs, baseline, registry, unsupported, permissions)
        # Server-owned source coordinates are the only alias authority.
        axes = (experiment['ranges'] if kind == 'tornado' else experiment['axes']) if kind else []
        keys = []
        for axis in axes:
            parameter = registry.get(axis['parameter_id'])
            if parameter is None:
                raise SensitivityRequestError('INVALID_REQUEST', 'UNKNOWN_OR_UNAVAILABLE_PARAMETER')
            keys.append(parameter.source_key)
        if len(keys) != len(set(keys)):
            raise SensitivityRequestError('INVALID_REQUEST', 'ALIASED_EXPERIMENT_PARAMETERS')
        evaluations = 1

        def evaluate(parsed):
            nonlocal evaluations
            normalized, effective = self._normalize(inputs, parsed, registry)
            evaluations += 1
            result = calculate_cost(inputs, normalized)
            if result.state is not CostState.OK:
                raise SensitivityRequestError('CALCULATION_ERROR' if result.state is CostState.CALCULATION_ERROR else 'INVALID_REQUEST',
                                              'EXPERIMENT_CALCULATION_FAILED' if result.state is CostState.CALCULATION_ERROR else 'SAMPLE_UNAVAILABLE',
                                              500 if result.state is CostState.CALCULATION_ERROR else 400)
            prediction = normalized.product_predictions.get(inputs.identity, inputs.product_prediction)
            return self._result(result, prediction, permissions), effective

        evaluated = {}
        for name in ('A', 'B'):
            result, effective = evaluate(drafts[name])
            evaluated[name] = {'id': name, 'result': result, 'effective_overrides': effective}
        compared = {'A_minus_baseline': comparison(report['baseline'], evaluated['A']['result'], 'A_minus_baseline'),
                    'B_minus_baseline': comparison(report['baseline'], evaluated['B']['result'], 'B_minus_baseline'),
                    'B_minus_A': comparison(evaluated['A']['result'], evaluated['B']['result'], 'B_minus_A')}
        points = []
        for parsed, position in samples:
            permitted = [{'parameter_id': p, 'mode': mode, 'value': value, 'unit': registry[p].public['unit'],
                          'final_value': self._final_value(registry[p].public['baseline_value'], mode, value)}
                         for p, mode, value in parsed]
            point = {'inputs': permitted, **position}
            try:
                result, effective = evaluate(parsed)
                point.update(state='OK', unit_cost=result['unit_cost'], projected_cost=result['projected_cost'],
                             effective_inputs=effective, issue=None,
                             unit_delta=difference(result['unit_cost'], report['baseline']['unit_cost'], 'IRR/product', 'point_minus_baseline'),
                             projected_delta=difference(result['projected_cost'], report['baseline']['projected_cost'], 'IRR/period', 'point_minus_baseline'))
            except SensitivityRequestError as exc:
                if exc.code not in DOMAIN_ERRORS | {'SAMPLE_UNAVAILABLE'}:
                    raise
                point.update(state='INVALID_INPUT', unit_cost=None, projected_cost=None,
                             effective_inputs=[], issue={'code': 'SAMPLE_OUT_OF_DOMAIN', 'message': 'این نقطه در دامنه معتبر ورودی قابل محاسبه نیست.'})
            points.append(point)
        if kind == 'one_factor':
            points.sort(key=lambda p: p['inputs'][0]['final_value'])
        output = None
        if kind:
            output = {'type': kind, 'points': points, 'valid_count': sum(p['state'] == 'OK' for p in points),
                      'invalid_count': sum(p['state'] != 'OK' for p in points), 'unit_cost_unit': 'IRR/product',
                      'projected_cost_unit': 'IRR/period', 'reference': 'captured_baseline_other_inputs_fixed'}
            if kind == 'tornado':
                ranking = []
                for low, high in zip(points[::2], points[1::2]):
                    valid = low['state'] == high['state'] == 'OK'
                    ranking.append({'parameter_id': low['inputs'][0]['parameter_id'],
                                    'impact': abs(high['unit_cost'] - low['unit_cost']) if valid else None,
                                    'state': 'OK' if valid else 'INVALID_INPUT'})
                output['ranking'] = sorted(ranking, key=lambda r: (r['impact'] is None, -(r['impact'] or ZERO), r['parameter_id']))
        # Reuse the existing whitelist context; new comparisons contain output costs only.
        report.pop('scenario'); report.pop('delta'); report.pop('effective_overrides')
        report.update(visual_version='1', scenarios=[evaluated['A'], evaluated['B']], comparisons=compared,
                      experiment=output, evaluation_budget={'reserved': budget, 'executed': evaluations, 'maximum': 200},
                      baseline_context='fresh_inputs_captured_once_for_this_request')
        return report
