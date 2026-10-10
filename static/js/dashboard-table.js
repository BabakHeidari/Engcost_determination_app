(function (window) {
    'use strict';

    const IDENTITY_FIELDS = ['factory_id', 'category', 'subcategory', 'product'];
    const STATE_LABELS = Object.freeze({
        OK: 'محاسبه‌شده', MISSING_INPUT: 'ورودی لازم موجود نیست',
        INVALID_INPUT: 'ورودی نامعتبر', AMBIGUOUS_INPUT: 'ورودی مبهم',
        NOT_APPLICABLE: 'قابل اعمال نیست', CALCULATION_ERROR: 'خطای محاسبه'
    });
    const ISSUE_LABELS = Object.freeze({
        INVALID_PERCENTAGE: 'درصد ورودی خارج از بازه مجاز است.',
        INVALID_FX_RATE: 'نرخ ارز معتبر و مثبت لازم است.',
        INVALID_CATEGORY_SHARE: 'سهم دسته معتبر و مثبت لازم است.',
        MISSING_PRODUCT_PREDICTION: 'برنامه تولید این پیکربندی موجود نیست.',
        INVALID_PREDICTION_DENOMINATOR: 'مجموع برنامه تولید دسته باید مثبت باشد.',
        PREDICTION_DIVERGENCE: 'برنامه تولید منابع با یکدیگر مطابقت ندارد.',
        PREDICTION_NOT_UNIQUE: 'برنامه تولید این پیکربندی یکتا نیست.',
        SOURCE_UNAVAILABLE: 'یکی از منابع لازم در دسترس نیست.',
        PERIOD_NOT_BOUND: 'دوره معتبر و فعال برای این کارخانه موجود نیست.',
        PERIOD_MISMATCH: 'بازه درخواست با دوره ثبت‌شده مطابقت ندارد.'
    });
    const AMOUNT_FIELDS = [
        ['prediction', 'برنامه تولید', 'product/period'],
        ['unit_cost', 'هزینه واحد', 'IRR/product'],
        ['projected_cost', 'هزینه دوره', 'IRR/period'],
        ['bom_total', 'جمع مواد و اقلام BOM', 'IRR/product']
    ];
    const identityKey = identity => JSON.stringify(IDENTITY_FIELDS.map(key => identity[key]));
    const lexical = (left, right) => left < right ? -1 : left > right ? 1 : 0;
    const fa = value => String(value).replace(/\d/g, digit => '۰۱۲۳۴۵۶۷۸۹'[digit]);
    const normalize = value => String(value).normalize('NFKC').toLocaleLowerCase('fa-IR').replace(/ي/g, 'ی').replace(/ك/g, 'ک');

    function node(doc, tag, content, className, id) {
        const result = doc.createElement(tag);
        if (content !== undefined && content !== null) result.textContent = content;
        if (className) result.className = className;
        if (id) result.id = id;
        return result;
    }

    function cell(doc, row, content, className) {
        const result = node(doc, 'td', undefined, className);
        if (content && content.nodeType) result.appendChild(content);
        else if (content !== undefined) result.textContent = content;
        row.appendChild(result);
        return result;
    }

    function issueText(problem) {
        return ISSUE_LABELS[problem.code] || problem.message;
    }

    function mount(report, container, callbacks) {
        const doc = container.ownerDocument;
        const numbers = window.DashboardNumbers;
        callbacks = callbacks || {};
        // This array is a presentation index. Neither sorting nor filtering
        // changes the accepted report, its calculation scope, or its CSV rows.
        const rows = report.detail_rows.map((item, index) => ({
            item, index, key: identityKey(item.identity),
            search: normalize(IDENTITY_FIELDS.map(key => item.identity[key]).join(' ') + ' ' +
                item.issues.map(problem => issueText(problem)).join(' '))
        }));
        const listeners = [];
        let page = 0;
        let pageSize = 10;
        let focusKey = null;
        let destroyed = false;

        function listen(element, type, handler) {
            element.addEventListener(type, handler);
            listeners.push(() => element.removeEventListener(type, handler));
        }

        container.appendChild(node(doc, 'p', 'فیلتر نمایشی جدول؛ جست‌وجو، مرتب‌سازی و صفحه‌بندی دامنه محاسبه، پوشش و CSV را تغییر نمی‌دهند.', 'report-table-scope-note'));
        const controls = node(doc, 'div', undefined, 'report-table-controls');
        function control(label, id, options) {
            const wrapper = node(doc, 'div', undefined, 'report-table-control');
            const fieldLabel = node(doc, 'label', label);
            fieldLabel.htmlFor = id;
            const field = node(doc, options ? 'select' : 'input', undefined, 'form-control', id);
            if (options) options.forEach(([value, text]) => {
                const option = node(doc, 'option', text);
                option.value = value;
                field.appendChild(option);
            });
            else {
                field.type = 'search';
                field.placeholder = 'نام محصول، دسته یا زیردسته';
                field.autocomplete = 'off';
            }
            field.setAttribute('aria-controls', 'detailTable');
            wrapper.appendChild(fieldLabel);
            wrapper.appendChild(field);
            controls.appendChild(wrapper);
            return field;
        }
        const search = control('جست‌وجوی جدول', 'tableSearch');
        const stateFilter = control('وضعیت ردیف', 'tableStateFilter', [
            ['all', 'همه وضعیت‌ها'], ['OK', 'محاسبه‌شده'], ['excluded', 'کنارگذاشته‌شده']
        ]);
        const sort = control('مرتب‌سازی', 'tableSort', [
            ['product-asc', 'نام محصول'], ['unit_cost-desc', 'هزینه واحد: بیشترین'],
            ['unit_cost-asc', 'هزینه واحد: کمترین'], ['prediction-desc', 'تولید: بیشترین'],
            ['prediction-asc', 'تولید: کمترین'], ['projected_cost-desc', 'هزینه دوره: بیشترین'],
            ['projected_cost-asc', 'هزینه دوره: کمترین']
        ]);
        const size = control('تعداد در صفحه', 'tablePageSize', [
            ['10', '۱۰ ردیف'], ['25', '۲۵ ردیف'], ['50', '۵۰ ردیف']
        ]);
        container.appendChild(controls);

        const focusNote = node(doc, 'div', undefined, 'report-table-focus-note');
        focusNote.hidden = true;
        const focusMessage = node(doc, 'p', undefined, undefined, 'tableFocusStatus');
        focusMessage.setAttribute('role', 'status');
        focusMessage.setAttribute('aria-live', 'polite');
        const reset = node(doc, 'button', 'پاک کردن تمرکز نمودار', 'btn btn-outline-secondary', 'tableResetFocus');
        reset.type = 'button';
        reset.hidden = true;
        reset.setAttribute('aria-controls', 'detailTable');
        focusNote.appendChild(focusMessage);
        focusNote.appendChild(reset);
        container.appendChild(focusNote);

        const scrollHint = node(doc, 'p', 'برای دیدن هزینه‌ها و جزئیات، جدول را به چپ و راست پیمایش کنید.', 'report-table-mobile-hint', 'tableScrollHint');
        container.appendChild(scrollHint);
        const scroll = node(doc, 'div', undefined, 'report-table-scroll table-responsive');
        scroll.tabIndex = 0;
        scroll.setAttribute('role', 'region');
        scroll.setAttribute('aria-label', 'جدول ریز پیکربندی‌ها؛ در صفحه کوچک برای دیدن ستون‌ها پیمایش افقی کنید.');
        scroll.setAttribute('aria-describedby', 'tableScrollHint');
        const table = node(doc, 'table', undefined, 'table report-table configuration-table', 'detailTable');
        table.appendChild(node(doc, 'caption', 'پیکربندی‌های گزارش پذیرفته‌شده، شامل موارد کنارگذاشته‌شده؛ فیلترها فقط نمای جدول را تغییر می‌دهند.'));
        const head = node(doc, 'thead');
        const headings = node(doc, 'tr');
        ['محصول و دسته', 'وضعیت', 'برنامه تولید', 'هزینه واحد', 'هزینه دوره', 'جزئیات'].forEach(label => {
            const heading = node(doc, 'th', label);
            heading.scope = 'col';
            headings.appendChild(heading);
        });
        head.appendChild(headings);
        const body = node(doc, 'tbody');
        table.appendChild(head);
        table.appendChild(body);
        scroll.appendChild(table);
        container.appendChild(scroll);

        const pagination = node(doc, 'div', undefined, 'report-table-pagination');
        const previous = node(doc, 'button', 'صفحه قبل', 'btn btn-outline-secondary', 'tablePrevious');
        const next = node(doc, 'button', 'صفحه بعد', 'btn btn-outline-secondary', 'tableNext');
        const pageInfo = node(doc, 'span', undefined, 'report-table-page-info', 'tablePageInfo');
        previous.type = next.type = 'button';
        previous.setAttribute('aria-controls', 'detailTable');
        next.setAttribute('aria-controls', 'detailTable');
        pageInfo.setAttribute('role', 'status');
        pageInfo.setAttribute('aria-live', 'polite');
        pagination.appendChild(previous);
        pagination.appendChild(pageInfo);
        pagination.appendChild(next);
        container.appendChild(pagination);

        function visibleRows() {
            const query = normalize(search.value.trim());
            const result = rows.filter(entry => (!query || entry.search.includes(query)) &&
                (stateFilter.value === 'all' || (stateFilter.value === 'OK' ? entry.item.state === 'OK' : entry.item.state !== 'OK')));
            const split = sort.value.lastIndexOf('-');
            const field = sort.value.slice(0, split);
            const descending = sort.value.slice(split + 1) === 'desc';
            result.sort((left, right) => {
                let comparison;
                if (field === 'product') {
                    comparison = left.item.identity.product.localeCompare(right.item.identity.product, 'fa');
                } else {
                    const leftValue = left.item[field];
                    const rightValue = right.item[field];
                    // Unavailable values stay at the end in either direction.
                    if (leftValue === null && rightValue !== null) return 1;
                    if (leftValue !== null && rightValue === null) return -1;
                    comparison = leftValue === null ? 0 : numbers.compare(leftValue, rightValue);
                }
                return (descending ? -comparison : comparison) || lexical(left.key, right.key);
            });
            return result;
        }

        function detailsFor(entry) {
            const item = entry.item;
            const details = node(doc, 'details', undefined, 'row-details', 'dashboardRowDetails-' + entry.index);
            details.appendChild(node(doc, 'summary', 'جزئیات ردیف'));
            details.appendChild(node(doc, 'p', 'هویت کامل و مقدارهای اصلی همین پیکربندی', 'report-secondary'));
            const identity = node(doc, 'dl', undefined, 'row-detail-grid');
            ['شناسه کارخانه', 'دسته', 'زیردسته', 'محصول'].forEach((label, index) => {
                identity.appendChild(node(doc, 'dt', label));
                const value = node(doc, 'dd');
                const isolated = node(doc, 'bdi', item.identity[IDENTITY_FIELDS[index]]);
                isolated.dir = 'auto';
                value.appendChild(isolated);
                identity.appendChild(value);
            });
            details.appendChild(identity);
            const amounts = node(doc, 'dl', undefined, 'row-detail-grid row-detail-amounts');
            AMOUNT_FIELDS.forEach(([field, label, unit]) => {
                amounts.appendChild(node(doc, 'dt', label));
                const value = node(doc, 'dd');
                value.appendChild(numbers.value(doc, item[field], {unit, compact: field !== 'prediction', state: item.state}));
                if (item[field] !== null) {
                    const original = node(doc, 'code', item[field], 'row-original-value');
                    original.dir = 'ltr';
                    original.dataset.raw = item[field];
                    original.setAttribute('aria-label', 'رشته اصلی مقدار دقیق');
                    value.appendChild(original);
                }
                amounts.appendChild(value);
            });
            details.appendChild(amounts);
            if (item.issues.length) {
                const issues = node(doc, 'ul', undefined, 'row-detail-issues');
                item.issues.forEach(problem => {
                    const issue = node(doc, 'li', problem.message + ' ');
                    const code = node(doc, 'code', problem.code);
                    code.dir = 'ltr';
                    issue.appendChild(code);
                    issues.appendChild(issue);
                });
                details.appendChild(issues);
            }
            return details;
        }

        function render() {
            if (destroyed) return;
            if (numbers.closeAll) numbers.closeAll();
            const visible = visibleRows();
            const pages = Math.max(1, Math.ceil(visible.length / pageSize));
            page = Math.min(page, pages - 1);
            body.replaceChildren();
            visible.slice(page * pageSize, (page + 1) * pageSize).forEach(entry => {
                const item = entry.item;
                const row = node(doc, 'tr', undefined, item.state === 'OK' ? '' : 'report-excluded');
                row.dataset.state = item.state;
                row.dataset.identity = entry.key;
                if (entry.key === focusKey) row.classList.add('report-focus-row');
                const product = node(doc, 'div', undefined, 'product-cell');
                product.appendChild(node(doc, 'strong', item.identity.product, 'product-name'));
                product.appendChild(node(doc, 'span', item.identity.category + ' / ' + item.identity.subcategory, 'product-context'));
                cell(doc, row, product, 'report-product-cell');
                const status = node(doc, 'div');
                status.appendChild(node(doc, 'span', STATE_LABELS[item.state], 'report-status-badge ' + (item.state === 'OK' ? 'is-ok' : 'is-excluded')));
                if (item.state !== 'OK') status.appendChild(node(doc, 'p', item.issues.map(issueText).join('؛ ') || STATE_LABELS[item.state], 'report-exclusion-reason'));
                cell(doc, row, status);
                AMOUNT_FIELDS.slice(0, 3).forEach(([field, , unit]) => {
                    const amountCell = cell(doc, row, numbers.value(doc, item[field], {unit, compact: field !== 'prediction', state: item.state}), 'report-amount-cell');
                    amountCell.dataset.valueKey = field;
                });
                cell(doc, row, detailsFor(entry), 'report-row-details-cell');
                body.appendChild(row);
            });
            if (!visible.length) {
                const empty = node(doc, 'tr');
                const emptyCell = cell(doc, empty, rows.length ? 'ردیفی با این فیلتر نمایشی پیدا نشد؛ جست‌وجو یا وضعیت را تغییر دهید.' : 'پیکربندی منطبقی برای نمایش موجود نیست.');
                emptyCell.colSpan = 6;
                body.appendChild(empty);
            }
            previous.disabled = page === 0;
            next.disabled = page >= pages - 1;
            const first = visible.length ? page * pageSize + 1 : 0;
            const last = Math.min((page + 1) * pageSize, visible.length);
            pageInfo.textContent = fa(first) + ' تا ' + fa(last) + ' از ' + fa(visible.length) + ' ردیف نمایشی · کل گزارش ' + fa(rows.length) + ' ردیف';
        }

        function clearFocus() {
            const hadFocus = focusKey !== null;
            focusKey = null;
            focusNote.hidden = true;
            reset.hidden = true;
            focusMessage.textContent = '';
            // Table-only interactions dismiss the matching chart highlight.
            // Clear local state before notifying, so coordinated resets cannot
            // send a second notification back through the same controller.
            if (hadFocus && typeof callbacks.onFocusCleared === 'function') callbacks.onFocusCleared();
        }

        function resetFocus() {
            if (destroyed) return;
            clearFocus();
            search.value = '';
            stateFilter.value = 'all';
            page = 0;
            render();
            focusNote.hidden = false;
            focusMessage.textContent = 'تمرکز نمودار پاک شد؛ همه پیکربندی‌های گزارش در جدول در دسترس‌اند.';
        }

        function focus(identity) {
            if (destroyed) return false;
            const key = identityKey(identity);
            if (!rows.some(entry => entry.key === key)) return false;
            search.value = '';
            stateFilter.value = 'all';
            focusKey = key;
            focusNote.hidden = false;
            reset.hidden = false;
            const sorted = visibleRows();
            page = Math.floor(sorted.findIndex(entry => entry.key === key) / pageSize);
            render();
            const row = Array.from(body.rows).find(element => element.dataset.identity === key);
            const details = row.querySelector('details');
            details.open = true;
            focusMessage.textContent = 'تمرکز نمایشی نمودار: ' + identity.product + '، ' + identity.category + ' / ' + identity.subcategory + '؛ دامنه محاسبه و CSV تغییر نکرده‌اند.';
            const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            row.scrollIntoView({block: 'center', behavior: reduced ? 'auto' : 'smooth'});
            const summary = details.querySelector('summary');
            // A mobile table may scroll horizontally. Reveal the actual focused
            // control within that container as well as bringing its row into view.
            summary.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: reduced ? 'auto' : 'smooth'});
            summary.focus({preventScroll: true});
            return true;
        }

        function filterChanged() {
            clearFocus();
            page = 0;
            render();
        }
        listen(search, 'input', filterChanged);
        listen(stateFilter, 'change', filterChanged);
        listen(sort, 'change', filterChanged);
        listen(size, 'change', () => {
            pageSize = {'10': 10, '25': 25, '50': 50}[size.value];
            filterChanged();
        });
        listen(previous, 'click', () => { page -= 1; clearFocus(); render(); });
        listen(next, 'click', () => { page += 1; clearFocus(); render(); });
        listen(reset, 'click', () => { resetFocus(); search.focus(); });
        render();
        return Object.freeze({
            focus, resetFocus,
            destroy: () => {
                destroyed = true;
                listeners.forEach(remove => remove());
                if (numbers.closeAll) numbers.closeAll();
            }
        });
    }

    window.DashboardTable = Object.freeze({mount});
})(window);
