/* Dashboard selection and transport only. Financial values remain API strings. */
(function (window, document) {
    'use strict';
    const bootstrap = document.getElementById('dashboardOptions');
    if (!bootstrap) return;
    const filterOptions = JSON.parse(bootstrap.textContent);
    const ALL = '__ALL__';
    const byId = id => document.getElementById(id);
    const factorySelect = byId('factorySelect');
    const categorySelect = byId('categorySelect');
    const subcategorySelect = byId('subcategorySelect');
    const productSelect = byId('productSelect');
    const periodSelect = byId('periodSelect');
    const startDate = byId('startDate');
    const endDate = byId('endDate');
    const analyzeBtn = byId('analyzeBtn');
    const exportBtn = byId('downloadCsvBtn');
    const report = window.DashboardReport;
    let requestSequence = 0, activeRequest = null, hierarchyLoading = false;
    let analysisSequence = 0, analysisRequest = null, analysisLoading = false;
    let acceptedSnapshot = null, acceptedScope = null;
    let periodMetadata = null;

    const statusMessages = {
        400: 'انتخاب‌ها یا بازه دوره معتبر نیست؛ ورودی‌ها را بررسی کنید.',
        401: 'نشست شما پایان یافته است. دوباره وارد سامانه شوید.',
        403: 'اجازه مشاهده تحلیل این کارخانه را ندارید.',
        404: 'کارخانه انتخاب‌شده در دسترس نیست.',
        422: 'گزارش کامل قابل محاسبه نیست؛ پوشش و دلایل حذف را بررسی کنید.',
        503: 'داده‌های سلسله‌مراتب فعلاً در دسترس نیست. دوباره تلاش کنید.',
        500: 'محاسبه انجام نشد. دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.'
    };
    function option(value, label) {
        const node = document.createElement('option');
        node.value = value;
        node.textContent = label;
        return node;
    }
    function setStatus(element, state, message) {
        delete element.dataset.httpStatus;
        element.dataset.state = state;
        element.textContent = message;
        element.className = 'dashboard-status ' + (state === 'OK' ? 'is-success' :
            state === 'LOADING' ? 'is-loading' : state === 'NOT_SELECTED' ? 'is-neutral' : 'is-warning');
        if (element.id === 'filterStatus') byId('retryHierarchyBtn').hidden =
            ['OK', 'NO_MATCH', 'UNCONFIGURED', 'NOT_SELECTED', 'LOADING'].includes(state) || !factorySelect.value;
    }
    function resetSelect(select, placeholder, disabled = true) {
        select.replaceChildren(option('', placeholder));
        select.disabled = disabled;
    }
    function fillSelect(select, options, placeholder, previous) {
        select.replaceChildren(option('', placeholder), option(ALL, 'همه'),
            ...options.map(item => option(item.id, select === productSelect ?
                item.label + ' | ' + item.category + ' / ' + item.subcategory : item.label)));
        select.disabled = false;
        if ([ALL, ...options.map(item => item.id)].includes(previous)) select.value = previous;
    }
    function resetChildren(from) {
        if (from <= 0) resetSelect(categorySelect, 'ابتدا کارخانه را انتخاب کنید');
        if (from <= 1) resetSelect(subcategorySelect, 'ابتدا دسته را انتخاب کنید');
        if (from <= 2) resetSelect(productSelect, 'ابتدا زیردسته را انتخاب کنید');
    }
    function currentPeriod() {
        if (!periodMetadata) return null;
        const id = periodSelect.value || periodMetadata.default_period_id;
        return periodMetadata.options.find(item => item.id === id) || null;
    }
    function dateInputs() {
        const binding = currentPeriod();
        const result = {valid: false, message: 'یک دوره ثبت‌شده معتبر انتخاب کنید.'};
        [startDate, endDate].forEach(input => input.setAttribute('aria-invalid', 'false'));
        if (!binding) return result;
        const texts = [startDate.value.trim(), endDate.value.trim()];
        if (texts.every(value => !value)) return {valid: true, binding};
        if (texts.some(value => !value)) {
            [startDate, endDate].forEach(input => input.setAttribute('aria-invalid', 'true'));
            return {...result, message: 'تاریخ شروع و پایان را با هم وارد کنید یا هر دو را خالی بگذارید.'};
        }
        const dates = [];
        for (const [index, text] of texts.entries()) {
            try {
                const value = window.JalaliDate.parseJalaliInput(text);
                if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error();
                dates.push(value);
            } catch (_) {
                [startDate, endDate][index].setAttribute('aria-invalid', 'true');
                return {...result, message: 'تاریخ جلالی معتبر را در قالب سال/ماه/روز وارد کنید.'};
            }
        }
        if (dates[0] !== binding.start || dates[1] !== binding.end) {
            [startDate, endDate].forEach(input => input.setAttribute('aria-invalid', 'true'));
            return {...result, message: 'بازه واردشده باید دقیقاً برابر شروع و پایان دوره ثبت‌شده باشد.'};
        }
        return {valid: true, binding, start: dates[0], end: dates[1]};
    }
    function selectionComplete() {
        return [factorySelect, categorySelect, subcategorySelect, productSelect]
            .every(select => !select.disabled && select.value !== '');
    }
    function updateControls() {
        analyzeBtn.disabled = hierarchyLoading || analysisLoading || !selectionComplete() || !dateInputs().valid;
        analyzeBtn.textContent = analysisLoading ? 'در حال تحلیل…' : 'تحلیل هزینه';
        exportBtn.disabled = !acceptedSnapshot || acceptedScope !== scopeKey();
        byId('analysisForm').setAttribute('aria-busy', String(analysisLoading || hierarchyLoading));
    }
    function showPeriodStatus() {
        const inputs = dateInputs();
        const binding = currentPeriod();
        let message = inputs.message;
        if (inputs.valid) message = 'دوره ثبت‌شده: ' + binding.id + '؛ ' + window.JalaliDate.formatDateOnly(binding.start) +
            ' تا ' + window.JalaliDate.formatDateOnly(binding.end) + ' — این بازه نشان‌دهنده سابقه تاریخی منابع نیست.';
        else if (!periodMetadata?.options.length && factorySelect.value)
            message = 'دوره معتبر نصب‌شده‌ای در دسترس نیست. ثبت یا اصلاح دوره باید توسط مسئول سامانه انجام شود.';
        setStatus(byId('periodStatus'), inputs.valid ? 'OK' : 'INVALID_INPUT', message);
        updateControls();
    }
    function fillPeriodDates() {
        const binding = currentPeriod();
        startDate.value = binding ? window.JalaliDate.formatDateOnly(binding.start) : '';
        endDate.value = binding ? window.JalaliDate.formatDateOnly(binding.end) : '';
        [startDate, endDate].forEach(input => { input.disabled = !binding; });
        showPeriodStatus();
    }
    function loadPeriods() {
        periodMetadata = filterOptions.periods_by_factory?.[factorySelect.value] || null;
        resetSelect(periodSelect, 'یک دوره ثبت‌شده را انتخاب کنید');
        if (periodMetadata?.options.length) {
            const defaultBinding = periodMetadata.options.find(item => item.id === periodMetadata.default_period_id);
            periodSelect.replaceChildren(option('', defaultBinding ? 'دوره فعال یکتا' : 'یک دوره ثبت‌شده را انتخاب کنید'),
                ...periodMetadata.options.map(item => option(item.id, item.id + ' | ' +
                    window.JalaliDate.formatDateOnly(item.start) + ' تا ' + window.JalaliDate.formatDateOnly(item.end))));
            periodSelect.disabled = false;
        }
        fillPeriodDates();
    }
    function paramsForCurrentSelection() {
        const params = new URLSearchParams({factory: factorySelect.value});
        if (categorySelect.value) params.set('category', categorySelect.value);
        if (subcategorySelect.value) params.set('subcategory', subcategorySelect.value);
        if (productSelect.value) params.set('product', productSelect.value);
        return params;
    }
    function analysisParams() {
        const params = paramsForCurrentSelection();
        if (periodSelect.value) params.set('period', periodSelect.value);
        const inputs = dateInputs();
        if (inputs.valid && inputs.start) { params.set('start', inputs.start); params.set('end', inputs.end); }
        return params;
    }
    // Include visible date text too: even invalid edits invalidate the accepted snapshot.
    function scopeKey() {
        return JSON.stringify([factorySelect.value, categorySelect.value, subcategorySelect.value,
            productSelect.value, periodSelect.value, startDate.value, endDate.value]);
    }
    function invalidateAnalysis() {
        analysisSequence += 1;
        if (analysisRequest) analysisRequest.abort();
        analysisRequest = null;
        analysisLoading = false;
        acceptedSnapshot = null;
        acceptedScope = null;
        exportBtn.disabled = true;
        report.clear();
        byId('noDataPlaceholder').hidden = false;
        setStatus(byId('analysisStatus'), 'NOT_SELECTED', 'انتخاب‌ها تغییر کرده‌اند؛ برای این دامنه تحلیل تازه اجرا کنید.');
        updateControls();
    }
    async function readResponse(response) {
        if (response.redirected || response.status === 401) throw {kind: 'SESSION', status: response.status};
        if (!(response.headers.get('content-type') || '').toLowerCase().includes('application/json'))
            throw {kind: 'NON_JSON', status: response.status};
        try { return {status: response.status, data: await response.json()}; }
        catch (_) { throw {kind: 'JSON', status: response.status}; }
    }
    function transportMessage(error) {
        if (error.kind === 'SESSION') return statusMessages[401];
        if (error.kind === 'NON_JSON') return 'پاسخ سامانه قابل خواندن نیست. وضعیت ورود را بررسی کنید و دوباره تلاش کنید.';
        if (error.kind === 'JSON') return 'پاسخ سامانه JSON معتبر نیست. دوباره تلاش کنید.';
        if (error.kind === 'SCHEMA') return 'نسخه یا ساختار پاسخ سامانه پشتیبانی نمی‌شود. صفحه را بازآوری کنید.';
        return 'ارتباط با سامانه برقرار نشد. اتصال را بررسی کنید و دوباره تلاش کنید.';
    }
    function hierarchyValid(data, params) {
        return data?.version === '1' && data.factory?.id === factorySelect.value &&
            ['OK', 'UNCONFIGURED', 'NO_MATCH'].includes(data.state) && data.operators?.all === ALL &&
            ['category', 'subcategory', 'product'].every(key => data.selection?.[key] === params.get(key)) &&
            ['categories', 'subcategories', 'products'].every(key => Array.isArray(data.options?.[key]) &&
                new Set(data.options[key].map(item => item.id)).size === data.options[key].length &&
                data.options[key].every(item => typeof item.id === 'string' && item.id && item.id !== ALL && typeof item.label === 'string' &&
                    (key !== 'products' || (typeof item.category === 'string' && typeof item.subcategory === 'string'))));
    }
    async function refreshHierarchy(level) {
        const sequence = ++requestSequence;
        if (activeRequest) activeRequest.abort();
        if (!factorySelect.value) {
            hierarchyLoading = false;
            resetChildren(0);
            setStatus(byId('filterStatus'), 'NOT_SELECTED', 'ابتدا یک کارخانه را انتخاب کنید.');
            updateControls();
            return;
        }
        activeRequest = new AbortController();
        const previous = {category: categorySelect.value, subcategory: subcategorySelect.value, product: productSelect.value};
        if (level <= 2) resetChildren(level);
        const params = paramsForCurrentSelection();
        const scope = params.toString();
        hierarchyLoading = true;
        [categorySelect, subcategorySelect, productSelect].forEach(select => { select.disabled = true; });
        setStatus(byId('filterStatus'), 'LOADING', 'در حال دریافت گزینه‌های مجاز…');
        updateControls();
        try {
            const response = await fetch('/api/dashboard/filter-options?' + params, {
                headers: {'Accept': 'application/json'}, signal: activeRequest.signal, cache: 'no-store'
            });
            const {status, data} = await readResponse(response);
            if (sequence !== requestSequence || scope !== paramsForCurrentSelection().toString()) return;
            if (status !== 200) {
                resetChildren(0);
                setStatus(byId('filterStatus'), data.state || 'UNAVAILABLE', statusMessages[status] || 'دریافت گزینه‌ها ممکن نیست.');
                return;
            }
            if (!hierarchyValid(data, params)) throw {kind: 'SCHEMA'};
            fillSelect(categorySelect, data.options.categories, 'یک دسته را انتخاب کنید', previous.category);
            if (categorySelect.value) fillSelect(subcategorySelect, data.options.subcategories, 'یک زیردسته را انتخاب کنید', previous.subcategory);
            else resetSelect(subcategorySelect, 'ابتدا دسته را انتخاب کنید');
            if (subcategorySelect.value) fillSelect(productSelect, data.options.products, 'یک محصول را انتخاب کنید', previous.product);
            else resetSelect(productSelect, 'ابتدا زیردسته را انتخاب کنید');
            setStatus(byId('filterStatus'), data.state,
                data.state === 'UNCONFIGURED' ? 'این کارخانه هنوز پیکربندی محصول ندارد.' :
                selectionComplete() ? 'دامنه انتخاب‌شده آماده تحلیل است.' : 'هر سه سطح را صریح انتخاب کنید؛ «همه» نیز یک انتخاب صریح است.');
        } catch (error) {
            if (sequence !== requestSequence || error.name === 'AbortError') return;
            resetChildren(0);
            setStatus(byId('filterStatus'), 'UNAVAILABLE', transportMessage(error));
        } finally {
            if (sequence === requestSequence) { hierarchyLoading = false; activeRequest = null; updateControls(); }
        }
    }
    function scopeMatches(data, params) {
        if (!data.scope) return false;
        return data.scope.factory?.id === params.get('factory') &&
            ['category', 'subcategory', 'product'].every(key => data.scope.selection?.[key] === params.get(key)) &&
            (!data.period || ((!params.has('period') || data.period.id === params.get('period')) &&
                (!params.has('start') || data.period.start === params.get('start')) &&
                (!params.has('end') || data.period.end === params.get('end'))));
    }
    function freeze(value) {
        if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
        return value;
    }
    async function analyze(event) {
        event.preventDefault();
        if (analysisLoading || hierarchyLoading || !selectionComplete() || !dateInputs().valid) return;
        invalidateAnalysis();
        const sequence = ++analysisSequence;
        const scope = scopeKey();
        const params = analysisParams();
        analysisRequest = new AbortController();
        analysisLoading = true;
        byId('noDataPlaceholder').hidden = true;
        setStatus(byId('analysisStatus'), 'LOADING', 'در حال محاسبه از منابع مجاز همین کارخانه…');
        updateControls();
        try {
            const response = await fetch('/api/cost_analysis?' + params, {
                headers: {'Accept': 'application/json'}, signal: analysisRequest.signal, cache: 'no-store'
            });
            const received = await readResponse(response);
            if (sequence !== analysisSequence || scope !== scopeKey()) return;
            const {status, data} = received;
            if (!report.validate(data)) throw {kind: 'SCHEMA', status};
            const matches = scopeMatches(data, params);
            if (status === 200 || status === 422) {
                if ((status === 200 || data.scope) && !matches) throw {kind: 'SCHEMA', status};
                const snapshot = freeze(data);
                report.render(snapshot);
                // An accepted 422 snapshot can contain valuable excluded rows; access/transport failures never export.
                if (matches && (status === 200 || data.detail_rows.length > 0)) {
                    acceptedSnapshot = snapshot;
                    acceptedScope = scope;
                }
                setStatus(byId('analysisStatus'), data.state,
                    status === 422 ? statusMessages[422] : data.state === 'PARTIAL' ?
                        'مجموع جزئی: بعضی پیکربندی‌ها حذف شده‌اند؛ پوشش و دلایل حذف را بررسی کنید.' :
                    data.state === 'NO_MATCH' ? 'انتخاب معتبر است اما هیچ پیکربندی منطبق پیدا نشد.' : 'گزارش این دامنه با موفقیت محاسبه شد.');
            } else {
                setStatus(byId('analysisStatus'), data.state, statusMessages[status] || 'دریافت تحلیل ممکن نیست. دوباره تلاش کنید.');
                byId('noDataPlaceholder').hidden = false;
            }
            byId('analysisStatus').dataset.httpStatus = String(status);
        } catch (error) {
            if (sequence !== analysisSequence || error.name === 'AbortError') return;
            report.clear();
            acceptedSnapshot = null;
            acceptedScope = null;
            byId('noDataPlaceholder').hidden = false;
            setStatus(byId('analysisStatus'), 'UNAVAILABLE', transportMessage(error));
            if (error.status) byId('analysisStatus').dataset.httpStatus = String(error.status);
        } finally {
            if (sequence === analysisSequence) { analysisLoading = false; analysisRequest = null; updateControls(); }
        }
    }
    factorySelect.replaceChildren(option('', 'یک کارخانه را انتخاب کنید'),
        ...filterOptions.factories.map(factory => option(factory.id, factory.name)));
    factorySelect.addEventListener('change', () => { invalidateAnalysis(); loadPeriods(); refreshHierarchy(0); });
    categorySelect.addEventListener('change', () => { invalidateAnalysis(); refreshHierarchy(1); });
    subcategorySelect.addEventListener('change', () => { invalidateAnalysis(); refreshHierarchy(2); });
    productSelect.addEventListener('change', () => {
        invalidateAnalysis();
        setStatus(byId('filterStatus'), selectionComplete() ? 'OK' : 'NOT_SELECTED',
            selectionComplete() ? 'دامنه انتخاب‌شده آماده تحلیل است.' : 'یک محصول یا «همه» را انتخاب کنید.');
        updateControls();
    });
    byId('retryHierarchyBtn').addEventListener('click', () => { invalidateAnalysis(); refreshHierarchy(0); });
    periodSelect.addEventListener('change', () => { invalidateAnalysis(); fillPeriodDates(); });
    [startDate, endDate].forEach(input => input.addEventListener('input', () => { invalidateAnalysis(); showPeriodStatus(); }));
    byId('analysisForm').addEventListener('submit', analyze);
    exportBtn.addEventListener('click', () => {
        if (!acceptedSnapshot || acceptedScope !== scopeKey() || exportBtn.disabled) return;
        const blob = new Blob([report.csv(acceptedSnapshot)], {type: 'text/csv;charset=utf-8;'});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'cost-analysis-' + new Date().toISOString().slice(0,10) + '.csv';
        document.body.append(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    updateControls();
})(window, document);
