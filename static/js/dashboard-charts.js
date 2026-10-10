(function (window) {
    'use strict';

    // All values displayed here come from the accepted Decimal strings. Only
    // finite chart coordinates pass through Number; ECharts never supplies a
    // financial total, share or exact tooltip value.
    const DRIVERS = Object.freeze({
        BOM: { label: 'مواد و اقلام BOM', color: '#147f86' },
        AdministrativeandResearch: { label: 'اداری و پژوهش', color: '#8c72b0' },
        Payroll: { label: 'حقوق و دستمزد', color: '#496bb1' },
        Overhead: { label: 'سربار', color: '#bb853b' },
        FinancialCosts: { label: 'هزینه‌های مالی', color: '#bd647d' },
        Depriciation: { label: 'استهلاک', color: '#468875' },
        NonOperationalCostsandIncomes: { label: 'هزینه‌ها و درآمدهای غیرعملیاتی', color: '#748296' }
    });
    const FIELDS = ['factory_id', 'category', 'subcategory', 'product'];
    const identityKey = identity => JSON.stringify(FIELDS.map(field => identity[field]));
    const identityText = identity => 'کارخانه: ' + identity.factory_id + '\nدسته: ' + identity.category +
        '\nزیردسته: ' + identity.subcategory + '\nمحصول: ' + identity.product;

    function node(doc, tag, content, className, id) {
        const result = doc.createElement(tag);
        if (content !== undefined && content !== null) result.textContent = content;
        if (className) result.className = className;
        if (id) result.id = id;
        return result;
    }

    function coordinateRows(rows, field) {
        if (rows.some(row => row[field] === null)) return null;
        const coordinates = rows.map(row => Number(row[field]));
        return coordinates.every(Number.isFinite) ? coordinates : null;
    }

    // ECharts may hand an axis tick back in exponent notation. Expanding that
    // coordinate string keeps the decimal formatter usable without converting
    // any accepted report string or changing the exact data.
    function tickDecimal(coordinate) {
        const value = String(coordinate);
        const exponent = value.match(/^([+-]?)(\d+)(?:\.(\d+))?e([+-]?\d+)$/i);
        if (!exponent) return value;
        const digits = exponent[2] + (exponent[3] || '');
        const point = exponent[2].length + Number(exponent[4]);
        if (point <= 0) return exponent[1] + '0.' + '0'.repeat(-point) + digits;
        if (point >= digits.length) return exponent[1] + digits + '0'.repeat(point - digits.length);
        return exponent[1] + digits.slice(0, point) + '.' + digits.slice(point);
    }

    function label(identity) {
        return identity.product + ' | ' + identity.category + ' / ' + identity.subcategory;
    }

    function table(doc, parent, id, caption, headings) {
        const wrapper = node(doc, 'div', null, 'table-responsive report-chart-table-wrap');
        const result = node(doc, 'table', null, 'table report-table report-chart-table', id);
        result.appendChild(node(doc, 'caption', caption));
        const head = node(doc, 'thead');
        const row = node(doc, 'tr');
        headings.forEach(heading => {
            const cell = node(doc, 'th', heading);
            cell.scope = 'col';
            row.appendChild(cell);
        });
        head.appendChild(row);
        const body = node(doc, 'tbody');
        result.appendChild(head);
        result.appendChild(body);
        wrapper.appendChild(result);
        parent.appendChild(wrapper);
        return body;
    }

    function cell(doc, row, content, className) {
        const result = node(doc, 'td', null, className);
        if (content && content.nodeType) result.appendChild(content);
        else result.textContent = content === null || content === undefined ? 'در دسترس نیست' : content;
        row.appendChild(result);
        return result;
    }

    function mount(report, container, callbacks) {
        const doc = container.ownerDocument;
        const numbers = window.DashboardNumbers;
        const settings = callbacks || {};
        const products = report.breakdowns.products.slice().sort((left, right) => {
            const compared = numbers.compare(right.unit_cost, left.unit_cost);
            return compared || identityKey(left.identity).localeCompare(identityKey(right.identity));
        });
        const drivers = report.breakdowns.drivers;
        const total = report.state === 'PARTIAL' ? report.kpis.partial_total : report.kpis.projected_total;
        const donutAllowed = drivers.length > 0 && total !== null && numbers.compare(total, '0') > 0 &&
            drivers.every(item => item.value !== null && numbers.compare(item.value, '0') >= 0);
        const instances = [];
        const cleanups = [];
        let disposed = false;
        let pendingResize = null;
        let productChart = null;
        let driverChart = null;
        let selectedIdentity = null;
        let driverView = 'bar';
        let observer = null;
        const font = window.getComputedStyle(doc.documentElement).getPropertyValue('--app-font-family').trim() || 'IRANSansX, Tahoma, sans-serif';
        const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const grid = node(doc, 'div', null, 'report-chart-grid charts');
        container.appendChild(grid);

        function listen(element, event, handler) {
            element.addEventListener(event, handler);
            cleanups.push(() => element.removeEventListener(event, handler));
        }

        function panel(title, subtitle, id) {
            const card = node(doc, 'section', null, 'report-chart-card chart-box');
            const heading = node(doc, 'div', null, 'report-chart-heading');
            heading.appendChild(node(doc, 'h2', title));
            card.appendChild(heading);
            card.appendChild(node(doc, 'p', subtitle, 'report-chart-subtitle report-secondary'));
            const chart = node(doc, 'div', null, 'report-chart chart', id);
            chart.setAttribute('role', 'img');
            chart.setAttribute('aria-label', title + '؛ جدول همراه شامل مقادیر و کنش‌های قابل استفاده با صفحه‌کلید است.');
            card.appendChild(chart);
            const note = node(doc, 'p', 'برای مقدار کامل روی عدد جدول بزنید. نمودار فقط مقایسه دیداری است.', 'report-chart-note');
            card.appendChild(note);
            grid.appendChild(card);
            return { card, heading, chart, note };
        }

        const productPanel = panel('مقایسه هزینه واحد محصول', 'مرتب از بیشترین هزینه؛ انتخاب یک محصول، فقط جدول ریز پیکربندی‌ها را متمرکز می‌کند.', 'productCostChart');
        const driverPanel = panel('ترکیب هزینه پیش‌بینی‌شده', 'هفت عامل در جمعیت منتخبِ محاسبه‌شده؛ مقادیر و سهم‌ها مطابق گزارش هستند.', 'driverCompositionChart');
        const productFocus = node(doc, 'div', null, 'report-chart-focus');
        productFocus.hidden = true;
        const focusLabel = node(doc, 'span');
        focusLabel.setAttribute('role', 'status');
        focusLabel.setAttribute('aria-live', 'polite');
        const focusReset = node(doc, 'button', 'پاک کردن تمرکز نمودار', 'btn btn-sm btn-outline-secondary', 'chartFocusReset');
        focusReset.type = 'button';
        productFocus.appendChild(focusLabel);
        productFocus.appendChild(focusReset);
        productPanel.card.insertBefore(productFocus, productPanel.chart);
        const productButtons = new Map();

        function focusProduct(identity) {
            if (disposed) return;
            selectedIdentity = identityKey(identity);
            productFocus.hidden = false;
            focusLabel.textContent = 'تمرکز محلی جدول: ' + label(identity);
            productButtons.forEach((button, key) => {
                button.setAttribute('aria-pressed', String(key === selectedIdentity));
            });
            if (productChart) {
                try {
                    productChart.dispatchAction && productChart.dispatchAction({ type: 'downplay', seriesIndex: 0 });
                    productChart.dispatchAction && productChart.dispatchAction({ type: 'highlight', seriesIndex: 0,
                        dataIndex: products.findIndex(row => identityKey(row.identity) === selectedIdentity) });
                } catch (error) { /* The table interaction remains available. */ }
            }
            if (typeof settings.onProductFocus === 'function') settings.onProductFocus(identity);
        }

        function clearFocus() {
            if (disposed) return;
            selectedIdentity = null;
            productFocus.hidden = true;
            productButtons.forEach(button => button.setAttribute('aria-pressed', 'false'));
            if (productChart && productChart.dispatchAction) {
                try { productChart.dispatchAction({ type: 'downplay', seriesIndex: 0 }); }
                catch (error) { /* Optional chart emphasis. */ }
            }
        }

        listen(focusReset, 'click', () => {
            clearFocus();
            if (typeof settings.onResetFocus === 'function') settings.onResetFocus();
            const summary = productAlternative.querySelector('summary');
            if (summary) summary.focus();
        });

        const productAlternative = node(doc, 'details', null, 'report-chart-alternative');
        productAlternative.appendChild(node(doc, 'summary', 'فهرست محصولات و انتخاب با صفحه‌کلید'));
        productPanel.card.appendChild(productAlternative);
        const productBody = table(doc, productAlternative, 'productChartTable', 'انتخاب یک ردیف تنها تمرکز محلی جدول را تغییر می‌دهد؛ دامنه، KPI و CSV ثابت می‌مانند.', ['محصول و مسیر', 'هزینه واحد', 'تمرکز جدول']);
        products.forEach(item => {
            const row = node(doc, 'tr');
            const context = node(doc, 'div', null, 'report-product-cell');
            context.appendChild(node(doc, 'strong', item.identity.product));
            context.appendChild(node(doc, 'span', item.identity.category + ' / ' + item.identity.subcategory, 'report-product-context'));
            cell(doc, row, context);
            cell(doc, row, numbers.value(doc, item.unit_cost, { unit: 'IRR/product', compact: true }));
            const button = node(doc, 'button', 'نمایش ردیف', 'btn btn-sm btn-outline-secondary chart-product-focus');
            button.type = 'button';
            button.setAttribute('aria-label', 'نمایش پیکربندی ' + label(item.identity) + ' در جدول');
            button.setAttribute('aria-pressed', 'false');
            button.dataset.identity = identityKey(item.identity);
            productButtons.set(identityKey(item.identity), button);
            listen(button, 'click', () => focusProduct(item.identity));
            cell(doc, row, button);
            productBody.appendChild(row);
        });
        if (!products.length) {
            const row = node(doc, 'tr');
            cell(doc, row, 'محصول محاسبه‌شده‌ای برای مقایسه موجود نیست.').colSpan = 3;
            productBody.appendChild(row);
        }

        const viewControls = node(doc, 'div', null, 'report-chart-actions');
        viewControls.setAttribute('role', 'group');
        viewControls.setAttribute('aria-label', 'نمایش محلی ترکیب عوامل');
        driverPanel.heading.appendChild(viewControls);
        const barButton = node(doc, 'button', 'میله‌ای', 'btn btn-sm chart-view-toggle', 'driverBarView');
        const donutButton = node(doc, 'button', 'حلقه‌ای', 'btn btn-sm chart-view-toggle', 'driverDonutView');
        [barButton, donutButton].forEach(button => { button.type = 'button'; viewControls.appendChild(button); });
        barButton.setAttribute('aria-pressed', 'true');
        donutButton.setAttribute('aria-pressed', 'false');
        donutButton.disabled = !donutAllowed;
        if (!donutAllowed) {
            donutButton.title = 'نمایش حلقه‌ای به مجموع مثبت و عوامل نامنفی نیاز دارد.';
            driverPanel.note.textContent = 'مقادیر علامت‌دار یا مجموع صفر با نمودار میله‌ای مقایسه می‌شوند؛ همه عوامل در جدول در دسترس‌اند.';
        }

        const driverBody = table(doc, driverPanel.card, 'driverTable', 'مقدار و سهم هر هفت عامل؛ عوامل کوچک حتی کنار BOM غالب قابل بررسی‌اند.', ['عامل هزینه', 'مبلغ', 'سهم گزارش']);
        drivers.forEach(item => {
            const row = node(doc, 'tr');
            row.dataset.driver = item.id;
            const driverLabel = node(doc, 'span', null, 'report-driver-label');
            const dot = node(doc, 'span', null, 'driver-dot');
            dot.style.backgroundColor = DRIVERS[item.id].color;
            dot.setAttribute('aria-hidden', 'true');
            driverLabel.appendChild(dot);
            driverLabel.appendChild(node(doc, 'span', DRIVERS[item.id].label));
            cell(doc, row, driverLabel);
            cell(doc, row, numbers.value(doc, item.value, { unit: 'IRR/period', compact: true }));
            cell(doc, row, numbers.value(doc, item.share, { unit: 'percentage', compact: false }));
            driverBody.appendChild(row);
        });
        if (!drivers.length) {
            const row = node(doc, 'tr');
            cell(doc, row, 'عامل قابل محاسبه‌ای برای این گزارش موجود نیست.').colSpan = 3;
            driverBody.appendChild(row);
        }

        function commonOptions() {
            return {
                animation: !reducedMotion, animationDuration: 380, animationDurationUpdate: 220,
                textStyle: { fontFamily: font, color: '#22364c' },
                tooltip: {
                    trigger: 'item', renderMode: 'richText', confine: true,
                    backgroundColor: '#fff', borderColor: '#dce6ec', borderWidth: 1,
                    padding: [12, 14], textStyle: { fontFamily: font, fontSize: 12, color: '#22364c', lineHeight: 23 }
                }
            };
        }

        function axisOptions(rows, labels, field, unit, chartElement) {
            const coordinates = coordinateRows(rows, field);
            const width = chartElement.clientWidth;
            return {
                grid: { left: 12, right: 22, top: 15, bottom: 38, containLabel: true },
                xAxis: {
                    type: 'value', name: unit === 'IRR/product' ? 'ریال / محصول' : 'ریال / دوره',
                    nameLocation: 'middle', nameGap: 30, nameTextStyle: { color: '#637386', fontSize: 10 },
                    splitNumber: 3, axisLine: { show: true, onZero: true, lineStyle: { color: '#7e93a7' } },
                    axisTick: { show: false }, splitLine: { lineStyle: { color: '#eaf0f4', type: 'dashed' } },
                    axisLabel: { color: '#65788b', fontSize: 10, hideOverlap: true,
                        formatter: value => numbers.format(tickDecimal(value), { compact: true, unit: 'IRR', showUnit: false }) }
                },
                yAxis: {
                    type: 'category', inverse: true, data: labels,
                    axisLine: { show: false }, axisTick: { show: false },
                    axisLabel: { color: '#324b63', fontSize: 11, lineHeight: 20, margin: 12,
                        width: width && width < 340 ? 84 : 132, overflow: 'truncate' }
                },
                series: [{ type: 'bar', data: coordinates, barMaxWidth: 24,
                    itemStyle: { borderRadius: [0, 5, 5, 0] },
                    emphasis: { focus: 'self', itemStyle: { opacity: 1, shadowBlur: 9, shadowColor: 'rgba(20,127,134,.2)' } } }]
            };
        }

        function fallback(panelObject, empty) {
            panelObject.chart.hidden = true;
            panelObject.note.textContent = empty ? 'ردیف محاسبه‌شده‌ای برای نمودار موجود نیست.' :
                'نمودار در دسترس نیست؛ جدول همراه تمام مقادیر دقیق و کنش‌های انتخاب را نشان می‌دهد.';
        }

        function initialize(panelObject, rows, field, options) {
            if (!window.echarts || !rows.length || !coordinateRows(rows, field)) {
                fallback(panelObject, !rows.length);
                return null;
            }
            let chart = null;
            try {
                chart = window.echarts.init(panelObject.chart);
                chart.setOption(options, true);
                instances.push(chart);
                return chart;
            } catch (error) {
                if (chart) { try { chart.dispose(); } catch (disposeError) { /* Optional visual. */ } }
                fallback(panelObject, false);
                return null;
            }
        }

        const productOptions = Object.assign(commonOptions(), axisOptions(products, products.map(row => label(row.identity)), 'unit_cost', 'IRR/product', productPanel.chart));
        productOptions.tooltip.formatter = params => {
            const item = products[params.dataIndex];
            return item ? identityText(item.identity) + '\nهزینه واحد: ' + numbers.exact(item.unit_cost, item.unit) + '\nبرای تمرکز جدول، محصول را انتخاب کنید.' : '';
        };
        productOptions.yAxis.axisLabel.formatter = value => {
            const divider = value.indexOf(' | ');
            return divider === -1 ? value : value.slice(0, divider) + '\n' + value.slice(divider + 3);
        };
        productOptions.series[0].itemStyle.color = '#16838c';
        if (products.length > 8) {
            productOptions.grid.right = 34;
            productOptions.dataZoom = [
                { type: 'slider', yAxisIndex: 0, filterMode: 'none', width: 13, right: 3, top: 14,
                    bottom: 43, startValue: 0, endValue: 7, showDetail: false, borderColor: '#dfe8ee',
                    fillerColor: 'rgba(20,127,134,.13)', handleStyle: { color: '#698b9a' } },
                { type: 'inside', yAxisIndex: 0, filterMode: 'none', startValue: 0, endValue: 7,
                    zoomOnMouseWheel: false, moveOnMouseWheel: true, moveOnMouseMove: false }
            ];
            productPanel.note.textContent = 'برای دیدن محصولات بیشتر، پیمایش کنار نمودار را جابه‌جا کنید؛ فهرست کامل و مقادیر دقیق در پایین است.';
        }
        productChart = initialize(productPanel, products, 'unit_cost', productOptions);
        if (productChart && productChart.on) {
            const handler = params => { const item = products[params.dataIndex]; if (item) focusProduct(item.identity); };
            productChart.on('click', handler);
            cleanups.push(() => { if (productChart && productChart.off) productChart.off('click', handler); });
        }
        if (!productChart) productAlternative.open = true;

        function driverOptions(view) {
            const result = commonOptions();
            result.tooltip.formatter = params => {
                const item = drivers[params.dataIndex];
                if (!item) return '';
                return DRIVERS[item.id].label + '\nمبلغ: ' + numbers.exact(item.value, item.unit) +
                    '\nسهم گزارش: ' + numbers.exact(item.share, 'percentage');
            };
            if (view === 'donut') {
                result.title = {
                    text: report.state === 'PARTIAL' ? 'مجموع جزئی' : 'هزینه منتخب',
                    subtext: numbers.format(total, { unit: 'IRR', compact: true }),
                    left: 'center', top: '40%', textStyle: { fontFamily: font, color: '#65788b', fontSize: 12, fontWeight: 400 },
                    subtextStyle: { fontFamily: font, color: '#22364c', fontWeight: 700, fontSize: 15 }
                };
                result.series = [{
                    type: 'pie', radius: ['54%', '79%'], center: ['50%', '49%'],
                    minAngle: 0, stillShowZeroSum: false, avoidLabelOverlap: true,
                    label: { show: false }, labelLine: { show: false },
                    itemStyle: { borderColor: '#fff', borderWidth: 2 },
                    emphasis: { scale: true, scaleSize: 5, label: { show: false } },
                    data: drivers.map(item => ({ name: DRIVERS[item.id].label, value: Number(item.value),
                        itemStyle: { color: DRIVERS[item.id].color } }))
                }];
            } else {
                Object.assign(result, axisOptions(drivers, drivers.map(item => DRIVERS[item.id].label), 'value', 'IRR/period', driverPanel.chart));
                result.series[0].itemStyle.color = params => DRIVERS[drivers[params.dataIndex].id].color;
                result.series[0].markLine = { silent: true, symbol: 'none', label: { show: false },
                    lineStyle: { color: '#63788c', type: 'solid', width: 1 }, data: [{ xAxis: 0 }] };
            }
            return result;
        }
        driverChart = initialize(driverPanel, drivers, 'value', driverOptions('bar'));
        if (!driverChart) { barButton.disabled = true; donutButton.disabled = true; }
        function changeView(view) {
            if (!driverChart || disposed || view === driverView || (view === 'donut' && !donutAllowed)) return;
            try {
                driverChart.setOption(driverOptions(view), true);
                driverView = view;
                barButton.setAttribute('aria-pressed', String(view === 'bar'));
                donutButton.setAttribute('aria-pressed', String(view === 'donut'));
            } catch (error) {
                fallback(driverPanel, false);
                barButton.disabled = true;
                donutButton.disabled = true;
            }
        }
        listen(barButton, 'click', () => changeView('bar'));
        listen(donutButton, 'click', () => changeView('donut'));

        function resize() {
            if (disposed) return;
            // Resize also adjusts label space after sidebar/layout changes.
            // Merge only presentation options so local zoom and focus survive.
            [[productChart, productPanel.chart, true], [driverChart, driverPanel.chart, driverView === 'bar']].forEach(([chart, element, hasAxis]) => {
                if (!chart || !hasAxis || !chart.getOption) return;
                const narrow = element.clientWidth < 340;
                try { chart.setOption({ yAxis: { axisLabel: { width: narrow ? 84 : 132, fontSize: narrow ? 10 : 11 } } }); }
                catch (error) { /* The original readable table is unaffected. */ }
            });
            instances.forEach(chart => { try { chart.resize(); } catch (error) { /* Table remains usable. */ } });
        }
        function scheduleResize() {
            if (disposed || pendingResize !== null) return;
            pendingResize = window.requestAnimationFrame(() => { pendingResize = null; resize(); });
        }
        listen(window, 'resize', scheduleResize);
        if (window.ResizeObserver) {
            observer = new window.ResizeObserver(scheduleResize);
            observer.observe(container);
            observer.observe(productPanel.chart);
            observer.observe(driverPanel.chart);
        }
        listen(productAlternative, 'toggle', scheduleResize);

        function destroy() {
            if (disposed) return;
            disposed = true;
            if (pendingResize !== null) { window.cancelAnimationFrame(pendingResize); pendingResize = null; }
            if (observer) observer.disconnect();
            cleanups.forEach(cleanup => cleanup());
            instances.forEach(chart => { try { chart.dispose(); } catch (error) { /* Already disposed. */ } });
        }
        return Object.freeze({ destroy, resize, clearFocus });
    }

    window.DashboardCharts = Object.freeze({ mount });
})(window);
