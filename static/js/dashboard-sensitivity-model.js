(function (window) {
    'use strict';

    // This module validates the PR-08 wire contract. Financial values remain
    // server Decimal strings; only absolute input domains are checked locally.
    const FORMULA_VERSION = 'cost-v1-owner-approved-2026-09-27';
    const DECIMAL = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;
    const MODES = ['absolute', 'percent_change'];
    const GROUPS = ['general_parameters', 'factory_parameters'];
    const RESULT_STATES = ['OK', 'MISSING_INPUT', 'INVALID_INPUT', 'AMBIGUOUS_INPUT', 'NOT_APPLICABLE', 'CALCULATION_ERROR'];
    const STATES = [...RESULT_STATES, 'NOT_SELECTED', 'INVALID_SELECTION', 'INVALID_REQUEST', 'UNKNOWN_FACTORY', 'FORBIDDEN', 'UNAVAILABLE'];
    const POOLS = ['AdministrativeandResearch', 'Payroll', 'Overhead', 'FinancialCosts', 'Depriciation', 'NonOperationalCostsandIncomes'];
    const IDENTITY_FIELDS = ['factory_id', 'category', 'subcategory', 'product'];
    const TOP_FIELDS = ['version', 'formula_version', 'state', 'identity', 'period', 'calculated_at', 'source_lineage',
        'non_persistent', 'permissions', 'parameters', 'unsupported_parameters', 'baseline', 'scenario', 'delta', 'effective_overrides', 'issues'];
    const PARAMETER_FIELDS = ['parameter_id', 'group', 'label', 'unit', 'numeric_type', 'baseline_value', 'supported_modes',
        'domain', 'constraints', 'applicable', 'editable', 'reason', 'effect_state', 'effect_context', 'scope', 'period',
        'source_reference', 'provenance', 'dependencies'];
    const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
    const text = value => typeof value === 'string';
    const nullableText = value => value === null || text(value);
    const decimal = value => text(value) && DECIMAL.test(value);
    const keys = (value, required, optional = []) => object(value) && required.every(key => Object.prototype.hasOwnProperty.call(value, key)) &&
        Object.keys(value).every(key => required.includes(key) || optional.includes(key));
    const selectionValue = value => text(value) && value.length > 0 && value.length <= 2048 && value === value.trim() &&
        value !== '__ALL__' && !/[\u0000-\u001f\u007f]/.test(value);
    const identity = value => keys(value, IDENTITY_FIELDS) && IDENTITY_FIELDS.every(key => selectionValue(value[key]));
    const sameIdentity = (a, b) => identity(a) && identity(b) && IDENTITY_FIELDS.every(key => a[key] === b[key]);
    const samePeriod = (a, b) => period(a) && period(b) && ['id', 'start', 'end'].every(key => a[key] === b[key]);
    const array = (value, check) => Array.isArray(value) && value.every(check);
    const unique = values => new Set(values).size === values.length;
    const parameterId = value => text(value) && value.length > 0 && value.length <= 256;
    const ERROR_MESSAGES = Object.freeze({
        DECIMAL_REQUIRED: 'مقدار را به صورت عدد اعشاری وارد کنید.',
        INVALID_DECIMAL: 'عدد معتبر با رقم فارسی، عربی یا لاتین وارد کنید؛ جداکننده هزارگان و توان مجاز نیست.',
        DECIMAL_TOO_LONG: 'مقدار اعشاری باید حداکثر ۱۲۸ نویسه داشته باشد.',
        UNAVAILABLE_PARAMETER: 'پارامتر یا روش تغییر برای این دامنه مجاز نیست.',
        INVALID_DOMAIN: 'حدود معتبر پارامتر در دسترس نیست؛ فهرست را تازه کنید.',
        OUT_OF_DOMAIN: 'مقدار واردشده خارج از حدود مجاز پارامتر است.',
        EXPLICIT_SELECTION_REQUIRED: 'یک کارخانه، دسته، زیردسته، محصول و دوره را صریح انتخاب کنید.',
        TOO_MANY_OVERRIDES: 'حداکثر ۶۴ پارامتر را در یک سناریو تغییر دهید.',
        INVALID_OVERRIDES: 'فهرست تغییرات معتبر نیست؛ مقدارها و شناسه‌های تکراری را بررسی کنید.',
        INCOMPLETE_PERIOD_RANGE: 'تاریخ شروع و پایان باید با هم وارد شوند.',
        INVALID_PERIOD_RANGE: 'بازه دوره معتبر نیست.',
        BODY_TOO_LARGE: 'حجم درخواست از حد مجاز ۶۴ کیلوبایت بیشتر است.'
    });
    const invalid = code => ({valid: false, code, error: ERROR_MESSAGES[code]});

    function dateOnly(value) {
        if (!text(value) || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000-')) return false;
        const parsed = new Date(value + 'T00:00:00Z');
        return !isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
    }
    function dateTime(value) {
        // Legacy actual-as-of metadata may be a naive ISO datetime; capture
        // timestamps from the API include UTC. Display conversion is separate.
        return text(value) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/.test(value) &&
            dateOnly(value.slice(0, 10)) && !isNaN(new Date(value).getTime());
    }
    function period(value) {
        return keys(value, ['id', 'start', 'end']) && selectionValue(value.id) && dateOnly(value.start) && dateOnly(value.end) && value.start <= value.end;
    }
    function sourceGroup(source) {
        if (source === 'materials') return 'general_parameters';
        if (['weights', 'predictions', 'configuration'].includes(source) || source.startsWith('pool:')) return 'factory_parameters';
        return null;
    }
    function logicalSource(value) {
        return ['bom', 'materials', 'weights', 'predictions', 'configuration', 'period_binding'].includes(value) ||
            POOLS.some(pool => value === 'pool:' + pool);
    }
    function provenance(value, permissions) {
        return keys(value, ['source', 'fingerprint', 'actual_as_of', 'owner_assigned_baseline', 'business_version']) &&
            logicalSource(value.source) && (!sourceGroup(value.source) || permissions[sourceGroup(value.source)] === true) &&
            text(value.fingerprint) && /^[a-f0-9]{64}$/i.test(value.fingerprint) &&
            (value.actual_as_of === null || dateTime(value.actual_as_of)) &&
            (value.owner_assigned_baseline === null || dateOnly(value.owner_assigned_baseline)) && nullableText(value.business_version);
    }
    function issue(value, contextIdentity) {
        return keys(value, ['state', 'code', 'message'], ['identity']) && RESULT_STATES.includes(value.state) && text(value.code) &&
            text(value.message) && (value.identity === undefined || (identity(value.identity) &&
                (contextIdentity === null || sameIdentity(value.identity, contextIdentity))));
    }
    function domain(value) {
        return keys(value, ['minimum', 'minimum_exclusive', 'maximum', 'maximum_exclusive']) && decimal(value.minimum) &&
            typeof value.minimum_exclusive === 'boolean' && (value.maximum === null || decimal(value.maximum)) &&
            typeof value.maximum_exclusive === 'boolean' && (value.maximum === null || window.DashboardNumbers.compare(value.minimum, value.maximum) <= 0);
    }
    function dependency(value, contextIdentity) {
        if (!object(value)) return false;
        switch (value.kind) {
        case 'material_unit_prices':
            return keys(value, ['kind', 'row_ids']) && array(value.row_ids, selectionValue) && unique(value.row_ids);
        case 'fx_rates':
            return keys(value, ['kind', 'currency', 'row_ids']) && selectionValue(value.currency) && array(value.row_ids, selectionValue) && unique(value.row_ids);
        case 'factory_pool_amounts':
            return keys(value, ['kind', 'pool_ids']) && array(value.pool_ids, id => POOLS.includes(id)) && unique(value.pool_ids);
        case 'category_share':
            return keys(value, ['kind', 'category']) && value.category === contextIdentity.category;
        case 'product_predictions':
            return keys(value, ['kind', 'identity', 'allocation_population']) && sameIdentity(value.identity, contextIdentity) &&
                value.allocation_population === 'full_category_predictions';
        default: return false;
        }
    }
    function parameter(value, report) {
        if (!keys(value, PARAMETER_FIELDS) || !parameterId(value.parameter_id) || !GROUPS.includes(value.group) ||
            report.permissions[value.group] !== true || !text(value.label) || !text(value.unit) || value.numeric_type !== 'decimal' ||
            !decimal(value.baseline_value) || !array(value.supported_modes, mode => MODES.includes(mode)) ||
            value.supported_modes.length !== 2 || !unique(value.supported_modes) || !domain(value.domain) ||
            !array(value.constraints, constraint => ['FINITE_DECIMAL', 'VALID_BASELINE_REQUIRED', 'POSITIVE_FULL_CATEGORY_PREDICTION_DENOMINATOR'].includes(constraint)) ||
            !value.constraints.includes('FINITE_DECIMAL') || !value.constraints.includes('VALID_BASELINE_REQUIRED') || !unique(value.constraints) ||
            value.applicable !== true || value.editable !== true || value.reason !== null || !['CONNECTED', 'MATHEMATICAL_ZERO'].includes(value.effect_state) ||
            value.effect_context !== 'baseline_inputs_other_parameters_fixed' ||
            !['selected_configuration', 'whole_factory_simulated', 'selected_category'].includes(value.scope) ||
            !samePeriod(value.period, report.period) || !keys(value.source_reference, ['source', 'record_id']) ||
            value.source_reference.record_id !== value.parameter_id || !provenance(value.provenance, report.permissions) ||
            value.source_reference.source !== value.provenance.source || sourceGroup(value.provenance.source) !== value.group ||
            !report.source_lineage.some(source => ['source', 'fingerprint', 'actual_as_of', 'owner_assigned_baseline', 'business_version']
                .every(key => source[key] === value.provenance[key])) || !array(value.dependencies, item => dependency(item, report.identity)) ||
            !value.dependencies.length) return false;
        // IDs are opaque registry identifiers. Neither source coordinates nor
        // authorization are inferred by parsing their strings.
        return true;
    }
    function unsupported(value, permissions) {
        return keys(value, ['parameter_type', 'reason', 'message'], ['group']) && text(value.parameter_type) && text(value.reason) && text(value.message) &&
            (value.group === undefined || (GROUPS.includes(value.group) && permissions[value.group] === true));
    }
    function result(value, report) {
        const financial = ['unit_cost', 'projected_cost', 'bom_total', 'driver_total'];
        const required = ['state', 'unit_cost', 'unit', 'projected_cost', 'projected_cost_unit', 'projected_cost_scope', 'projected_cost_label',
            'bom_total', 'driver_total', 'breakdown', 'issues'];
        const predictionFields = report.permissions.factory_parameters ? ['prediction', 'prediction_unit'] : [];
        if (!keys(value, [...required, ...predictionFields]) || !RESULT_STATES.includes(value.state) || value.unit !== 'IRR/product' ||
            value.projected_cost_unit !== 'IRR/period' || value.projected_cost_scope !== 'single_configuration' || !text(value.projected_cost_label) ||
            !keys(value.breakdown, ['bom_components', 'driver_components']) || !array(value.issues, item => issue(item, report.identity)) ||
            (predictionFields.length && value.prediction_unit !== 'product/period')) return false;
        if (predictionFields.length) financial.push('prediction');
        if (!financial.every(key => value.state === 'OK' ? decimal(value[key]) : value[key] === null)) return false;
        if (!array(value.breakdown.bom_components, row => keys(row, ['row_id', 'material', 'live_cost_in_rial']) &&
            selectionValue(row.row_id) && text(row.material) && decimal(row.live_cost_in_rial)) ||
            !unique(value.breakdown.bom_components.map(row => row.row_id))) return false;
        const rawFields = report.permissions.factory_parameters ? ['raw_factory_pool', 'adjusted_category_pool', 'category_prediction_total', 'modeled_minus_raw'] : [];
        if (!array(value.breakdown.driver_components, row => keys(row, ['pool_id', 'per_unit_contribution', 'product_period_contribution', ...rawFields]) &&
            POOLS.includes(row.pool_id) && ['per_unit_contribution', 'product_period_contribution', ...rawFields].every(key => decimal(row[key]))) ||
            !unique(value.breakdown.driver_components.map(row => row.pool_id))) return false;
        return value.state === 'OK' ? value.issues.length === 0 : value.issues.length > 0 &&
            value.breakdown.bom_components.length === 0 && value.breakdown.driver_components.length === 0;
    }
    function delta(value) {
        return keys(value, ['amount', 'percentage', 'percentage_state', 'unit', 'direction']) && decimal(value.amount) &&
            ['OK', 'NOT_APPLICABLE'].includes(value.percentage_state) &&
            (value.percentage_state === 'OK' ? decimal(value.percentage) : value.percentage === null) &&
            value.unit === 'IRR/product' && value.direction === 'scenario_minus_baseline';
    }
    function effective(value, report) {
        const registered = report.parameters.find(item => item.parameter_id === value?.parameter_id);
        return keys(value, ['parameter_id', 'mode', 'value', 'baseline_value', 'final_value', 'unit', 'provenance_state']) && registered !== undefined &&
            MODES.includes(value.mode) && ['value', 'baseline_value', 'final_value'].every(key => decimal(value[key])) &&
            window.DashboardNumbers.compare(value.baseline_value, registered.baseline_value) === 0 && value.unit === registered.unit &&
            value.provenance_state === 'HYPOTHETICAL_OVERRIDE';
    }
    function validate(report) {
        try {
            if (!window.DashboardNumbers || !keys(report, TOP_FIELDS) || report.version !== '1' || report.formula_version !== FORMULA_VERSION ||
                !STATES.includes(report.state) || report.non_persistent !== true || !(report.identity === null || identity(report.identity)) ||
                !(report.period === null || period(report.period)) || !(report.calculated_at === null || dateTime(report.calculated_at)) ||
                !object(report.permissions) || !array(report.issues, item => issue(item, report.identity))) return false;
            const uncaptured = Object.keys(report.permissions).length === 0;
            if (!uncaptured && (!keys(report.permissions, GROUPS) || !GROUPS.every(group => typeof report.permissions[group] === 'boolean'))) return false;
            if (!array(report.source_lineage, item => provenance(item, report.permissions)) || !unique(report.source_lineage.map(item => item.source)) ||
                !array(report.parameters, item => parameter(item, report)) || !unique(report.parameters.map(item => item.parameter_id)) ||
                !array(report.unsupported_parameters, item => unsupported(item, report.permissions)) ||
                !(report.baseline === null || result(report.baseline, report)) || !(report.scenario === null || result(report.scenario, report)) ||
                !(report.delta === null || delta(report.delta)) || !array(report.effective_overrides, item => effective(item, report)) ||
                report.effective_overrides.length > 64 || !unique(report.effective_overrides.map(item => item.parameter_id))) return false;
            if (uncaptured) return report.state !== 'OK' && report.identity === null && report.period === null && report.calculated_at === null &&
                report.source_lineage.length === 0 && report.parameters.length === 0 && report.unsupported_parameters.length === 0 &&
                report.baseline === null && report.scenario === null && report.delta === null && report.effective_overrides.length === 0 && report.issues.length > 0;
            if (report.calculated_at === null || report.baseline === null) return false;
            if (report.baseline.state !== 'OK') return report.state === report.baseline.state && report.parameters.length === 0 &&
                report.scenario === null && report.delta === null && report.effective_overrides.length === 0 && report.issues.length > 0;
            if (report.identity === null || report.period === null) return false;
            if (report.scenario === null) return report.state === 'OK' && report.delta === null && report.effective_overrides.length === 0 && report.issues.length === 0;
            if (report.scenario.state !== 'OK') return (report.state === 'INVALID_REQUEST' && report.scenario.state === 'INVALID_INPUT' ||
                report.state === 'CALCULATION_ERROR' && report.scenario.state === 'CALCULATION_ERROR') && report.delta === null &&
                report.effective_overrides.length === 0 && report.issues.length > 0;
            if (report.state !== 'OK' || report.delta === null || report.issues.length > 0) return false;
            const baselineZero = window.DashboardNumbers.compare(report.baseline.unit_cost, '0') === 0;
            return report.delta.percentage_state === (baselineZero ? 'NOT_APPLICABLE' : 'OK');
        } catch (_) { return false; }
    }
    function freeze(value) {
        if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
        return value;
    }
    function adapt(report) {
        if (!validate(report)) throw new Error('UNSUPPORTED_SENSITIVITY_SCHEMA');
        return freeze(JSON.parse(JSON.stringify(report)));
    }
    function matchesScope(report, selection) {
        if (!object(selection) || !identity(report?.identity) || !period(report.period)) return false;
        return report.identity.factory_id === selection.factory && report.identity.category === selection.category &&
            report.identity.subcategory === selection.subcategory && report.identity.product === selection.productLabel &&
            report.period.id === selection.period_id && (selection.start === undefined || report.period.start === selection.start) &&
            (selection.end === undefined || report.period.end === selection.end);
    }
    function normalizeInput(raw) {
        if (!text(raw)) return invalid('DECIMAL_REQUIRED');
        const value = raw.trim().replace(/[۰-۹]/g, digit => String.fromCharCode(digit.charCodeAt(0) - 0x06F0 + 48))
            .replace(/[٠-٩]/g, digit => String.fromCharCode(digit.charCodeAt(0) - 0x0660 + 48)).replace(/٫/g, '.')
            .replace(/^−/, '-').replace(/^\+(?=[0-9])/, '');
        if (!value || !DECIMAL.test(value)) return invalid('INVALID_DECIMAL');
        if (value.length > 128) return invalid('DECIMAL_TOO_LONG');
        return {valid: true, value};
    }
    function validateOverride(parameter, mode, raw) {
        if (!object(parameter) || parameter.applicable !== true || parameter.editable !== true || !parameterId(parameter.parameter_id) ||
            !Array.isArray(parameter.supported_modes) || !parameter.supported_modes.includes(mode) || !MODES.includes(mode))
            return invalid('UNAVAILABLE_PARAMETER');
        const normalized = normalizeInput(raw);
        if (!normalized.valid) return normalized;
        if (!domain(parameter.domain)) return invalid('INVALID_DOMAIN');
        if (mode === 'absolute') {
            const minimum = window.DashboardNumbers.compare(normalized.value, parameter.domain.minimum);
            const maximum = parameter.domain.maximum === null ? -1 : window.DashboardNumbers.compare(normalized.value, parameter.domain.maximum);
            if (minimum < 0 || (minimum === 0 && parameter.domain.minimum_exclusive) || maximum > 0 ||
                (maximum === 0 && parameter.domain.maximum_exclusive)) return invalid('OUT_OF_DOMAIN');
        }
        // Relative final values and coupled prediction denominators belong to
        // the backend. The browser never multiplies or allocates cost inputs.
        return {valid: true, override: {parameter_id: parameter.parameter_id, mode, value: normalized.value}};
    }
    function buildRequest(selection, overrides) {
        if (!object(selection) || !['factory', 'category', 'subcategory', 'product', 'period_id'].every(key => selectionValue(selection[key])))
            return invalid('EXPLICIT_SELECTION_REQUIRED');
        if (!Array.isArray(overrides) || overrides.length > 64) return invalid('TOO_MANY_OVERRIDES');
        if (!overrides.every(item => keys(item, ['parameter_id', 'mode', 'value']) && parameterId(item.parameter_id) && MODES.includes(item.mode) &&
            decimal(item.value) && item.value.length <= 128) || !unique(overrides.map(item => item.parameter_id)))
            return invalid('INVALID_OVERRIDES');
        const body = {factory: selection.factory, category: selection.category, subcategory: selection.subcategory,
            product: selection.product, period: selection.period_id, overrides: overrides.map(item => ({...item}))};
        if ((selection.start === undefined) !== (selection.end === undefined)) return invalid('INCOMPLETE_PERIOD_RANGE');
        if (selection.start !== undefined) {
            if (!dateOnly(selection.start) || !dateOnly(selection.end) || selection.start > selection.end) return invalid('INVALID_PERIOD_RANGE');
            body.start = selection.start; body.end = selection.end;
        }
        const json = JSON.stringify(body);
        const byteLength = encodeURIComponent(json).replace(/%[A-F\d]{2}/g, 'x').length;
        if (byteLength > 64 * 1024) return invalid('BODY_TOO_LARGE');
        return {valid: true, body, json};
    }
    function contextKey(report) {
        return JSON.stringify([report.identity, report.period, report.formula_version, report.permissions,
            report.source_lineage, report.parameters.map(item => [item.parameter_id, item.baseline_value, item.provenance])]);
    }
    function canExport(report) {
        return validate(report) && report.state === 'OK' && report.baseline.state === 'OK' && report.scenario?.state === 'OK' && report.delta !== null;
    }
    function csvText(value) {
        const raw = value == null ? '' : String(value);
        // Quoting CSV alone does not neutralize spreadsheet expressions.
        return /^[\s\u0000-\u001f]*[=+\-@]/.test(raw) || /^[\u0000-\u001f]/.test(raw) ? "'" + raw : raw;
    }
    function csvNumber(value) {
        if (value === null || value === undefined) return '';
        if (!decimal(value)) throw new Error('INVALID_DECIMAL');
        return value;
    }
    function csv(report) {
        if (!canExport(report)) throw new Error('NO_ACCEPTED_SCENARIO');
        const fields = ['row_type', 'scenario_label', 'non_persistent', 'formula_version', ...IDENTITY_FIELDS, 'period_id', 'period_start', 'period_end',
            'calculated_at', 'state', 'unit_cost', 'projected_cost', 'bom_total', 'bom_total_unit', 'driver_total', 'driver_total_unit', 'prediction', 'unit', 'projected_cost_unit',
            'prediction_unit', 'projected_cost_scope', 'projected_cost_label', 'delta_amount', 'delta_percentage', 'percentage_state',
            'delta_unit', 'direction', 'parameter_id', 'label', 'group', 'scope', 'mode', 'value', 'baseline_value', 'final_value',
            'provenance_state', 'effect_state', 'effect_context', 'source', 'fingerprint', 'actual_as_of', 'owner_assigned_baseline', 'business_version',
            'row_id', 'material', 'live_cost_in_rial', 'live_cost_in_rial_unit', 'pool_id', 'per_unit_contribution', 'per_unit_contribution_unit',
            'product_period_contribution', 'product_period_contribution_unit', 'raw_factory_pool', 'raw_factory_pool_unit',
            'adjusted_category_pool', 'adjusted_category_pool_unit', 'category_prediction_total', 'category_prediction_total_unit',
            'modeled_minus_raw', 'modeled_minus_raw_unit'];
        const numeric = new Set(['unit_cost', 'projected_cost', 'bom_total', 'driver_total', 'prediction', 'delta_amount', 'delta_percentage',
            'value', 'baseline_value', 'final_value', 'live_cost_in_rial', 'per_unit_contribution', 'product_period_contribution',
            'raw_factory_pool', 'adjusted_category_pool', 'category_prediction_total', 'modeled_minus_raw']);
        const quoted = value => '"' + String(value).replace(/"/g, '""') + '"';
        const metadata = {scenario_label: 'سناریوی فرضی؛ فقط شبیه‌سازی و بدون ذخیره در منابع', non_persistent: true,
            formula_version: report.formula_version, ...report.identity,
            period_id: report.period.id, period_start: report.period.start, period_end: report.period.end, calculated_at: report.calculated_at};
        const lines = [fields.map(quoted).join(',')];
        function push(row) {
            const values = {...metadata, ...row};
            lines.push(fields.map(key => quoted(numeric.has(key) ? csvNumber(values[key]) : csvText(values[key]))).join(','));
        }
        ['baseline', 'scenario'].forEach(kind => {
            const value = report[kind];
            push({row_type: kind, state: value.state, unit_cost: value.unit_cost, projected_cost: value.projected_cost, bom_total: value.bom_total,
                bom_total_unit: 'IRR/product', driver_total: value.driver_total, driver_total_unit: 'IRR/product', prediction: value.prediction,
                unit: value.unit, projected_cost_unit: value.projected_cost_unit,
                prediction_unit: value.prediction_unit, projected_cost_scope: value.projected_cost_scope, projected_cost_label: value.projected_cost_label});
            value.breakdown.bom_components.forEach(row => push({row_type: kind + '_bom', ...row, live_cost_in_rial_unit: 'IRR/product'}));
            value.breakdown.driver_components.forEach(row => {
                const units = {per_unit_contribution_unit: 'IRR/product', product_period_contribution_unit: 'IRR/period'};
                // Protected pool details and their units exist only when the
                // accepted server result actually returned those fields.
                ['raw_factory_pool', 'adjusted_category_pool', 'modeled_minus_raw'].forEach(key => {
                    if (row[key] !== undefined) units[key + '_unit'] = 'IRR/period';
                });
                if (row.category_prediction_total !== undefined) units.category_prediction_total_unit = 'product/period';
                push({row_type: kind + '_driver', ...row, ...units});
            });
        });
        push({row_type: 'delta', delta_amount: report.delta.amount, delta_percentage: report.delta.percentage,
            percentage_state: report.delta.percentage_state, delta_unit: report.delta.unit, direction: report.delta.direction});
        report.effective_overrides.forEach(item => {
            const parameter = report.parameters.find(entry => entry.parameter_id === item.parameter_id);
            push({row_type: 'override', ...item, label: parameter.label, group: parameter.group, scope: parameter.scope,
                effect_state: parameter.effect_state, effect_context: parameter.effect_context, ...parameter.provenance});
        });
        report.source_lineage.forEach(item => push({row_type: 'source_lineage', ...item}));
        return '\uFEFF' + lines.join('\r\n') + '\r\n';
    }

    window.DashboardSensitivityModel = Object.freeze({validate, adapt, matchesScope, normalizeInput, validateOverride, buildRequest, contextKey, canExport, csv});
})(window);
