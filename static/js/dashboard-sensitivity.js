/* One exact configuration, current authorized registry, server-only costing. */
(function (window, document) {
    'use strict';
    const byId = id => document.getElementById(id);
    const form = byId('sens-form');
    if (!form) return;
    const model = window.DashboardSensitivityModel;
    const numbers = window.DashboardNumbers;
    const options = JSON.parse(byId('dashboardOptions').textContent);
    const selects = ['factory', 'category', 'subcategory', 'product', 'period'].map(key => byId('sens-' + key));
    const [factory, category, subcategory, product, period] = selects;
    const runButton = byId('sens-run'), resetButton = byId('sens-reset');
    const refreshButton = byId('sens-refresh'), exportButton = byId('sens-export');
    const baselineView = window.DashboardSensitivityView.mount(byId('sens-baseline'));
    const comparisonView = window.DashboardLab.mount(byId('sens-results'));
    const draftSets = {A: new Map(), B: new Map()};
    let activeScenario = 'A', drafts = draftSets.A;
    let acceptedLab = null;
    const experiments = window.DashboardLabControls.mount(byId('lab-experiment-controls'), () => {
        invalidateComparison('تنظیم آزمایش تغییر کرده است؛ نتیجه و خروجی قبلی معتبر نیستند.'); controls();
    });
    let hierarchyGeneration = 0, hierarchyRequest = null, hierarchyLoading = false;
    let registryGeneration = 0, registryRequest = null, registryLoading = false;
    let scenarioGeneration = 0, scenarioRequest = null, scenarioLoading = false, revision = 0;
    let context = null, contextScope = null, latestBaseline = null;
    let accepted = null, acceptedScope = null, acceptedRevision = null, nextDraftId = 0;
    const messages = {
        400: 'انتخاب یا تغییر پیشنهادی معتبر نیست؛ ورودی‌ها و محدودیت‌ها را بررسی کنید.',
        401: 'نشست شما پایان یافته است. دوباره وارد سامانه شوید.',
        403: 'مجوز این درخواست در دسترس نیست یا تغییر کرده است. اطلاعات قبلی پاک شد.',
        404: 'کارخانه انتخاب‌شده در دسترس نیست.',
        413: 'حجم درخواست بیشتر از حد مجاز است. تعداد یا طول تغییرها را کاهش دهید.',
        422: 'خط‌مبنای این پیکربندی قابل محاسبه نیست؛ دلیل‌های زیر را بررسی کنید.',
        503: 'داده‌های مورد نیاز فعلاً در دسترس نیست. دوباره تلاش کنید.',
        500: 'محاسبه سناریو انجام نشد. دوباره تلاش کنید یا با مسئول سامانه تماس بگیرید.'
    };
    function node(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }
    function option(value, label) {
        const result = node('option', '', label); result.value = value; return result;
    }
    function status(id, state, message, httpStatus) {
        const target = byId(id);
        target.textContent = message;
        target.dataset.state = state;
        if (httpStatus !== undefined) target.dataset.httpStatus = String(httpStatus);
        else delete target.dataset.httpStatus;
        target.className = 'dashboard-status ' + (state === 'OK' ? 'is-success' :
            state === 'LOADING' ? 'is-loading' : state === 'NOT_SELECTED' ? 'is-neutral' : 'is-warning');
    }
    function selection() {
        return {factory: factory.value, category: category.value, subcategory: subcategory.value,
            product: product.value, period_id: period.value,
            productLabel: product.selectedOptions[0]?.dataset.productLabel || ''};
    }
    function scopeKey() { return JSON.stringify(selects.map(select => select.value)); }
    function complete() {
        return selects.every(select => !select.disabled && select.value && select.value !== '__ALL__');
    }
    function baselineAvailable() {
        return contextScope === scopeKey() && context?.baseline?.state === 'OK';
    }
    function draftValidation() {
        const scenarios = [];
        for (const id of ['A', 'B']) {
            const overrides = [];
            for (const [parameterId, draft] of draftSets[id]) {
                const parameter = context?.parameters.find(item => item.parameter_id === parameterId);
                if (!parameter) return {valid:false,error:'پارامتر پیشنهادی دیگر مجاز نیست.'};
                const result = model.validateOverride(parameter, draft.mode, draft.raw);
                if (!result.valid) return result;
                overrides.push(result.override);
            }
            scenarios.push({id,overrides});
        }
        const experiment = experiments.prepare();
        experiments.showError(experiment.error);
        if (!experiment.valid) return experiment;
        const selected = selection();
        const check = model.buildRequest(selected, scenarios[0].overrides);
        if (!check.valid) return check;
        const body = {...check.body, scenarios, experiment:experiment.spec}; delete body.overrides;
        const json=JSON.stringify(body);
        if (new TextEncoder().encode(json).length>65536) return {valid:false,error:'حجم درخواست بیشتر از حد مجاز است.'};
        return {valid:true,json};
    }
    function controls() {
        runButton.disabled = hierarchyLoading || registryLoading || scenarioLoading || !complete() ||
            !baselineAvailable() || !draftValidation().valid;
        runButton.textContent = scenarioLoading ? 'در حال اجرای سناریو…' : 'اجرای سناریو';
        resetButton.disabled = !draftSets.A.size && !draftSets.B.size && !accepted && !scenarioLoading && experiments.prepare().spec === null;
        refreshButton.disabled = !complete() || hierarchyLoading || registryLoading || scenarioLoading;
        exportButton.disabled = !accepted || acceptedScope !== scopeKey() || acceptedRevision !== revision;
        form.setAttribute('aria-busy', String(hierarchyLoading || registryLoading || scenarioLoading));
    }
    function cancelScenario() {
        scenarioGeneration += 1;
        scenarioRequest?.abort(); scenarioRequest = null; scenarioLoading = false;
    }
    function invalidateComparison(message) {
        revision += 1;
        cancelScenario();
        accepted = null; acceptedLab = null; acceptedScope = null; acceptedRevision = null;
        exportButton.disabled = true;
        numbers.closeAll(document);
        comparisonView.clear(); byId('sens-comparison').hidden = true;
        if (latestBaseline && contextScope === scopeKey()) {
            byId('sens-baseline').hidden = false;
            baselineView.render(latestBaseline);
        }
        if (message) status('sens-status', 'NOT_SELECTED', message);
    }
    function cancelRegistry() {
        registryGeneration += 1;
        registryRequest?.abort(); registryRequest = null; registryLoading = false;
    }
    function clearContext() {
        numbers.closeAll(document);
        accepted = null; acceptedLab = null; acceptedScope = null; acceptedRevision = null;
        comparisonView.clear(); byId('sens-comparison').hidden = true; exportButton.disabled = true;
        context = null; contextScope = null; latestBaseline = null; draftSets.A.clear(); draftSets.B.clear(); experiments.clear();
        baselineView.clear(); byId('sens-baseline').hidden = true;
        renderEditor();
    }
    function changeScope() {
        cancelRegistry();
        invalidateComparison('انتخاب تغییر کرده است؛ یک پیکربندی و دوره دقیق را تکمیل کنید.');
        clearContext(); controls();
    }
    function resetSelect(select, placeholder, disabled = true) {
        select.replaceChildren(option('', placeholder)); select.disabled = disabled;
    }
    function resetChildren(level) {
        if (level <= 0) resetSelect(category, 'ابتدا کارخانه را انتخاب کنید');
        if (level <= 1) resetSelect(subcategory, 'ابتدا دسته را انتخاب کنید');
        if (level <= 2) resetSelect(product, 'ابتدا زیردسته را انتخاب کنید');
    }
    function fillSelect(select, items, placeholder, previous) {
        const children = items.map(item => {
            const entry = option(item.id, select === product ? item.label + ' | ' + item.category + ' / ' + item.subcategory : item.label);
            if (select === product) entry.dataset.productLabel = item.label;
            return entry;
        });
        select.replaceChildren(option('', placeholder), ...children);
        select.disabled = false;
        if (items.some(item => item.id === previous)) select.value = previous;
    }
    function loadPeriods() {
        resetSelect(period, 'یک دوره ثبت‌شده را انتخاب کنید');
        const metadata = options.periods_by_factory?.[factory.value];
        if (metadata?.options.length) {
            period.replaceChildren(option('', 'یک دوره ثبت‌شده را صریح انتخاب کنید'), ...metadata.options.map(item =>
                option(item.id, item.id + ' | ' + window.JalaliDate.formatDateOnly(item.start) + ' تا ' + window.JalaliDate.formatDateOnly(item.end))));
            period.disabled = false;
        }
        showPeriod();
    }
    function showPeriod() {
        const binding = options.periods_by_factory?.[factory.value]?.options.find(item => item.id === period.value);
        status('sens-period-status', binding ? 'OK' : 'NOT_SELECTED', binding ?
            window.JalaliDate.formatDateOnly(binding.start) + ' تا ' + window.JalaliDate.formatDateOnly(binding.end) +
            ' — این بازه به‌معنای سابقه تاریخی منابع نیست.' :
            !period.disabled ? 'دوره را صریح انتخاب کنید؛ دوره ضمنی برای حساسیت استفاده نمی‌شود.' :
                factory.value ? 'دوره معتبر نصب‌شده در دسترس نیست؛ با مسئول سامانه تماس بگیرید.' : 'دوره پس از انتخاب کارخانه نمایش داده می‌شود.');
    }
    function hierarchyParams() {
        const params = new URLSearchParams({factory: factory.value});
        if (category.value) params.set('category', category.value);
        if (subcategory.value) params.set('subcategory', subcategory.value);
        if (product.value) params.set('product', product.value);
        return params;
    }
    async function readResponse(response) {
        if (response.redirected || response.status === 401) throw {kind: 'SESSION', status: response.status};
        if (!(response.headers.get('content-type') || '').toLowerCase().includes('application/json'))
            throw {kind: 'NON_JSON', status: response.status};
        try { return {status: response.status, data: await response.json()}; }
        catch (_) { throw {kind: 'JSON', status: response.status}; }
    }
    function transportMessage(error) {
        if (error.kind === 'SESSION') return messages[401];
        if (error.kind === 'NON_JSON') return 'پاسخ سامانه JSON نیست. وضعیت ورود را بررسی کنید و دوباره تلاش کنید.';
        if (error.kind === 'JSON') return 'پاسخ سامانه JSON معتبر نیست. دوباره تلاش کنید.';
        if (error.kind === 'SCHEMA') return 'ساختار یا نسخه پاسخ سامانه معتبر نیست. صفحه را بازآوری کنید.';
        return 'ارتباط با سامانه برقرار نشد. اتصال را بررسی کنید و دوباره تلاش کنید.';
    }
    function hierarchyValid(data, params) {
        return data?.version === '1' && data.factory?.id === factory.value &&
            ['OK', 'UNCONFIGURED', 'NO_MATCH'].includes(data.state) && data.operators?.all === '__ALL__' &&
            ['category', 'subcategory', 'product'].every(key => data.selection?.[key] === params.get(key)) &&
            ['categories', 'subcategories', 'products'].every(key => Array.isArray(data.options?.[key]) &&
                new Set(data.options[key].map(item => item.id)).size === data.options[key].length &&
                data.options[key].every(item => typeof item.id === 'string' && item.id && item.id !== '__ALL__' &&
                    typeof item.label === 'string' && (key !== 'products' ||
                    (typeof item.category === 'string' && typeof item.subcategory === 'string'))));
    }
    async function loadHierarchy(level) {
        const generation = ++hierarchyGeneration;
        hierarchyRequest?.abort(); hierarchyRequest = null;
        resetChildren(level);
        if (!factory.value) {
            hierarchyLoading = false;
            status('sens-filter-status', 'NOT_SELECTED', 'ابتدا یک کارخانه را انتخاب کنید.'); controls(); return;
        }
        const previous = {category: category.value, subcategory: subcategory.value, product: product.value};
        const params = hierarchyParams(), key = params.toString();
        hierarchyRequest = new AbortController(); hierarchyLoading = true;
        [category, subcategory, product].forEach(select => { select.disabled = true; });
        status('sens-filter-status', 'LOADING', 'در حال دریافت گزینه‌های مجاز…');
        byId('sens-retry-options').hidden = true; controls();
        try {
            const response = await fetch('/api/dashboard/filter-options?' + params,
                {headers: {Accept: 'application/json'}, cache: 'no-store', signal: hierarchyRequest.signal});
            const received = await readResponse(response);
            if (generation !== hierarchyGeneration || key !== hierarchyParams().toString()) return;
            if (received.status !== 200) throw {kind: 'HTTP', status: received.status};
            if (!hierarchyValid(received.data, params)) throw {kind: 'SCHEMA', status: received.status};
            fillSelect(category, received.data.options.categories, 'یک دسته را انتخاب کنید', previous.category);
            if (category.value) fillSelect(subcategory, received.data.options.subcategories, 'یک زیردسته را انتخاب کنید', previous.subcategory);
            else resetSelect(subcategory, 'ابتدا دسته را انتخاب کنید');
            if (subcategory.value) fillSelect(product, received.data.options.products, 'یک محصول دقیق را انتخاب کنید', previous.product);
            else resetSelect(product, 'ابتدا زیردسته را انتخاب کنید');
            status('sens-filter-status', received.data.state, received.data.state === 'UNCONFIGURED' ?
                'این کارخانه هنوز پیکربندی محصول ندارد.' : received.data.state === 'NO_MATCH' ?
                    'در این مسیر محصولی موجود نیست.' : 'دسته، زیردسته و یک محصول را صریح انتخاب کنید.');
        } catch (error) {
            if (generation !== hierarchyGeneration || error.name === 'AbortError') return;
            resetChildren(0); clearContext();
            status('sens-filter-status', 'UNAVAILABLE', messages[error.status] || transportMessage(error), error.status);
            byId('sens-retry-options').hidden = false;
        } finally {
            if (generation === hierarchyGeneration) {
                hierarchyLoading = false; hierarchyRequest = null; controls(); maybeLoadRegistry();
            }
        }
    }
    function domainText(parameter) {
        const domain = parameter.domain;
        const bounds = [];
        if (domain.minimum !== null) bounds.push((domain.minimum_exclusive ? 'بیشتر از ' : 'حداقل ') + numbers.format(domain.minimum, {compact: false}));
        if (domain.maximum !== null) bounds.push((domain.maximum_exclusive ? 'کمتر از ' : 'حداکثر ') + numbers.format(domain.maximum, {compact: false}));
        return bounds.length ? 'محدوده مقدار نهایی: ' + bounds.join('؛ ') : 'مقدار نهایی بدون سقف ثبت‌شده';
    }
    function renderEditor() {
        numbers.closeAll(document);
        const groups = {general_parameters: byId('sens-general-parameters'), factory_parameters: byId('sens-factory-parameters')};
        Object.values(groups).forEach(group => group.replaceChildren());
        const available = context?.parameters || [];
        const editorStatus = byId('sens-editor-status');
        if (editorStatus) editorStatus.textContent = !context ? 'پس از تکمیل انتخاب، پارامترهای مجاز همین پیکربندی دریافت می‌شوند.' :
            !available.length ? 'خط‌مبنا در دسترس است؛ برای این پیکربندی پارامتر قابل ویرایش مجاز ندارید. اجرای بدون تغییر ممکن است.' :
                'فقط پارامترهای مجاز همین انتخاب نمایش داده می‌شوند. تغییرها تا درخواست شما اجرا نمی‌شوند.';
        byId('sens-editor').hidden = !context;
        for (const [groupName, target] of Object.entries(groups)) {
            target.hidden = !context?.permissions[groupName];
            if (!context?.permissions[groupName]) continue;
            const list = available.filter(parameter => parameter.group === groupName);
            target.append(node('h3', 'sens-group-heading', groupName === 'general_parameters' ? 'پارامترهای عمومی' : 'پارامترهای کارخانه'));
            if (!list.length) target.append(node('p', 'sens-help', 'پارامتر قابل استفاده‌ای در این گروه گزارش نشده است.'));
            for (const parameter of list) {
                const card = node('div', 'sens-parameter-row'); card.dataset.parameterId = parameter.parameter_id;
                const header = node('div', 'sens-parameter-head');
                const title = node('strong', '', parameter.label);
                const add = node('button', 'btn btn-outline-primary btn-sm', drafts.has(parameter.parameter_id) ? 'در پیش‌نویس' : 'افزودن تغییر');
                add.type = 'button'; add.dataset.addParameter = parameter.parameter_id;
                add.disabled = drafts.has(parameter.parameter_id) || drafts.size >= 64 || !parameter.editable || !parameter.applicable;
                add.addEventListener('click', () => addDraft(parameter));
                header.append(title, add);
                const baseline = node('div', 'sens-parameter-baseline'); baseline.append(node('span', '', 'مقدار خط‌مبنا: '),
                    numbers.value(document, parameter.baseline_value, {unit: parameter.unit, compact: false}));
                card.append(header, baseline, node('p', 'sens-parameter-meta', domainText(parameter)),
                    node('p', 'sens-parameter-meta', 'روش‌های مجاز: ' + parameter.supported_modes.map(mode => mode === 'absolute' ? 'مقدار نهایی' : 'تغییر درصدی').join('، ')));
                if (parameter.effect_state === 'MATHEMATICAL_ZERO') card.append(node('p', 'sens-effect-note',
                    'با ثابت‌بودن دیگر ورودی‌های خط‌مبنا اثر این پارامتر صفر است؛ تغییرهای ترکیبی می‌توانند اثر آن را فعال کنند.'));
                target.append(card);
            }
        }
        const unsupported = byId('sens-unsupported'); unsupported.replaceChildren();
        unsupported.hidden = !context?.unsupported_parameters.length;
        if (context?.unsupported_parameters.length) {
            const details = node('details', 'sens-unsupported-details');
            details.append(node('summary', '', 'ورودی‌های پشتیبانی‌نشده'));
            const list = node('ul');
            context.unsupported_parameters.forEach(item => list.append(node('li', '', item.message)));
            details.append(list); unsupported.append(details);
        }
        renderDrafts(); controls();
    }
    function addDraft(parameter) {
        if (!context || drafts.has(parameter.parameter_id) || drafts.size >= 64 || !parameter.editable || !parameter.applicable) return;
        invalidateComparison('پیش‌نویس تغییر کرده است؛ برای مشاهده مقایسه، سناریو را اجرا کنید.');
        drafts.set(parameter.parameter_id, {mode: parameter.supported_modes[0], raw: '', id: ++nextDraftId});
        renderEditor(); byId('sens-value-' + nextDraftId)?.focus();
    }
    function checkDraft(item, draft, input, errorNode) {
        const result = model.validateOverride(item, draft.mode, draft.raw);
        input.setAttribute('aria-invalid', String(!result.valid));
        errorNode.textContent = result.valid ? '' : result.error;
        errorNode.hidden = result.valid;
        const summary = input.closest('.sens-draft-item').querySelector('[data-draft-summary]');
        summary.textContent = result.valid ? (draft.mode === 'absolute' ? 'مقدار نهایی پیشنهادی: ' : 'تغییر نسبت به خط‌مبنا: ') +
            numbers.format(result.override.value, {unit: draft.mode === 'percent_change' ? 'percent' : item.unit, compact: false}) : 'مقدار پیشنهادی را کامل کنید.';
    }
    function renderDrafts() {
        const target = byId('sens-draft'); target.replaceChildren();
        if (!drafts.size) { target.append(node('p', 'sens-help', 'تغییری در پیش‌نویس نیست. اجرای بدون تغییر، خط‌مبنا و سناریوی یکسان را نشان می‌دهد.')); return; }
        const list = node('div', 'sens-draft-list');
        for (const [id, draft] of drafts) {
            const parameter = context.parameters.find(item => item.parameter_id === id);
            if (!parameter) continue;
            const row = node('div', 'sens-draft-item'); row.dataset.parameterId = id;
            const heading = node('div', 'sens-parameter-head');
            const remove = node('button', 'btn btn-outline-secondary btn-sm', 'حذف تغییر');
            remove.type = 'button'; remove.dataset.removeParameter = id;
            remove.setAttribute('aria-label', 'حذف تغییر ' + parameter.label);
            remove.addEventListener('click', () => {
                invalidateComparison('یک تغییر حذف شد؛ مقایسه قبلی معتبر نیست.'); drafts.delete(id); renderEditor();
            });
            heading.append(node('strong', '', parameter.label), remove);
            const fields = node('div', 'sens-parameter-controls');
            const modeField = node('div'), valueField = node('div');
            const modeId = 'sens-mode-' + draft.id, valueId = 'sens-value-' + draft.id;
            const modeLabel = node('label', '', 'روش تغییر'); modeLabel.htmlFor = modeId;
            const mode = node('select', 'form-select'); mode.id = modeId; mode.dataset.overrideMode = '';
            mode.append(...parameter.supported_modes.map(item => option(item, item === 'absolute' ? 'مقدار نهایی' : 'تغییر درصدی'))); mode.value = draft.mode;
            const valueLabel = node('label', '', 'مقدار پیشنهادی'); valueLabel.htmlFor = valueId;
            const input = node('input', 'form-control'); input.id = valueId; input.dataset.overrideValue = '';
            input.type = 'text'; input.inputMode = 'decimal'; input.autocomplete = 'off'; input.dir = 'ltr'; input.value = draft.raw;
            // The adapter enforces 128 canonical characters; raw localized input is bounded separately.
            input.maxLength = 256;
            const error = node('p', 'sens-field-error'); error.id = valueId + '-error'; error.setAttribute('aria-live', 'polite');
            const help = node('p', 'sens-help'); help.id = valueId + '-help';
            help.textContent = 'مقدار نهایی، مقدار فرضی جدید را تعیین می‌کند. تغییر درصدی نسبت به خط‌مبناست؛ سهم ۵۰ با ‎+۱۰٪ به ۵۵ می‌رسد.';
            input.setAttribute('aria-describedby', help.id + ' ' + error.id);
            modeField.append(modeLabel, mode); valueField.append(valueLabel, input);
            fields.append(modeField, valueField);
            const summary = node('p', 'sens-draft-summary'); summary.dataset.draftSummary = '';
            row.append(heading, fields, help, summary, error); list.append(row);
            const edit = () => {
                draft.mode = mode.value; draft.raw = input.value;
                invalidateComparison('پیش‌نویس تغییر کرده است؛ مقایسه قبلی معتبر نیست.');
                checkDraft(parameter, draft, input, error); controls();
            };
            mode.addEventListener('change', edit); input.addEventListener('input', edit);
            checkDraft(parameter, draft, input, error);
        }
        target.append(list);
    }
    function contextSignature(snapshot) {
        if (!snapshot) return null;
        return JSON.stringify([snapshot.baseline, snapshot.parameters.map(item => [item.parameter_id, item.baseline_value]), snapshot.source_lineage]);
    }
    function acceptContext(snapshot, scope) {
        context = snapshot; contextScope = scope;
        if (snapshot.period) {
            const range = window.JalaliDate.formatDateOnly(snapshot.period.start) + ' تا ' + window.JalaliDate.formatDateOnly(snapshot.period.end);
            status('sens-period-status', 'OK', range + ' — مرزهای دوره از پاسخ فعلی سرور؛ این بازه به‌معنای سابقه تاریخی منابع نیست.');
            const selectedPeriod = Array.from(period.options).find(item => item.value === snapshot.period.id);
            if (selectedPeriod) selectedPeriod.textContent = snapshot.period.id + ' | ' + range;
        }
        // Every POST may change permissions. Discard drafts absent from the new authorized registry.
        for (const set of Object.values(draftSets)) for (const id of set.keys()) if (!snapshot.parameters.some(item => item.parameter_id === id)) set.delete(id);
        experiments.update(snapshot.parameters);
        latestBaseline = snapshot.baseline ? {...snapshot, scenario: null, delta: null, effective_overrides: []} : null;
        renderEditor();
        if (byId('sens-catalog')) byId('sens-catalog').open = true;
        if (latestBaseline) { baselineView.render(latestBaseline); byId('sens-baseline').hidden = false; }
        else { baselineView.clear(); byId('sens-baseline').hidden = true; }
    }
    function safeFailure(received, snapshot, scope) {
        const {status: httpStatus} = received;
        const captured = snapshot.identity && snapshot.period && model.matchesScope(snapshot, selection());
        if (captured && ![401, 403, 404].includes(httpStatus)) acceptContext(snapshot, scope);
        else clearContext();
        const issues = snapshot.issues.map(issue => issue.message).filter(Boolean).join(' ');
        // API issue messages are whitelisted and never echo submitted values.
        status('sens-status', snapshot.state, (messages[httpStatus] || 'سناریو اجرا نشد.') + (issues ? ' ' + issues : ''), httpStatus);
    }
    function validateReceived(received) {
        let snapshot;
        try { snapshot = model.adapt(received.data); }
        catch (_) { throw {kind: 'SCHEMA', status: received.status}; }
        if (snapshot.identity && snapshot.period && !model.matchesScope(snapshot, selection()))
            throw {kind: 'SCHEMA', status: received.status};
        return snapshot;
    }
    function maybeLoadRegistry() { if (complete() && !hierarchyLoading) loadRegistry(); else controls(); }
    async function loadRegistry() {
        if (!complete() || hierarchyLoading) return;
        cancelRegistry(); invalidateComparison('خط‌مبنا و پارامترهای مجاز دوباره دریافت می‌شوند.');
        clearContext();
        const generation = ++registryGeneration, scope = scopeKey();
        registryRequest = new AbortController(); registryLoading = true;
        const selected = selection();
        const params = new URLSearchParams({factory: selected.factory, category: selected.category,
            subcategory: selected.subcategory, product: selected.product, period: selected.period_id});
        status('sens-status', 'LOADING', 'در حال دریافت خط‌مبنا و پارامترهای مجاز…'); controls();
        try {
            const response = await fetch('/api/dashboard/sensitivity/parameters?' + params,
                {headers: {Accept: 'application/json'}, signal: registryRequest.signal, cache: 'no-store'});
            const received = await readResponse(response);
            if (generation !== registryGeneration || scope !== scopeKey()) return;
            const snapshot = validateReceived(received);
            if (received.status === 200 && snapshot.state === 'OK' && snapshot.baseline?.state === 'OK' && !snapshot.scenario) {
                acceptContext(snapshot, scope);
                status('sens-status', 'OK', 'خط‌مبنا آماده است. تغییرهای پیشنهادی را اضافه کنید و سناریو را اجرا کنید.', received.status);
            } else safeFailure(received, snapshot, scope);
        } catch (error) {
            if (generation !== registryGeneration || error.name === 'AbortError') return;
            clearContext(); status('sens-status', 'UNAVAILABLE', transportMessage(error), error.status);
        } finally {
            if (generation === registryGeneration) { registryLoading = false; registryRequest = null; controls(); }
        }
    }
    async function execute(event) {
        event.preventDefault();
        if (scenarioLoading || registryLoading || hierarchyLoading || !complete() || !baselineAvailable()) return;
        const prepared = draftValidation();
        if (!prepared.valid) { status('sens-status', 'INVALID_INPUT', prepared.error); controls(); return; }
        const previousContext = contextSignature(context);
        invalidateComparison(); cancelRegistry();
        const generation = ++scenarioGeneration, scope = scopeKey(), draftRevision = revision;
        scenarioRequest = new AbortController(); scenarioLoading = true;
        status('sens-status', 'LOADING', 'در حال اجرای سناریوی فرضی از منابع مجاز فعلی…'); controls();
        try {
            const response = await fetch('/api/dashboard/sensitivity/visual-analysis', {method: 'POST',
                headers: {Accept: 'application/json', 'Content-Type': 'application/json'}, credentials: 'same-origin',
                body: prepared.json, cache: 'no-store', signal: scenarioRequest.signal});
            const received = await readResponse(response);
            if (generation !== scenarioGeneration || scope !== scopeKey() || draftRevision !== revision) return;
            const visual = window.DashboardLab.adapt(received.data);
            const snapshot = visual.context;
            if (snapshot.identity && snapshot.period && !model.matchesScope(snapshot, selection())) throw {kind:'SCHEMA',status:received.status};
            if (received.status === 200 && visual.lab && snapshot.state === 'OK' && snapshot.baseline?.state === 'OK' &&
                snapshot.scenario?.state === 'OK' && snapshot.delta) {
                const changed = previousContext !== contextSignature(snapshot);
                acceptContext(snapshot, scope);
                accepted = snapshot; acceptedLab = visual.lab; acceptedScope = scope; acceptedRevision = revision;
                baselineView.clear(); byId('sens-baseline').hidden = true;
                byId('sens-comparison').hidden = false; comparisonView.render(visual.lab);
                if (byId('sens-catalog')) byId('sens-catalog').open = false;
                status('sens-status', 'OK', changed ?
                    'منابع یا خط‌مبنای مجاز از زمان دریافت قبلی تغییر کرده‌اند؛ هر دو نتیجه از خط‌مبنای تازه همین اجرا هستند.' :
                    'سناریو اجرا شد؛ هر دو نتیجه از منابع و خط‌مبنای مشترک همین اجرا هستند.', received.status);
            } else safeFailure(received, snapshot, scope);
        } catch (error) {
            if (generation !== scenarioGeneration || error.name === 'AbortError') return;
            clearContext(); status('sens-status', 'UNAVAILABLE', transportMessage(error), error.status);
        } finally {
            if (generation === scenarioGeneration) { scenarioLoading = false; scenarioRequest = null; controls(); }
        }
    }
    function reset() {
        invalidateComparison('پیش‌نویس و مقایسه پاک شدند؛ آخرین خط‌مبنای مجاز همین انتخاب حفظ شده است.');
        draftSets.A.clear(); draftSets.B.clear(); experiments.reset(); renderEditor(); controls();
    }
    function download() {
        if (!accepted || acceptedScope !== scopeKey() || acceptedRevision !== revision) return;
        const blob = new Blob([window.DashboardLab.csv(acceptedLab)], {type: 'text/csv;charset=utf-8'});
        const url = URL.createObjectURL(blob);
        const anchor = node('a'); anchor.href = url; anchor.download = 'dashboard-sensitivity.csv';
        document.body.append(anchor); anchor.click(); anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
    }
    factory.replaceChildren(option('', 'یک کارخانه را انتخاب کنید'), ...options.factories.map(item => option(item.id, item.name)));
    factory.addEventListener('change', () => { changeScope(); loadPeriods(); loadHierarchy(0); });
    category.addEventListener('change', () => { changeScope(); loadHierarchy(1); });
    subcategory.addEventListener('change', () => { changeScope(); loadHierarchy(2); });
    product.addEventListener('change', () => { changeScope(); maybeLoadRegistry(); });
    period.addEventListener('change', () => { changeScope(); showPeriod(); maybeLoadRegistry(); });
    form.addEventListener('submit', execute);
    resetButton.addEventListener('click', reset);
    refreshButton.addEventListener('click', loadRegistry);
    exportButton.addEventListener('click', download);
    byId('sens-retry-options').addEventListener('click', () => { changeScope(); loadHierarchy(0); });
    document.addEventListener('dashboard:tabchange', event => {
        const active = event.detail.panel === 'sensitivity';
        baselineView.setActive(active); comparisonView.setActive(active); numbers.closeAll(document);
    });
    window.addEventListener('pagehide', () => { cancelRegistry(); cancelScenario(); hierarchyRequest?.abort(); baselineView.destroy(); comparisonView.destroy(); });
    byId('lab-draft-scenario').addEventListener('change', event => { activeScenario = event.target.value; drafts = draftSets[activeScenario]; byId('lab-draft-heading').textContent = 'پیش‌نویس مستقل سناریو ' + activeScenario; renderEditor(); });
    renderEditor(); controls();
})(window, document);
