(function (window) {
    'use strict';

    // Decimal strings are the report authority. Number conversion is confined
    // to chart coordinates; displayed values and exports always use the string.
    const DECIMAL = /^[+-]?\d+(?:\.\d+)?$/;
    const DRIVER_LABELS = Object.freeze({
        BOM: 'مواد و اقلام BOM',
        AdministrativeandResearch: 'اداری و پژوهش',
        Payroll: 'حقوق و دستمزد',
        Overhead: 'سربار',
        FinancialCosts: 'هزینه‌های مالی',
        Depriciation: 'استهلاک',
        NonOperationalCostsandIncomes: 'هزینه‌ها و درآمدهای غیرعملیاتی'
    });
    const STATE_LABELS = Object.freeze({
        OK: 'محاسبه‌شده', PARTIAL: 'مجموع جزئی', NO_MATCH: 'بدون پیکربندی منطبق',
        MISSING_INPUT: 'ورودی لازم موجود نیست', INVALID_INPUT: 'ورودی نامعتبر',
        AMBIGUOUS_INPUT: 'ورودی مبهم', NOT_APPLICABLE: 'قابل اعمال نیست',
        CALCULATION_ERROR: 'خطای محاسبه', NOT_SELECTED: 'انتخاب کامل نیست',
        INVALID_SELECTION: 'انتخاب نامعتبر', INVALID_REQUEST: 'درخواست نامعتبر',
        UNKNOWN_FACTORY: 'کارخانه پیدا نشد', FORBIDDEN: 'دسترسی مجاز نیست',
        UNAVAILABLE: 'در دسترس نیست'
    });
    const SOURCE_LABELS = Object.freeze({
        bom: 'BOM پیکربندی', materials: 'قیمت مواد', exchange_rates: 'نرخ ارز',
        predictions: 'برنامه تولید', category_predictions: 'برنامه تولید دسته',
        shares: 'سهم دسته', loss_recyclability: 'ضایعات و بازیافت',
        configuration: 'پیکربندی کارخانه', period_binding: 'اتصال دوره'
    });
    const IDENTITY_FIELDS = ['factory_id', 'category', 'subcategory', 'product'];
    const views = new Map();
    const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
    const text = value => typeof value === 'string';
    const nullableText = value => value === null || text(value);
    const decimal = value => value === null || (text(value) && DECIMAL.test(value));
    const count = value => Number.isSafeInteger(value) && value >= 0;
    const state = value => text(value) && Object.prototype.hasOwnProperty.call(STATE_LABELS, value);
    const driver = value => text(value) && Object.prototype.hasOwnProperty.call(DRIVER_LABELS, value);
    const identity = value => object(value) && IDENTITY_FIELDS.every(key => text(value[key]));
    const coverage = value => object(value) && ['configured', 'calculated', 'excluded'].every(key => count(value[key])) && decimal(value.percentage);
    const issue = value => object(value) && text(value.code) && state(value.state) && text(value.message) && (value.identity === undefined || identity(value.identity));
    const issues = value => Array.isArray(value) && value.every(issue);
    function dateOnly(value) {
        if (!text(value) || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
        const [year, month, day] = value.split('-').map(Number);
        const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
        const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        return year > 0 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1];
    }
    const detailRow = value => object(value) && identity(value.identity) &&
        ['OK', 'MISSING_INPUT', 'INVALID_INPUT', 'AMBIGUOUS_INPUT', 'NOT_APPLICABLE', 'CALCULATION_ERROR'].includes(value.state) &&
        ['unit_cost', 'prediction', 'projected_cost', 'bom_total'].every(key => decimal(value[key])) &&
        value.unit === 'IRR/product' && value.prediction_unit === 'product/period' && value.projected_cost_unit === 'IRR/period' &&
        ['unit_cost', 'prediction', 'projected_cost', 'bom_total'].every(key => value.state === 'OK' ? value[key] !== null : value[key] === null) &&
        Array.isArray(value.bom_components) && Array.isArray(value.driver_components) && issues(value.issues);
    const identityKey = value => JSON.stringify(IDENTITY_FIELDS.map(key => value[key]));

    function validate(report) {
        if (!object(report) || report.version !== '1' || !state(report.state) || !text(report.formula_version)) return false;
        if (report.scope !== null && (!object(report.scope) || !object(report.scope.factory) ||
            !text(report.scope.factory.id) || !text(report.scope.factory.name) || !text(report.scope.factory.code) ||
            !object(report.scope.selection) || !['category', 'subcategory', 'product'].every(key => nullableText(report.scope.selection[key])) ||
            report.scope.population !== 'selected_configurations' || report.scope.allocation_population !== 'full_category_predictions')) return false;
        if (report.period !== null && (!object(report.period) || !text(report.period.id) || !dateOnly(report.period.start) || !dateOnly(report.period.end) || report.period.start > report.period.end)) return false;
        if (!nullableText(report.calculated_at) || !coverage(report.coverage) || !issues(report.issues)) return false;
        const kpis = report.kpis;
        if (!object(kpis) || !count(kpis.matched_configuration_count) || !decimal(kpis.projected_total) ||
            !decimal(kpis.partial_total) || !nullableText(kpis.partial_total_label) || !object(kpis.units) ||
            kpis.units.matched_configuration_count !== 'configuration' || kpis.units.projected_total !== 'IRR/period' ||
            kpis.units.partial_total !== 'IRR/period') return false;
        const average = kpis.weighted_average;
        if (!object(average) || !state(average.state) || !['value', 'numerator', 'denominator'].every(key => decimal(average[key])) ||
            average.unit !== 'IRR/product' || average.population !== 'selected_calculated_configurations' || (average.coverage !== undefined && !coverage(average.coverage))) return false;
        const top = kpis.top_cost_driver;
        if (!object(top) || !state(top.state) || !(top.id === null || driver(top.id)) || !decimal(top.value) || !decimal(top.share) ||
            !(top.tie === null || typeof top.tie === 'boolean') || !Array.isArray(top.tied_ids) || !top.tied_ids.every(driver) ||
            (top.coverage !== undefined && !coverage(top.coverage)) || (top.unit !== undefined && top.unit !== 'IRR/period') ||
            (top.population !== undefined && top.population !== 'selected_calculated_configurations')) return false;
        const breakdowns = report.breakdowns;
        if (!object(breakdowns) || !Array.isArray(breakdowns.products) || !breakdowns.products.every(detailRow) ||
            !Array.isArray(report.detail_rows) || !report.detail_rows.every(detailRow)) return false;
        if (!Array.isArray(breakdowns.drivers) || !breakdowns.drivers.every(item => object(item) && driver(item.id) &&
            decimal(item.value) && decimal(item.share) && item.unit === 'IRR/period' && item.population === 'selected_calculated_configurations')) return false;
        if (!Array.isArray(breakdowns.factory_pools) || !breakdowns.factory_pools.every(item => object(item) && driver(item.id) && item.id !== 'BOM' &&
            ['raw_total', 'modeled_selected_total', 'selected_minus_raw', 'modeled_category_total', 'category_minus_raw'].every(key => decimal(item[key])) &&
            item.raw_scope === 'whole_factory' && item.modeled_selected_scope === 'selected_calculated_configurations' &&
            item.modeled_category_scope === 'full_prediction_population_of_reported_categories' && item.unit === 'IRR/period' && coverage(item.coverage) &&
            Array.isArray(item.categories) && item.categories.every(category => object(category) && text(category.category) &&
                decimal(category.adjusted_pool) && decimal(category.prediction_denominator)))) return false;
        if (report.arithmetic_reconciliation !== null && (!object(report.arithmetic_reconciliation) ||
            !['projected_rows_total', 'driver_components_total', 'difference'].every(key => decimal(report.arithmetic_reconciliation[key])) ||
            report.arithmetic_reconciliation.unit !== 'IRR/period')) return false;
        if (!Array.isArray(report.source_lineage) || !report.source_lineage.every(item => object(item) && text(item.source) &&
            text(item.fingerprint) && /^[a-f\d]{64}$/i.test(item.fingerprint) && nullableText(item.actual_as_of) && nullableText(item.owner_assigned_baseline) && nullableText(item.business_version) &&
            (item.identity === undefined || identity(item.identity)))) return false;
        // These checks verify shape, identity and counts only. Financial totals,
        // rankings and shares are consumed exactly as returned by the backend.
        const cov = report.coverage;
        if (kpis.matched_configuration_count !== cov.configured || cov.calculated + cov.excluded !== cov.configured ||
            report.detail_rows.length !== cov.configured || breakdowns.products.length !== cov.calculated) return false;
        const validRows = report.detail_rows.filter(row => row.state === 'OK');
        if (validRows.length !== cov.calculated) return false;
        const selectedKeys = new Set(report.detail_rows.map(row => identityKey(row.identity)));
        const calculatedKeys = new Set(validRows.map(row => identityKey(row.identity)));
        const productKeys = new Set(breakdowns.products.map(row => identityKey(row.identity)));
        if (selectedKeys.size !== report.detail_rows.length || productKeys.size !== breakdowns.products.length ||
            breakdowns.products.some(row => row.state !== 'OK' || !calculatedKeys.has(identityKey(row.identity)))) return false;
        if (report.scope && report.detail_rows.some(row => row.identity.factory_id !== report.scope.factory.id ||
            (report.scope.selection.category !== '__ALL__' && row.identity.category !== report.scope.selection.category) ||
            (report.scope.selection.subcategory !== '__ALL__' && row.identity.subcategory !== report.scope.selection.subcategory))) return false;
        if (!report.scope && report.detail_rows.length) return false;
        if (report.state === 'OK') {
            if (kpis.projected_total === null || kpis.partial_total !== null || kpis.partial_total_label !== null || !cov.calculated || cov.excluded) return false;
        } else if (report.state === 'PARTIAL') {
            if (kpis.projected_total !== null || kpis.partial_total === null || kpis.partial_total_label !== 'مجموع جزئی' || !cov.calculated || !cov.excluded) return false;
        } else if (kpis.projected_total !== null || kpis.partial_total !== null || kpis.partial_total_label !== null || cov.calculated) return false;
        if (cov.calculated) {
            if (!report.period || breakdowns.drivers.length !== 7 || new Set(breakdowns.drivers.map(row => row.id)).size !== 7 ||
                breakdowns.factory_pools.length !== 6 || new Set(breakdowns.factory_pools.map(row => row.id)).size !== 6 ||
                top.id === null || top.value === null || top.tie === null || !top.tied_ids.includes(top.id) ||
                new Set(top.tied_ids).size !== top.tied_ids.length || top.tie !== (top.tied_ids.length > 1) ||
                breakdowns.drivers.some(row => row.value === null) ||
                breakdowns.factory_pools.some(row => ['raw_total', 'modeled_selected_total', 'selected_minus_raw', 'modeled_category_total', 'category_minus_raw'].some(key => row[key] === null))) return false;
        } else if (breakdowns.drivers.length || breakdowns.factory_pools.length || top.id !== null || top.value !== null ||
            top.share !== null || top.tie !== null || top.tied_ids.length || average.value !== null || average.numerator !== null ||
            average.denominator !== null || report.arithmetic_reconciliation !== null) return false;
        return true;
    }

    function fa(value) {
        return window.JalaliDate ? window.JalaliDate.toPersianDigits(value) : String(value);
    }

    function formatDecimal(raw) { return window.DashboardNumbers.format(raw, { compact: false }); }

    function formatDate(raw) {
        if (!raw || !window.JalaliDate) return 'در دسترس نیست';
        try { return window.JalaliDate.formatDateOnly(raw, 'در دسترس نیست'); }
        catch (error) { return 'در دسترس نیست'; }
    }

    function formatDateTime(raw) {
        if (!raw || !window.JalaliDate) return 'در دسترس نیست';
        if (dateOnly(raw)) return formatDate(raw);
        try { return window.JalaliDate.formatDateTime(raw, true, 'در دسترس نیست'); }
        catch (error) { return 'در دسترس نیست'; }
    }

    function resolveRoot(root) {
        const candidate = root || window.document;
        return candidate.nodeType === 9 ? candidate.getElementById('costDashboard') : candidate;
    }

    function node(doc, tag, content, className, id) {
        const result = doc.createElement(tag);
        if (content !== undefined && content !== null) result.textContent = content;
        if (className) result.className = className;
        if (id) result.id = id;
        return result;
    }

    function amount(doc, raw, id, unit, options) {
        return window.DashboardNumbers.value(doc, raw, { unit: unit || 'IRR/period', compact: true, id, ...options });
    }

    function table(doc, parent, id, caption, headers) {
        const wrapper = node(doc, 'div', null, 'report-table-scroll');
        const result = node(doc, 'table', null, 'table report-table', id);
        result.appendChild(node(doc, 'caption', caption));
        const head = node(doc, 'thead');
        const tr = node(doc, 'tr');
        headers.forEach(header => { const th = node(doc, 'th', header); th.scope = 'col'; tr.appendChild(th); });
        head.appendChild(tr);
        const body = node(doc, 'tbody');
        result.append(head, body); wrapper.appendChild(result); parent.appendChild(wrapper);
        return body;
    }

    function cell(doc, row, content) {
        const td = node(doc, 'td');
        if (content && content.nodeType) td.appendChild(content);
        else td.textContent = content == null ? 'در دسترس نیست' : content;
        row.appendChild(td);
        return td;
    }

    function identityText(value) { return IDENTITY_FIELDS.map(key => value[key]).join(' / '); }
    function sourceText(source) {
        if (source.startsWith('pool:') && driver(source.slice(5))) return 'مخزن ' + DRIVER_LABELS[source.slice(5)];
        return SOURCE_LABELS[source] || 'منبع ورودی';
    }

    function section(doc, parent, title, id) {
        const result = node(doc, 'section', null, 'report-section', id);
        result.appendChild(node(doc, 'h3', title)); parent.appendChild(result);
        return result;
    }

    function disclosure(doc, parent, title, id) {
        const result = node(doc, 'details', null, 'report-disclosure', id);
        result.appendChild(node(doc, 'summary', title)); parent.appendChild(result);
        return result;
    }

    function appendMeta(doc, parent, label, value) {
        const paragraph = node(doc, 'p', null, 'report-secondary');
        paragraph.appendChild(node(doc, 'strong', label + ': '));
        if (value && value.nodeType) paragraph.appendChild(value);
        else paragraph.appendChild(node(doc, 'span', value));
        parent.appendChild(paragraph);
    }

    function clear(root) {
        const target = resolveRoot(root);
        if (!target) return;
        const active = views.get(target);
        if (active) { active.table.destroy(); active.charts.destroy(); }
        views.delete(target);
        const doc = target.ownerDocument;
        // Exact-value listeners and their weak registrations are shared with
        // the independent Sensitivity panel. Keep those sibling controls live.
        window.DashboardNumbers.closeAll(doc);
        // Keep the controller's original button and its listener when relocating
        // CSV between the selection panel and the accepted report toolbar.
        const exportButton = doc.getElementById('downloadCsvBtn');
        const actions = doc.getElementById('selectionActions');
        if (exportButton && actions && target.contains(exportButton)) actions.appendChild(exportButton);
        target.replaceChildren();
        target.hidden = true;
        target.style.display = 'none';
        delete target.dataset.state;
    }

    function render(report, root) {
        if (!validate(report)) throw new Error('UNSUPPORTED_REPORT_SCHEMA');
        const target = resolveRoot(root);
        if (!target) throw new Error('REPORT_CONTAINER_MISSING');
        clear(target);
        const doc = target.ownerDocument;
        const numbers = window.DashboardNumbers;
        target.hidden = false; target.style.display = ''; target.dataset.state = report.state;
        const cov = report.coverage;

        const toolbar = node(doc, 'header', null, 'report-toolbar', 'reportToolbar');
        const summary = node(doc, 'div', null, 'report-toolbar-summary');
        const heading = node(doc, 'div', null, 'report-toolbar-heading');
        heading.appendChild(node(doc, 'h2', 'نمای هزینه'));
        heading.appendChild(node(doc, 'span', STATE_LABELS[report.state], 'report-status-badge ' +
            (report.state === 'OK' ? 'is-ok' : 'is-excluded'), 'reportStatus'));
        heading.lastElementChild.dataset.state = report.state;
        summary.appendChild(heading);
        const selection = report.scope ? report.scope.selection : null;
        const selected = selection ? ['category', 'subcategory', 'product'].map(key => selection[key] === '__ALL__' ? 'همه' : selection[key] || '—') : [];
        // Composite references are canonical keys. Use the selected row's human
        // identity in the summary, never reinterpret or expose the encoded key.
        if (selection && selection.product !== '__ALL__' && report.detail_rows.length === 1) selected[2] = report.detail_rows[0].identity.product;
        summary.appendChild(node(doc, 'p', report.scope ? report.scope.factory.name + ' · ' + selected.join(' / ') : 'دامنه معتبر موجود نیست', 'report-scope'));
        const meta = node(doc, 'div', null, 'report-toolbar-meta');
        meta.appendChild(node(doc, 'span', report.period ? 'دوره ' + report.period.id + ' · ' + formatDate(report.period.start) + ' تا ' + formatDate(report.period.end) : 'دوره معتبر موجود نیست', null, 'reportPeriod'));
        meta.appendChild(node(doc, 'span', 'محاسبه: ' + formatDateTime(report.calculated_at), null, 'reportCalculatedAt'));
        summary.appendChild(meta); toolbar.appendChild(summary);
        const actions = node(doc, 'div', null, 'report-toolbar-actions');
        const exportButton = doc.getElementById('downloadCsvBtn');
        if (exportButton) actions.appendChild(exportButton);
        toolbar.appendChild(actions); target.appendChild(toolbar);

        if (report.state === 'PARTIAL') {
            const warning = node(doc, 'div', null, 'report-partial');
            warning.setAttribute('role', 'note');
            warning.appendChild(node(doc, 'strong', 'مجموع جزئی'));
            warning.appendChild(node(doc, 'span', fa(cov.excluded) + ' پیکربندی کنار گذاشته شده؛ اعداد فقط موارد محاسبه‌شده منتخب را پوشش می‌دهند. دلیل‌ها در جدول آمده است.'));
            target.appendChild(warning);
        } else if (report.state !== 'OK') {
            target.appendChild(node(doc, 'p', report.state === 'NO_MATCH' ? 'پیکربندی منطبقی یافت نشد.' : STATE_LABELS[report.state] + '؛ پوشش و دلیل‌ها را بررسی کنید.', 'report-partial'));
        }

        const coverage = node(doc, 'div', null, 'report-coverage', 'coverageSummary');
        const coverageText = node(doc, 'div', null, 'report-coverage-text');
        coverageText.appendChild(node(doc, 'strong', 'پوشش محاسبه'));
        coverageText.appendChild(amount(doc, cov.percentage, 'coveragePercentage', 'percentage', { compact: false, coverage: cov }));
        coverageText.appendChild(node(doc, 'span', 'ثبت‌شده ' + fa(cov.configured) + ' · محاسبه‌شده ' + fa(cov.calculated) + ' · کنارگذاشته‌شده ' + fa(cov.excluded)));
        coverage.appendChild(coverageText);
        const track = node(doc, 'div', null, 'report-coverage-track');
        track.setAttribute('aria-hidden', 'true');
        const fill = node(doc, 'span');
        // A CSS coordinate only; the displayed percentage and exact access come
        // from the string formatter, with incomplete coverage guarded there.
        if (cov.percentage !== null && numbers.compare(cov.percentage, '0') >= 0 && numbers.compare(cov.percentage, '100') <= 0) fill.style.width = cov.percentage + '%';
        track.appendChild(fill); coverage.appendChild(track); target.appendChild(coverage);

        const kpis = node(doc, 'div', null, 'report-kpis');
        function kpi(title, raw, id, unit, supporting, options) {
            const card = node(doc, 'section', null, 'report-kpi');
            card.appendChild(node(doc, 'h3', title, null, id === 'totalCost' ? 'totalCostLabel' : undefined));
            const value = amount(doc, raw, id, unit, options);
            if (value.textContent.length > 32) value.classList.add('is-long-number');
            card.appendChild(value);
            if (supporting) card.appendChild(node(doc, 'p', supporting, 'report-kpi-support'));
            kpis.appendChild(card); return card;
        }
        kpi(report.state === 'PARTIAL' ? 'مجموع جزئی' : 'هزینه پیش‌بینی‌شده', report.state === 'PARTIAL' ? report.kpis.partial_total : report.kpis.projected_total,
            'totalCost', 'IRR/period', 'پیکربندی‌های منتخب محاسبه‌شده');
        const average = report.kpis.weighted_average;
        kpi('میانگین موزون هزینه واحد', average.value, 'avgCost', 'IRR/product', 'وزن‌دهی بر مبنای برنامه تولید', { state: average.state });
        kpi('پیکربندی‌های منطبق', String(report.kpis.matched_configuration_count), 'productCount', 'configuration',
            fa(cov.calculated) + ' محاسبه‌شده · ' + fa(cov.excluded) + ' کنارگذاشته‌شده');
        const top = report.kpis.top_cost_driver;
        const topCard = kpi('عامل غالب هزینه', top.value, 'topDriverValue', 'IRR/period');
        const topName = node(doc, 'p', top.id === null ? 'در دسترس نیست' : DRIVER_LABELS[top.id], 'report-driver-name', 'topDriver');
        topCard.insertBefore(topName, topCard.children[1]);
        const share = node(doc, 'p', null, 'report-kpi-support');
        share.append(node(doc, 'span', 'سهم گزارش: '), amount(doc, top.share, 'topDriverShare', 'percentage', { compact: false })); topCard.appendChild(share);
        if (top.tie) {
            const ties = node(doc, 'details', null, 'report-ties');
            ties.appendChild(node(doc, 'summary', fa(top.tied_ids.length) + ' عامل هم‌رتبه'));
            ties.appendChild(node(doc, 'p', top.tied_ids.map(id => DRIVER_LABELS[id]).join('، '))); topCard.appendChild(ties);
        }
        target.appendChild(kpis);
        target.appendChild(node(doc, 'p', 'اعداد برای نمایش تا دو رقم اعشار گرد شده‌اند. برای مقدار کامل و کپی دقیق، روی عدد بروید یا آن را انتخاب کنید.', 'report-format-note'));

        const chartContainer = node(doc, 'div', null, 'report-charts'); target.appendChild(chartContainer);
        const detail = section(doc, target, 'جزئیات پیکربندی‌ها', 'reportConfigurations');
        let chartController;
        const tableController = window.DashboardTable.mount(report, detail, { onFocusCleared: () => {
            if (chartController && chartController.clearFocus) chartController.clearFocus();
        } });
        chartController = window.DashboardCharts.mount(report, chartContainer, {
            onProductFocus: value => tableController.focus(value), onResetFocus: () => tableController.resetFocus()
        });
        views.set(target, { table: tableController, charts: chartController });

        if (report.issues.length) {
            const problems = disclosure(doc, target, 'دلیل‌های ورودی و پوشش (' + fa(report.issues.length) + ')', 'reportIssues');
            const list = node(doc, 'ul', null, 'report-issue-list');
            report.issues.forEach(problem => list.appendChild(node(doc, 'li', (problem.identity ? identityText(problem.identity) + '؛ ' : '') + problem.message)));
            problems.appendChild(list);
        }

        const pools = disclosure(doc, target, 'مقایسه مخازن کارخانه و مبالغ مدل‌شده', 'reportPools');
        pools.appendChild(node(doc, 'p', 'خام: کل کارخانه. مدل منتخب: پیکربندی‌های منتخب محاسبه‌شده. مدل دسته: کل جمعیت برنامه تولید دسته‌های گزارش‌شده. اختلاف دامنه‌ها الزام برابری ندارد.', 'report-secondary'));
        const poolBody = table(doc, pools, 'poolTable', 'ریال / دوره؛ هر ستون جمعیت مشخص خود را دارد.', ['مخزن', 'خام کل کارخانه', 'مدل منتخب', 'منتخب منهای خام', 'مدل کامل دسته‌ها', 'دسته‌ها منهای خام']);
        report.breakdowns.factory_pools.forEach(item => {
            const row = node(doc, 'tr'); cell(doc, row, DRIVER_LABELS[item.id]);
            ['raw_total', 'modeled_selected_total', 'selected_minus_raw', 'modeled_category_total', 'category_minus_raw'].forEach(key => cell(doc, row, amount(doc, item[key])));
            poolBody.appendChild(row);
            const categories = node(doc, 'tr'); const td = cell(doc, categories, null); td.colSpan = 6;
            item.categories.forEach(category => {
                const line = node(doc, 'p', null, 'report-secondary');
                line.append(node(doc, 'strong', category.category + ': '), node(doc, 'span', 'مخزن تعدیل‌شده '), amount(doc, category.adjusted_pool),
                    node(doc, 'span', ' · برنامه تولید کامل دسته '), amount(doc, category.prediction_denominator, undefined, 'product/period'));
                td.appendChild(line);
            });
            poolBody.appendChild(categories);
        });
        if (!report.breakdowns.factory_pools.length) { const row = node(doc, 'tr'); cell(doc, row, 'مخزن مدل‌شده‌ای موجود نیست.').colSpan = 6; poolBody.appendChild(row); }

        const technical = disclosure(doc, target, 'جزئیات فنی گزارش', 'reportTechnical');
        appendMeta(doc, technical, 'نسخه فرمول', node(doc, 'code', report.formula_version, 'report-machine-value'));
        const weighted = section(doc, technical, 'میانگین موزون');
        appendMeta(doc, weighted, 'صورت؛ هزینه پیش‌بینی‌شده منتخب', amount(doc, average.numerator, 'weightedNumerator'));
        appendMeta(doc, weighted, 'مخرج؛ برنامه تولید منتخب', amount(doc, average.denominator, 'weightedDenominator', 'product/period'));
        weighted.appendChild(node(doc, 'p', 'جمعیت: پیکربندی‌های منتخب محاسبه‌شده؛ پوشش همان شمار پیکربندی گزارش است.', 'report-secondary'));
        const arithmetic = section(doc, technical, 'تطبیق جمع Decimal', 'reportPrecision');
        if (report.arithmetic_reconciliation) {
            const trace = report.arithmetic_reconciliation;
            appendMeta(doc, arithmetic, 'مجموع ردیف‌های پیش‌بینی‌شده', amount(doc, trace.projected_rows_total));
            appendMeta(doc, arithmetic, 'مجموع اجزای عوامل', amount(doc, trace.driver_components_total));
            appendMeta(doc, arithmetic, 'اختلاف ردیف‌ها منهای عوامل', amount(doc, trace.difference));
            arithmetic.appendChild(node(doc, 'p', 'اختلاف فنی از ترتیب جمع Decimal گزارش شده است؛ مبلغ‌های اصلی بدون تغییر حفظ شده‌اند.', 'report-secondary'));
        } else arithmetic.appendChild(node(doc, 'p', 'تطبیق برای این وضعیت قابل محاسبه نیست.'));
        const lineage = section(doc, technical, 'زمان و شناسنامه منابع مجاز', 'reportLineage');
        lineage.appendChild(node(doc, 'p', 'زمان واقعی منبع، خط مبنای مالک و زمان محاسبه مستقل‌اند. اثر انگشت تاریخ تاریخی منبع را اثبات نمی‌کند.', 'report-secondary'));
        const lineageBody = table(doc, lineage, 'lineageTable', 'شناسنامه عمومی منابع؛ بدون مسیر فایل یا پارامترهای ورودی.', ['منبع', 'هویت پیکربندی', 'زمان واقعی منبع', 'خط مبنای مالک', 'نسخه تجاری', 'اثر انگشت']);
        report.source_lineage.forEach(item => {
            const row = node(doc, 'tr'); cell(doc, row, sourceText(item.source)); cell(doc, row, item.identity ? identityText(item.identity) : '—');
            cell(doc, row, formatDateTime(item.actual_as_of)); cell(doc, row, formatDate(item.owner_assigned_baseline)); cell(doc, row, item.business_version || 'در دسترس نیست');
            cell(doc, row, numbers.identifier(doc, item.fingerprint)); lineageBody.appendChild(row);
        });
        return report;
    }

    function csvText(value) {
        const raw = value == null ? '' : String(value);
        // Quoting is CSV syntax, not spreadsheet formula protection. Prefix
        // untrusted text; signed numeric columns use csvNumber instead.
        return /^[\s\u0000-\u001f]*[=+\-@]/.test(raw) || /^[\u0000-\u001f]/.test(raw) ? "'" + raw : raw;
    }

    function csvNumber(value) {
        if (value === null || value === undefined) return '';
        const raw = String(value);
        if (!DECIMAL.test(raw)) throw new Error('INVALID_DECIMAL');
        return raw;
    }

    function quoted(value) { return '"' + String(value).replace(/"/g, '""') + '"'; }

    function csv(report) {
        if (!validate(report)) throw new Error('UNSUPPORTED_REPORT_SCHEMA');
        const scope = report.scope;
        const cov = report.coverage;
        const period = report.period;
        const metadataHeaders = ['report_state', 'partial_total_label', 'report_note', 'formula_version', 'factory_scope', 'category_selection', 'subcategory_selection', 'product_selection',
            'population', 'allocation_population', 'period_id', 'period_start', 'period_end', 'period_start_jalali', 'period_end_jalali',
            'calculated_at', 'coverage_configured', 'coverage_calculated', 'coverage_excluded', 'coverage_percentage'];
        const metadata = {
            report_state: report.state, partial_total_label: report.kpis.partial_total_label,
            report_note: report.state === 'PARTIAL' ? 'مجموع جزئی؛ فقط پیکربندی‌های منتخب محاسبه‌شده، با کنارگذاشتن ردیف‌های دارای مسئله.' : STATE_LABELS[report.state],
            formula_version: report.formula_version,
            factory_scope: scope && scope.factory.id,
            category_selection: scope && scope.selection.category, subcategory_selection: scope && scope.selection.subcategory,
            product_selection: scope && scope.selection.product, population: scope && scope.population,
            allocation_population: scope && scope.allocation_population, period_id: period && period.id,
            period_start: period && period.start, period_end: period && period.end,
            period_start_jalali: period ? formatDate(period.start) : '', period_end_jalali: period ? formatDate(period.end) : '',
            calculated_at: report.calculated_at, coverage_configured: cov.configured, coverage_calculated: cov.calculated,
            coverage_excluded: cov.excluded, coverage_percentage: cov.percentage
        };
        const headers = ['row_type', ...IDENTITY_FIELDS, 'row_state', 'issue_codes', 'issue_messages',
            'unit_cost', 'unit_cost_unit', 'prediction', 'prediction_unit', 'projected_cost', 'projected_cost_unit',
            ...metadataHeaders, 'projected_total', 'partial_total', 'total_unit', 'weighted_average', 'weighted_numerator',
            'weighted_denominator', 'weighted_unit', 'weighted_state', 'top_driver_id', 'top_driver_value', 'top_driver_share',
            'top_driver_tie', 'top_driver_tied_ids', 'driver_id', 'driver_label', 'value', 'share', 'unit', 'pool_id', 'pool_label',
            'raw_total', 'raw_scope', 'modeled_selected_total', 'modeled_selected_scope', 'selected_minus_raw',
            'modeled_category_total', 'modeled_category_scope', 'category_minus_raw', 'adjusted_pool', 'prediction_denominator',
            'projected_rows_total', 'driver_components_total', 'difference'];
        const numeric = new Set(['unit_cost', 'prediction', 'projected_cost', 'coverage_configured', 'coverage_calculated',
            'coverage_excluded', 'coverage_percentage', 'projected_total', 'partial_total', 'weighted_average',
            'weighted_numerator', 'weighted_denominator', 'top_driver_value', 'top_driver_share', 'value', 'share', 'raw_total',
            'modeled_selected_total', 'selected_minus_raw', 'modeled_category_total', 'category_minus_raw',
            'adjusted_pool', 'prediction_denominator', 'projected_rows_total', 'driver_components_total', 'difference']);
        const lines = [];
        lines.push(headers.map(quoted).join(','));
        const push = row => {
            const values = Object.assign({}, metadata, row);
            lines.push(headers.map(key => quoted(numeric.has(key) ? csvNumber(values[key]) : csvText(values[key]))).join(','));
        };
        const issueFields = problems => ({ issue_codes: problems.map(problem => problem.code).join(';'), issue_messages: problems.map(problem => problem.message).join('؛ ') });
        if (report.detail_rows.length) report.detail_rows.forEach(row => push(Object.assign({
            row_type: 'configuration', row_state: row.state, unit_cost: row.unit_cost, unit_cost_unit: row.unit,
            prediction: row.prediction, prediction_unit: row.prediction_unit, projected_cost: row.projected_cost,
            projected_cost_unit: row.projected_cost_unit
        }, row.identity, issueFields(row.issues))));
        else push(Object.assign({ row_type: 'report', row_state: report.state }, issueFields(report.issues)));
        const avg = report.kpis.weighted_average, top = report.kpis.top_cost_driver;
        push(Object.assign({ row_type: 'kpis', projected_total: report.kpis.projected_total, partial_total: report.kpis.partial_total,
            total_unit: 'IRR/period', weighted_average: avg.value, weighted_numerator: avg.numerator, weighted_denominator: avg.denominator,
            weighted_unit: avg.unit, weighted_state: avg.state, top_driver_id: top.id, top_driver_value: top.value,
            top_driver_share: top.share, top_driver_tie: top.tie, top_driver_tied_ids: top.tied_ids.join(';') }, issueFields(report.issues)));
        report.breakdowns.drivers.forEach(row => push({ row_type: 'driver', driver_id: row.id, driver_label: DRIVER_LABELS[row.id],
            value: row.value, share: row.share, unit: row.unit }));
        report.breakdowns.factory_pools.forEach(row => {
            push({ row_type: 'factory_pool', pool_id: row.id, pool_label: DRIVER_LABELS[row.id], raw_total: row.raw_total,
                raw_scope: row.raw_scope, modeled_selected_total: row.modeled_selected_total, modeled_selected_scope: row.modeled_selected_scope,
                selected_minus_raw: row.selected_minus_raw, modeled_category_total: row.modeled_category_total,
                modeled_category_scope: row.modeled_category_scope, category_minus_raw: row.category_minus_raw, unit: row.unit });
            row.categories.forEach(category => push({ row_type: 'pool_category', pool_id: row.id, pool_label: DRIVER_LABELS[row.id],
                category: category.category, adjusted_pool: category.adjusted_pool, prediction_denominator: category.prediction_denominator, unit: row.unit }));
        });
        if (report.arithmetic_reconciliation) {
            const trace = report.arithmetic_reconciliation;
            push({ row_type: 'arithmetic_reconciliation', projected_rows_total: trace.projected_rows_total,
                driver_components_total: trace.driver_components_total, difference: trace.difference, unit: trace.unit });
        }
        return '\uFEFF' + lines.join('\r\n') + '\r\n';
    }

    window.DashboardReport = Object.freeze({ validate, render, clear, csv, formatDecimal });
})(window);
