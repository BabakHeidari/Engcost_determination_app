(function (window) {
    'use strict';

    // The accepted API strings remain authoritative. This view does not sum
    // contributions, derive predictions, or reconstruct permission-omitted
    // inputs. Number is used only to obtain finite ECharts coordinates.
    const DRIVERS = Object.freeze({
        BOM: 'مواد و اقلام BOM',
        AdministrativeandResearch: 'اداری و پژوهش',
        Payroll: 'حقوق و دستمزد',
        Overhead: 'سربار',
        FinancialCosts: 'هزینه‌های مالی',
        Depriciation: 'استهلاک',
        NonOperationalCostsandIncomes: 'هزینه‌ها و درآمدهای غیرعملیاتی'
    });
    const DRIVER_IDS = Object.keys(DRIVERS);
    const SOURCE_LABELS = Object.freeze({
        bom: 'BOM پیکربندی', materials: 'قیمت مواد', exchange_rates: 'نرخ ارز',
        predictions: 'برنامه تولید', weights: 'سهم دسته', shares: 'سهم دسته',
        loss_recyclability: 'ضایعات و بازیافت', configuration: 'پیکربندی کارخانه',
        period_binding: 'اتصال دوره'
    });
    const STATES = Object.freeze({
        OK: 'محاسبه‌شده', MISSING_INPUT: 'ورودی لازم موجود نیست',
        INVALID_INPUT: 'ورودی نامعتبر', AMBIGUOUS_INPUT: 'ورودی مبهم',
        CALCULATION_ERROR: 'خطای محاسبه', NOT_APPLICABLE: 'قابل اعمال نیست'
    });
    const own = (value, field) => value && Object.prototype.hasOwnProperty.call(value, field);

    function node(doc, tag, text, className) {
        const result = doc.createElement(tag);
        if (text !== undefined && text !== null) result.textContent = text;
        if (className) result.className = className;
        return result;
    }

    function date(raw, dateTime) {
        if (!raw || !window.JalaliDate) return 'در دسترس نیست';
        try {
            return dateTime ? window.JalaliDate.formatDateTime(raw, true, 'در دسترس نیست') :
                window.JalaliDate.formatDateOnly(raw, 'در دسترس نیست');
        } catch (_) { return 'در دسترس نیست'; }
    }

    function sourceLabel(source) {
        if (source.startsWith('pool:') && own(DRIVERS, source.slice(5))) return 'مخزن ' + DRIVERS[source.slice(5)];
        return SOURCE_LABELS[source] || 'منبع ورودی';
    }

    function table(doc, parent, kind, caption, headings) {
        const wrapper = node(doc, 'div', null, 'table-responsive');
        const result = node(doc, 'table', null, 'table report-table sens-table');
        result.dataset.sensitivityTable = kind;
        result.appendChild(node(doc, 'caption', caption));
        const head = node(doc, 'thead');
        const headingRow = node(doc, 'tr');
        headings.forEach(heading => {
            const cell = node(doc, 'th', heading);
            cell.scope = 'col';
            headingRow.appendChild(cell);
        });
        head.appendChild(headingRow);
        const body = node(doc, 'tbody');
        result.append(head, body);
        wrapper.appendChild(result);
        parent.appendChild(wrapper);
        return body;
    }

    function cell(doc, row, value) {
        const result = node(doc, 'td');
        if (value && value.nodeType) result.appendChild(value);
        else result.textContent = value === null || value === undefined ? 'در دسترس نیست' : value;
        row.appendChild(result);
        return result;
    }

    // Axis ticks are approximate chart coordinates, not accepted amounts.
    function tickDecimal(coordinate) {
        const text = String(coordinate);
        const exponent = text.match(/^([+-]?)(\d+)(?:\.(\d+))?e([+-]?\d+)$/i);
        if (!exponent) return text;
        const digits = exponent[2] + (exponent[3] || '');
        const point = exponent[2].length + Number(exponent[4]);
        if (point <= 0) return exponent[1] + '0.' + '0'.repeat(-point) + digits;
        if (point >= digits.length) return exponent[1] + digits + '0'.repeat(point - digits.length);
        return exponent[1] + digits.slice(0, point) + '.' + digits.slice(point);
    }

    function driverRows(baseline, scenario) {
        const baselineDrivers = new Map((baseline?.breakdown?.driver_components || []).map(item => [item.pool_id, item]));
        const scenarioDrivers = new Map((scenario?.breakdown?.driver_components || []).map(item => [item.pool_id, item]));
        return DRIVER_IDS.map(id => ({
            id, label: DRIVERS[id],
            baseline: id === 'BOM' ? baseline?.bom_total ?? null : baselineDrivers.get(id)?.per_unit_contribution ?? null,
            scenario: id === 'BOM' ? scenario?.bom_total ?? null : scenarioDrivers.get(id)?.per_unit_contribution ?? null
        }));
    }

    function mount(container) {
        const doc = container.ownerDocument;
        const numbers = window.DashboardNumbers;
        const panel = container.closest('[role="tabpanel"]');
        let active = !panel || !panel.hidden;
        let destroyed = false;
        let chart = null;
        let chartPlan = null;
        let observer = null;
        let pendingFrame = null;
        let renderCleanups = [];
        const cleanups = [];

        function listen(target, event, handler, permanent) {
            target.addEventListener(event, handler);
            (permanent ? cleanups : renderCleanups).push(() => target.removeEventListener(event, handler));
        }

        function disposeChart() {
            if (!chart) return;
            try { chart.dispose(); } catch (_) { /* The numbers and tables remain usable. */ }
            chart = null;
        }

        function stopRender() {
            if (pendingFrame !== null) { window.cancelAnimationFrame(pendingFrame); pendingFrame = null; }
            if (observer) { observer.disconnect(); observer = null; }
            disposeChart();
            renderCleanups.forEach(cleanup => cleanup());
            renderCleanups = [];
            chartPlan = null;
            numbers.closeAll(doc);
        }

        function clear() {
            stopRender();
            container.replaceChildren();
            container.hidden = true;
            delete container.dataset.state;
        }

        function metric(parent, label, raw, unit, key, state, signed) {
            const card = node(doc, 'div', null, 'sens-summary-item sens-result-card');
            card.appendChild(node(doc, 'p', label, 'sens-result-label'));
            const value = node(doc, 'div', null, 'sens-result-number');
            value.dataset.sensitivityMetric = key;
            // A presentation prefix provides the positive sign without changing
            // the original string used by the exact-value/copy popover.
            if (signed && raw !== null && raw !== undefined && numbers.compare(raw, '0') >= 0) {
                const sign = node(doc, 'span', '+', 'sens-positive-sign');
                sign.setAttribute('aria-hidden', 'true');
                value.appendChild(sign);
            }
            value.appendChild(numbers.value(doc, raw, { unit, compact: true, state }));
            card.appendChild(value);
            parent.appendChild(card);
            return card;
        }

        function context(snapshot) {
            const result = node(doc, 'div', null, 'sens-context');
            if (snapshot.identity) result.appendChild(node(doc, 'p',
                snapshot.identity.product + ' | ' + snapshot.identity.category + ' / ' + snapshot.identity.subcategory +
                ' — کارخانه: ' + snapshot.identity.factory_id));
            if (snapshot.period) result.appendChild(node(doc, 'p', 'دوره ' + snapshot.period.id + '؛ ' +
                date(snapshot.period.start) + ' تا ' + date(snapshot.period.end)));
            result.appendChild(node(doc, 'p', 'مبالغ پیش‌بینی‌شده فقط برای همین پیکربندی هستند.', 'sens-help'));
            container.appendChild(result);
        }

        function summary(snapshot) {
            const baseline = snapshot.baseline;
            const scenario = snapshot.scenario;
            const comparison = scenario !== null && scenario !== undefined;
            const grid = node(doc, 'div', null, 'sens-result-kpis');
            metric(grid, 'هزینه واحد خط‌مبنا', baseline?.unit_cost ?? null, 'IRR/product', 'baseline-unit-cost', baseline?.state);
            if (comparison) metric(grid, 'هزینه واحد سناریو', scenario.unit_cost, 'IRR/product', 'scenario-unit-cost', scenario.state);
            if (comparison) {
                metric(grid, 'تغییر هزینه واحد (سناریو منهای خط‌مبنا)', snapshot.delta?.amount ?? null,
                    'IRR/product', 'delta-amount', snapshot.delta ? 'OK' : scenario.state, true);
                const percentage = metric(grid, 'درصد تغییر هزینه واحد', snapshot.delta?.percentage ?? null,
                    'percentage', 'delta-percentage', snapshot.delta?.percentage_state || scenario.state, true);
                if (snapshot.delta?.percentage_state === 'NOT_APPLICABLE') percentage.appendChild(node(doc, 'p',
                    'هزینه واحد خط‌مبنا صفر است؛ درصد تغییر قابل اعمال نیست.', 'sens-help'));
            } else {
                metric(grid, 'هزینه پیش‌بینی‌شده همین پیکربندی — خط‌مبنا', baseline?.projected_cost ?? null,
                    'IRR/period', 'baseline-projected-cost', baseline?.state);
                metric(grid, 'جمع BOM خط‌مبنا', baseline?.bom_total ?? null, 'IRR/product', 'baseline-bom-total', baseline?.state);
                metric(grid, 'جمع عوامل کارخانه‌ای خط‌مبنا', baseline?.driver_total ?? null,
                    'IRR/product', 'baseline-driver-total', baseline?.state);
            }
            container.appendChild(grid);
            if (comparison) {
                const projection = node(doc, 'div', null, 'sens-projected-grid');
                metric(projection, 'هزینه پیش‌بینی‌شده همین پیکربندی — خط‌مبنا', baseline?.projected_cost ?? null,
                    'IRR/period', 'baseline-projected-cost', baseline?.state);
                metric(projection, 'هزینه پیش‌بینی‌شده همین پیکربندی — سناریو', scenario.projected_cost,
                    'IRR/period', 'scenario-projected-cost', scenario.state);
                container.appendChild(projection);
            }
            if (baseline && baseline.state !== 'OK') container.appendChild(node(doc, 'p',
                'خط‌مبنا: ' + (STATES[baseline.state] || 'در دسترس نیست'), 'dashboard-status is-warning'));
            if (comparison && scenario.state !== 'OK') container.appendChild(node(doc, 'p',
                'سناریو: ' + (STATES[scenario.state] || 'در دسترس نیست'), 'dashboard-status is-warning'));
        }

        function chartFallback() {
            if (!chartPlan) return;
            chartPlan.element.hidden = true;
            chartPlan.note.textContent = 'نمودار در دسترس نیست؛ جدول همراه همه مقادیر دقیق و انتخاب ردیف‌ها را نشان می‌دهد.';
            disposeChart();
        }

        function highlight(index, selected) {
            if (!chartPlan) return;
            chartPlan.hovered = index;
            if (selected) chartPlan.selected = chartPlan.selected === index ? null : index;
            chartPlan.rows.forEach((row, rowIndex) => {
                row.classList.toggle('is-focused', rowIndex === index);
                row.classList.toggle('is-selected', rowIndex === chartPlan.selected);
                chartPlan.buttons[rowIndex].setAttribute('aria-pressed', String(rowIndex === chartPlan.selected));
            });
            chartPlan.focus.textContent = chartPlan.selected === null ? 'یک عامل را برای تمرکز انتخاب کنید.' :
                'عامل انتخاب‌شده: ' + chartPlan.data[chartPlan.selected].label;
            if (!chart || !chart.dispatchAction) return;
            try {
                chart.dispatchAction({ type: 'downplay' });
                const focus = index === null ? chartPlan.selected : index;
                if (focus !== null) [0, 1].forEach(seriesIndex =>
                    chart.dispatchAction({ type: 'highlight', seriesIndex, dataIndex: focus }));
            } catch (_) { chartFallback(); }
        }

        function options() {
            const data = chartPlan.data;
            const coords = field => {
                if (data.some(row => row[field] === null)) return null;
                const values = data.map(row => Number(row[field]));
                return values.every(Number.isFinite) ? values : null;
            };
            const baseline = coords('baseline'), scenario = coords('scenario');
            if (!baseline || !scenario) return null;
            const font = window.getComputedStyle(doc.documentElement).getPropertyValue('--app-font-family').trim() ||
                'IRANSansX, Tahoma, sans-serif';
            const narrow = chartPlan.element.clientWidth < 420;
            return {
                animation: !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches),
                animationDuration: 300, animationDurationUpdate: 180,
                textStyle: { fontFamily: font, color: '#22364c' },
                legend: { data: ['خط‌مبنا', 'سناریو'], top: 4, textStyle: { fontFamily: font } },
                grid: { left: 10, right: 20, top: 45, bottom: 38, containLabel: true },
                tooltip: {
                    trigger: 'axis', axisPointer: { type: 'shadow' }, renderMode: 'richText', confine: true,
                    backgroundColor: '#fff', borderColor: '#dce6ec', padding: [12, 14],
                    textStyle: { fontFamily: font, color: '#22364c', lineHeight: 23 },
                    formatter: params => {
                        const item = data[(Array.isArray(params) ? params[0] : params)?.dataIndex];
                        return item ? item.label + '\nخط‌مبنا: ' + item.baseline + ' ریال / محصول' +
                            '\nسناریو: ' + item.scenario + ' ریال / محصول' + '\nبرای انتخاب ردیف، روی میله بزنید.' : '';
                    }
                },
                xAxis: {
                    type: 'value', name: 'ریال / محصول', nameLocation: 'middle', nameGap: 29, splitNumber: 3,
                    axisLine: { show: true, onZero: true, lineStyle: { color: '#7e93a7' } },
                    axisTick: { show: false }, splitLine: { lineStyle: { color: '#eaf0f4', type: 'dashed' } },
                    axisLabel: { hideOverlap: true, color: '#65788b', fontSize: 10,
                        formatter: value => numbers.format(tickDecimal(value), { unit: 'IRR', compact: true, showUnit: false }) }
                },
                yAxis: {
                    type: 'category', inverse: true, data: data.map(item => item.label),
                    axisLine: { show: false }, axisTick: { show: false },
                    axisLabel: { color: '#324b63', width: narrow ? 90 : 164, overflow: 'truncate',
                        fontSize: narrow ? 10 : 11, lineHeight: 20, margin: 10 }
                },
                series: [
                    { name: 'خط‌مبنا', type: 'bar', data: baseline, barMaxWidth: 17, itemStyle: { color: '#748b9d' },
                        emphasis: { focus: 'self' } },
                    { name: 'سناریو', type: 'bar', data: scenario, barMaxWidth: 17, itemStyle: { color: '#147f86' },
                        emphasis: { focus: 'self' } }
                ]
            };
        }

        function initializeChart() {
            if (destroyed || !active || !chartPlan || chart) return;
            if (!window.echarts) { chartFallback(); return; }
            const configuration = options();
            if (!configuration) { chartFallback(); return; }
            try {
                chartPlan.element.hidden = false;
                chart = window.echarts.init(chartPlan.element);
                chart.setOption(configuration, true);
                if (chart.on) {
                    chart.on('mouseover', params => { if (Number.isInteger(params.dataIndex)) highlight(params.dataIndex, false); });
                    chart.on('mouseout', () => highlight(null, false));
                    chart.on('click', params => {
                        if (!Number.isInteger(params.dataIndex) || !chartPlan.buttons[params.dataIndex]) return;
                        highlight(params.dataIndex, true);
                        const button = chartPlan.buttons[params.dataIndex];
                        button.scrollIntoView && button.scrollIntoView({ block: 'nearest', behavior: 'auto' });
                        button.focus({ preventScroll: true });
                    });
                }
                chartPlan.note.textContent = 'نمایش میله‌ها تقریبی است؛ مقدار دقیق در راهنمای نمودار و دکمه‌های جدول حفظ می‌شود.';
                highlight(chartPlan.hovered, false);
            } catch (_) { chartFallback(); }
        }

        function comparison(snapshot) {
            const section = node(doc, 'section', null, 'sens-card sens-chart-card');
            section.appendChild(node(doc, 'h3', 'مقایسه سهم هفت عامل در هزینه واحد', 'sens-section-heading'));
            section.appendChild(node(doc, 'p', 'BOM و شش عامل کارخانه‌ای؛ انتخاب یا تمرکز هر ردیف، همان عامل را در نمودار مشخص می‌کند.', 'sens-help'));
            section.appendChild(node(doc, 'p', 'این مقایسه سهم عوامل در سناریوی ترکیبی است؛ اثر مستقل یا علت تغییر هر پارامتر را نشان نمی‌دهد.', 'sens-help'));
            const element = node(doc, 'div', null, 'sens-chart');
            element.dataset.sensitivityChart = 'drivers';
            element.setAttribute('role', 'img');
            element.setAttribute('aria-label', 'نمودار میله‌ای افقی مقایسه خط‌مبنا و سناریو؛ جدول همراه با صفحه‌کلید و لمس قابل استفاده است.');
            const note = node(doc, 'p', 'مقادیر کامل در جدول همراه قابل مشاهده و کپی هستند.', 'sens-chart-note');
            const focus = node(doc, 'p', 'یک عامل را برای تمرکز انتخاب کنید.', 'sens-driver-focus');
            focus.setAttribute('role', 'status');
            focus.setAttribute('aria-live', 'polite');
            section.append(element, note, focus);
            const body = table(doc, section, 'drivers', 'مقادیر هر عامل بر حسب ریال / محصول؛ این مقادیر مستقیماً از پاسخ سرور آمده‌اند.',
                ['عامل هزینه', 'خط‌مبنا', 'سناریو']);
            chartPlan = { element, note, focus, data: driverRows(snapshot.baseline, snapshot.scenario),
                rows: [], buttons: [], selected: null, hovered: null };
            chartPlan.data.forEach((item, index) => {
                const row = node(doc, 'tr', null, 'sens-driver-row');
                row.dataset.driverId = item.id;
                const button = node(doc, 'button', item.label, 'sens-driver-select btn btn-sm btn-outline-secondary');
                button.type = 'button';
                button.dataset.driverId = item.id;
                button.setAttribute('aria-pressed', 'false');
                button.setAttribute('aria-label', 'انتخاب عامل ' + item.label + ' در نمودار و جدول');
                cell(doc, row, button);
                cell(doc, row, numbers.value(doc, item.baseline, { unit: 'IRR/product', compact: true }));
                cell(doc, row, numbers.value(doc, item.scenario, { unit: 'IRR/product', compact: true }));
                body.appendChild(row);
                chartPlan.rows.push(row);
                chartPlan.buttons.push(button);
                listen(row, 'pointerenter', () => highlight(index, false));
                listen(row, 'pointerleave', () => highlight(null, false));
                listen(row, 'focusin', () => highlight(index, false));
                listen(row, 'focusout', event => { if (!row.contains(event.relatedTarget)) highlight(null, false); });
                listen(button, 'click', () => highlight(index, true));
            });
            container.appendChild(section);

            const bomSection = node(doc, 'section', null, 'sens-card');
            bomSection.appendChild(node(doc, 'h3', 'ریز اقلام BOM', 'sens-section-heading'));
            const bomBody = table(doc, bomSection, 'bom', 'هزینه جاری هر ردیف BOM؛ مقادیر تاریخی ذخیره‌شده مبنای این مقایسه نیستند.',
                ['ردیف و ماده', 'هزینه خط‌مبنا', 'هزینه سناریو']);
            const baseline = new Map((snapshot.baseline?.breakdown?.bom_components || []).map(item => [item.row_id, item]));
            const scenario = new Map((snapshot.scenario?.breakdown?.bom_components || []).map(item => [item.row_id, item]));
            const ids = new Set([...baseline.keys(), ...scenario.keys()]);
            ids.forEach(id => {
                const before = baseline.get(id), after = scenario.get(id);
                const row = node(doc, 'tr');
                row.dataset.rowId = id;
                const label = node(doc, 'div', null, 'sens-driver-label');
                label.appendChild(node(doc, 'strong', (before || after).material));
                const identifier = node(doc, 'span', id, 'sens-help');
                identifier.dir = 'ltr';
                label.appendChild(identifier);
                cell(doc, row, label);
                cell(doc, row, numbers.value(doc, before?.live_cost_in_rial ?? null, { unit: 'IRR/product', compact: true }));
                cell(doc, row, numbers.value(doc, after?.live_cost_in_rial ?? null, { unit: 'IRR/product', compact: true }));
                bomBody.appendChild(row);
            });
            if (!ids.size) {
                const row = node(doc, 'tr');
                cell(doc, row, 'ردیف BOM قابل محاسبه‌ای در دسترس نیست.').colSpan = 3;
                bomBody.appendChild(row);
            }
            container.appendChild(bomSection);
        }

        function appliedChanges(snapshot) {
            const section = node(doc, 'section', null, 'sens-card');
            section.appendChild(node(doc, 'h3', 'تغییرهای اعمال‌شده در این سناریو', 'sens-section-heading'));
            const body = table(doc, section, 'overrides', 'مقدارهای خط‌مبنا و نهایی از تغییرهای مؤثر همین پاسخ سرور؛ فقط شبیه‌سازی و بدون ذخیره.',
                ['پارامتر', 'روش تغییر', 'درخواست', 'خط‌مبنای همین اجرا', 'مقدار نهایی', 'واحد منبع']);
            snapshot.effective_overrides.forEach(item => {
                const parameter = snapshot.parameters.find(entry => entry.parameter_id === item.parameter_id);
                const row = node(doc, 'tr');
                row.dataset.parameterId = item.parameter_id;
                cell(doc, row, parameter.label);
                cell(doc, row, item.mode === 'absolute' ? 'مقدار نهایی' : 'تغییر درصدی نسبت به خط‌مبنا');
                cell(doc, row, numbers.value(doc, item.value, {unit: item.mode === 'percent_change' ? 'percent' : item.unit, compact: false}));
                cell(doc, row, numbers.value(doc, item.baseline_value, {unit: item.unit, compact: false}));
                cell(doc, row, numbers.value(doc, item.final_value, {unit: item.unit, compact: false}));
                const unit = node(doc, 'bdi', item.unit); unit.dir = 'ltr'; cell(doc, row, unit);
                body.appendChild(row);
            });
            if (!snapshot.effective_overrides.length) {
                const row = node(doc, 'tr');
                cell(doc, row, 'این سناریو بدون تغییر اجرا شده است.').colSpan = 6;
                body.appendChild(row);
            }
            container.appendChild(section);
        }

        function technical(snapshot) {
            const details = node(doc, 'details', null, 'sens-technical report-disclosure');
            details.appendChild(node(doc, 'summary', 'جزئیات فنی، نسخه فرمول و منشأ داده‌ها'));
            function metadata(label, value) {
                const line = node(doc, 'p', null, 'sens-help');
                line.appendChild(node(doc, 'strong', label + ': '));
                if (value && value.nodeType) line.appendChild(value);
                else line.appendChild(node(doc, 'span', value));
                details.appendChild(line);
            }
            metadata('نسخه فرمول', numbers.identifier(doc, snapshot.formula_version, 'نسخه فرمول'));
            metadata('زمان محاسبه', date(snapshot.calculated_at, true));
            metadata('ماندگاری', 'سناریو فرضی است؛ داده‌های اصلی ذخیره یا تغییر نمی‌کنند.');
            details.appendChild(node(doc, 'p', 'خط‌مبنا و سناریو از snapshot همان پاسخ استفاده می‌کنند. تغییر فرضی، تاریخ یا اثر انگشت تازه‌ای برای منابع ایجاد نمی‌کند.', 'sens-help'));
            const body = table(doc, details, 'lineage', 'منشأ واقعی و مجاز داده‌ها؛ اثر انگشت کامل با نویسه‌های اصلی ASCII قابل مشاهده و کپی است.',
                ['منبع', 'اثر انگشت', 'تاریخ واقعی منبع', 'خط‌مبنای تعیین‌شده مالک', 'نسخه کسب‌وکار']);
            (snapshot.source_lineage || []).forEach(item => {
                const row = node(doc, 'tr');
                cell(doc, row, sourceLabel(item.source));
                cell(doc, row, numbers.identifier(doc, item.fingerprint, 'اثر انگشت ' + sourceLabel(item.source)));
                cell(doc, row, date(item.actual_as_of, true));
                cell(doc, row, date(item.owner_assigned_baseline));
                cell(doc, row, item.business_version);
                body.appendChild(row);
            });
            if (!snapshot.source_lineage?.length) {
                const row = node(doc, 'tr');
                cell(doc, row, 'منشأ مجازی برای نمایش در این پاسخ موجود نیست.').colSpan = 5;
                body.appendChild(row);
            }
            if (snapshot.permissions?.factory_parameters) {
                const results = [['خط‌مبنا', snapshot.baseline], ['سناریو', snapshot.scenario]];
                results.forEach(([label, result]) => {
                    if (own(result, 'prediction')) metadata('برنامه تولید همین پیکربندی — ' + label,
                        numbers.value(doc, result.prediction, { unit: result.prediction_unit, compact: false }));
                });
                const fields = ['raw_factory_pool', 'adjusted_category_pool', 'category_prediction_total', 'modeled_minus_raw'];
                const entries = results.flatMap(([label, result]) => (result?.breakdown?.driver_components || [])
                    .filter(item => fields.every(field => own(item, field))).map(item => ({ label, item })));
                if (entries.length) {
                    const poolBody = table(doc, details, 'authorized-pools', 'مقادیر مجاز مخزن؛ سهم هر محصول و مخرج کامل دسته توسط سرور محاسبه می‌شوند.',
                        ['وضعیت و عامل', 'مخزن کل کارخانه', 'مخزن تعدیل‌شده دسته', 'برنامه تولید کل دسته', 'اختلاف مدل و مخزن خام']);
                    entries.forEach(({ label, item }) => {
                        const row = node(doc, 'tr');
                        cell(doc, row, label + ' — ' + DRIVERS[item.pool_id]);
                        fields.forEach(field => cell(doc, row, numbers.value(doc, item[field], {
                            unit: field === 'category_prediction_total' ? 'product/period' : 'IRR/period', compact: true
                        })));
                        poolBody.appendChild(row);
                    });
                }
            }
            container.appendChild(details);
            listen(details, 'toggle', scheduleResize);
        }

        function render(snapshot) {
            if (destroyed) return;
            clear();
            container.hidden = false;
            container.dataset.state = snapshot.state;
            context(snapshot);
            summary(snapshot);
            if (snapshot.scenario !== null && snapshot.scenario !== undefined) {
                comparison(snapshot);
                appliedChanges(snapshot);
            }
            const issues = [...(snapshot.issues || []), ...(snapshot.baseline?.issues || []), ...(snapshot.scenario?.issues || [])];
            const unique = new Map(issues.map(issue => [issue.code + '\n' + issue.message, issue]));
            if (unique.size) {
                const list = node(doc, 'ul', null, 'sens-issues');
                unique.forEach(issue => list.appendChild(node(doc, 'li', issue.message)));
                container.appendChild(list);
            }
            technical(snapshot);
            if (window.ResizeObserver) {
                observer = new window.ResizeObserver(scheduleResize);
                observer.observe(container);
            }
            initializeChart();
            scheduleResize();
        }

        function resize() {
            if (destroyed || !active) return;
            initializeChart();
            if (!chart || !chartPlan) return;
            try {
                const narrow = chartPlan.element.clientWidth < 420;
                chart.setOption({ yAxis: { axisLabel: { width: narrow ? 90 : 164, fontSize: narrow ? 10 : 11 } } });
                chart.resize();
            } catch (_) { chartFallback(); }
        }

        function scheduleResize() {
            if (destroyed || !active || pendingFrame !== null) return;
            pendingFrame = window.requestAnimationFrame(() => { pendingFrame = null; resize(); });
        }

        function setActive(value) {
            if (destroyed) return;
            active = !!value;
            if (!active) {
                if (pendingFrame !== null) { window.cancelAnimationFrame(pendingFrame); pendingFrame = null; }
                disposeChart();
                numbers.closeAll(doc);
            } else scheduleResize();
        }

        function destroy() {
            if (destroyed) return;
            clear();
            cleanups.forEach(cleanup => cleanup());
            destroyed = true;
        }

        listen(window, 'resize', scheduleResize, true);
        listen(doc, 'dashboard:tabchange', event => setActive(event.detail?.panel === 'sensitivity'), true);
        return Object.freeze({ render, clear, setActive, resize, destroy });
    }

    window.DashboardSensitivityView = Object.freeze({ mount });
})(window);
