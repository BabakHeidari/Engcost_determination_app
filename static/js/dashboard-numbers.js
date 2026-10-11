(function (window) {
    'use strict';

    // Presentation only: financial strings never pass through Number, parseFloat
    // or Intl.NumberFormat. Half-up rounding acts on the absolute decimal string
    // at two places (ties therefore round away from zero). Exact access and copy
    // always retain the original sign, leading digits and trailing decimal zeros.
    const DECIMAL = /^([+-]?)(\d+)(?:\.(\d+))?$/;
    const DIGITS = '۰۱۲۳۴۵۶۷۸۹';
    const UNITS = Object.freeze({
        IRR: 'ریال', 'IRR/period': 'ریال / دوره', 'IRR/product': 'ریال / محصول',
        'ریال': 'ریال', 'product/period': 'محصول / دوره', product: 'محصول',
        configuration: 'پیکربندی', count: 'عدد', 'عدد': 'عدد',
        percentage: '٪', percent: '٪', '%': '٪', '٪': '٪'
    });
    const MONEY = new Set(['IRR', 'IRR/period', 'IRR/product', 'ریال']);
    const SCALES = Object.freeze([
        { places: 0, label: '' }, { places: 6, label: 'میلیون' },
        { places: 9, label: 'میلیارد' }, { places: 12, label: 'تریلیون' }
    ]);
    const documents = new WeakMap();
    const activeDocuments = new Set();
    let nextId = 0;

    function persian(raw) {
        return String(raw).replace(/\d/g, digit => DIGITS[digit.charCodeAt(0) - 48]);
    }

    function grouped(integer) {
        return integer.replace(/\B(?=(\d{3})+(?!\d))/g, '٬');
    }

    function parse(raw) {
        if (raw === null || raw === undefined) return null;
        const original = String(raw);
        const match = original.match(DECIMAL);
        if (!match) return null;
        const integer = match[2].replace(/^0+(?=\d)/, '');
        const fraction = match[3] || '';
        return {
            original: original, sign: match[1], integer: integer, fraction: fraction,
            zero: !/[1-9]/.test(integer + fraction)
        };
    }

    function unitLabel(unit) {
        if (Object.prototype.hasOwnProperty.call(UNITS, unit)) return UNITS[unit];
        // Authorized parameter source units (for example USD/kg and IRR/USD)
        // keep their original form in formatting and the exact-value dialog.
        return typeof unit === 'string' && unit.length <= 80 && /^[\p{L}\p{N} _.-]+\/[\p{L}\p{N} _.-]+$/u.test(unit) ? unit : '';
    }

    function withUnit(content, options) {
        const label = options.showUnit === false ? '' : unitLabel(options.unit);
        return content + (label ? (label === '٪' ? '' : ' ') + label : '');
    }

    function unavailable(options) {
        return options.state === 'NOT_APPLICABLE' ? 'قابل اعمال نیست' : 'در دسترس نیست';
    }

    function compareAbsolute(left, right) {
        if (left.integer.length !== right.integer.length) return left.integer.length > right.integer.length ? 1 : -1;
        if (left.integer !== right.integer) return left.integer > right.integer ? 1 : -1;
        const length = Math.max(left.fraction.length, right.fraction.length);
        const a = left.fraction.padEnd(length, '0');
        const b = right.fraction.padEnd(length, '0');
        return a === b ? 0 : a > b ? 1 : -1;
    }

    function compare(a, b) {
        const left = parse(a), right = parse(b);
        if (!left || !right) throw new TypeError('Exact decimal comparison requires two decimal strings');
        const leftNegative = left.sign === '-' && !left.zero;
        const rightNegative = right.sign === '-' && !right.zero;
        if (leftNegative !== rightNegative) return leftNegative ? -1 : 1;
        const result = compareAbsolute(left, right);
        return leftNegative ? -result : result;
    }

    function increment(digits) {
        const result = digits.split('');
        for (let index = result.length - 1; index >= 0; index -= 1) {
            if (result[index] !== '9') {
                result[index] = String.fromCharCode(result[index].charCodeAt(0) + 1);
                return result.join('');
            }
            result[index] = '0';
        }
        return '1' + result.join('');
    }

    function shifted(value, places) {
        if (!places) return { integer: value.integer, fraction: value.fraction };
        if (value.integer.length > places) return {
            integer: value.integer.slice(0, -places),
            fraction: value.integer.slice(-places) + value.fraction
        };
        return {
            integer: '0', fraction: '0'.repeat(places - value.integer.length) + value.integer + value.fraction
        };
    }

    function rounded(value) {
        let retained = value.integer + value.fraction.slice(0, 2).padEnd(2, '0');
        if (value.fraction.length > 2 && value.fraction[2] >= '5') retained = increment(retained);
        return {
            integer: retained.slice(0, -2).replace(/^0+(?=\d)/, ''),
            fraction: retained.slice(-2).replace(/0+$/, '')
        };
    }

    function format(raw, options) {
        options = options || {};
        const value = parse(raw);
        if (!value || options.state === 'NOT_APPLICABLE') return unavailable(options);
        const sign = value.sign === '-' ? '−' : value.sign;
        // A positive/negative amount below one hundredth is informative even
        // when two-place rounding would otherwise display zero.
        if (!value.zero && compareAbsolute(value, { integer: '0', fraction: '01' }) < 0) {
            return withUnit(value.sign === '-' ? 'بیشتر از −۰٫۰۱' : 'کمتر از ۰٫۰۱', options);
        }
        let scale = 0;
        const compact = options.compact !== false && MONEY.has(options.unit);
        if (compact) {
            for (let index = 1; index < SCALES.length; index += 1) {
                if (value.integer.length > SCALES[index].places) scale = index;
            }
        }
        let display = rounded(shifted(value, SCALES[scale].places));
        // Re-evaluate from the original string when rounding crosses a scale
        // boundary, e.g. 999999999.995 -> 1 billion, rather than 1000 million.
        if (compact && scale < SCALES.length - 1 &&
                display.integer.length > SCALES[scale + 1].places - SCALES[scale].places) {
            scale += 1;
            display = rounded(shifted(value, SCALES[scale].places));
        }
        if (options.coverage && compare(raw, '100') < 0 && compare(raw, '0') >= 0 &&
                display.integer === '100' && !display.fraction) {
            return withUnit('بیش از ۹۹٫۹۹', options);
        }
        const numeric = persian(sign + grouped(display.integer) + (display.fraction ? '٫' + display.fraction : ''));
        return withUnit(numeric + (SCALES[scale].label ? ' ' + SCALES[scale].label : ''), options);
    }

    function exact(raw, unit) {
        const value = parse(raw);
        if (!value) return 'در دسترس نیست';
        const match = value.original.match(DECIMAL);
        const numeric = persian(match[1] + grouped(match[2]) + (match[3] === undefined ? '' : '٫' + match[3]));
        return withUnit(numeric, { unit: unit });
    }

    function element(doc, tag, className, text) {
        const node = doc.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function triggerFrom(state, target) {
        const trigger = target && target.closest ? target.closest('[data-exact-trigger]') : null;
        return trigger && state.values.has(trigger) ? trigger : null;
    }

    function close(state, restoreFocus) {
        if (state.closeTimer) { state.view.clearTimeout(state.closeTimer); state.closeTimer = null; }
        const trigger = state.trigger;
        state.trigger = null;
        state.pinned = false;
        state.awaitingAnchor = false;
        if (trigger) trigger.setAttribute('aria-expanded', 'false');
        if (state.portal) {
            state.portal.hidden = true;
            // A dismissed dialog must not retain values from a scope whose
            // permissions may have changed since it was opened.
            state.full.textContent = '';
            state.label.textContent = '';
            state.status.textContent = '';
        }
        if (restoreFocus && trigger && trigger.isConnected) {
            // Restoring focus must not reopen the portal through focusin.
            state.restoring = true;
            trigger.focus({ preventScroll: true });
            state.restoring = false;
        }
    }

    function position(state) {
        if (!state.trigger || !state.portal || state.portal.hidden) return;
        if (!state.trigger.isConnected) { close(state, false); return; }
        const anchor = state.trigger.getBoundingClientRect();
        const width = state.view.innerWidth, height = state.view.innerHeight;
        const outside = anchor.bottom < 0 || anchor.top > height;
        // Native keyboard focus can precede Bootstrap's smooth focus scroll.
        // Keep the newly opened dialog clamped inside the viewport until its
        // focused anchor first arrives; subsequent offscreen scrolls dismiss
        // normally. A single animation frame cannot cover a smooth scroll.
        if (outside && !state.awaitingAnchor) { close(state, false); return; }
        if (!outside) state.awaitingAnchor = false;
        const bounds = state.portal.getBoundingClientRect();
        const left = Math.max(12, Math.min(anchor.right - bounds.width, width - bounds.width - 12));
        let top = anchor.bottom + 8;
        if (top + bounds.height > height - 12 && anchor.top - bounds.height - 8 >= 12) top = anchor.top - bounds.height - 8;
        top = Math.max(12, Math.min(top, height - bounds.height - 12));
        state.portal.style.left = left + 'px';
        state.portal.style.top = top + 'px';
    }

    async function copyRaw(state) {
        if (!state.trigger) return;
        const raw = state.values.get(state.trigger).raw;
        try {
            if (state.view.navigator.clipboard && state.view.navigator.clipboard.writeText) {
                await state.view.navigator.clipboard.writeText(raw);
            } else {
                const focused = state.doc.activeElement;
                const field = element(state.doc, 'textarea');
                field.value = raw;
                field.readOnly = true;
                field.style.position = 'fixed';
                field.style.opacity = '0';
                state.doc.body.appendChild(field);
                field.select();
                const copied = state.doc.execCommand('copy');
                field.remove();
                if (focused && focused.isConnected) focused.focus({ preventScroll: true });
                if (!copied) throw new Error('Copy unavailable');
            }
            state.status.textContent = 'مقدار دقیق کپی شد';
        } catch (error) {
            state.status.textContent = 'کپی انجام نشد؛ مقدار دقیق را انتخاب کنید.';
        }
    }

    function portal(state) {
        if (state.portal) return;
        const popup = element(state.doc, 'div', 'exact-popover');
        popup.id = state.id;
        popup.dir = 'rtl';
        popup.hidden = true;
        popup.setAttribute('role', 'dialog');
        popup.setAttribute('aria-modal', 'false');
        popup.setAttribute('aria-labelledby', state.id + '-label');
        // The body-level fixed portal cannot be clipped by scrolling tables.
        popup.style.position = 'fixed';
        popup.style.zIndex = '1085';
        popup.style.width = 'min(28rem, calc(100vw - 24px))';
        popup.style.maxHeight = 'calc(100vh - 24px)';
        popup.style.overflowY = 'auto';
        state.label = element(state.doc, 'div', 'exact-popover-label', 'مقدار دقیق');
        state.label.id = state.id + '-label';
        state.full = element(state.doc, 'div', 'exact-popover-value');
        state.full.dir = 'ltr';
        const actions = element(state.doc, 'div', 'exact-popover-actions');
        state.copy = element(state.doc, 'button', 'exact-copy', 'کپی مقدار دقیق');
        state.copy.type = 'button';
        const dismiss = element(state.doc, 'button', 'exact-close', 'بستن');
        dismiss.type = 'button';
        state.status = element(state.doc, 'span', 'exact-copy-status');
        state.status.setAttribute('role', 'status');
        state.status.setAttribute('aria-live', 'polite');
        actions.append(state.copy, dismiss);
        popup.append(state.label, state.full, actions, state.status);
        state.copy.addEventListener('click', () => copyRaw(state));
        dismiss.addEventListener('click', () => close(state, true));
        state.doc.body.appendChild(popup);
        state.portal = popup;
    }

    function open(state, trigger, pinned) {
        if (state.closeTimer) { state.view.clearTimeout(state.closeTimer); state.closeTimer = null; }
        if (state.trigger && state.trigger !== trigger) close(state, false);
        portal(state);
        const info = state.values.get(trigger);
        state.trigger = trigger;
        state.pinned = state.pinned || pinned;
        state.label.textContent = info.kind === 'identifier' ? info.label + ' — شناسه کامل' : 'مقدار دقیق';
        state.full.textContent = info.kind === 'identifier' ? info.raw : exact(info.raw, info.unit);
        state.full.classList.toggle('identifier-value', info.kind === 'identifier');
        state.copy.textContent = info.kind === 'identifier' ? 'کپی شناسه کامل' : 'کپی مقدار دقیق';
        state.status.textContent = '';
        trigger.setAttribute('aria-expanded', 'true');
        state.portal.hidden = false;
        const anchor = trigger.getBoundingClientRect();
        state.awaitingAnchor = state.doc.activeElement === trigger &&
            (anchor.bottom < 0 || anchor.top > state.view.innerHeight);
        position(state);
        if (pinned) state.copy.focus({ preventScroll: true });
    }

    function scheduleClose(state) {
        if (state.closeTimer) state.view.clearTimeout(state.closeTimer);
        state.closeTimer = state.view.setTimeout(() => {
            state.closeTimer = null;
            const focused = state.doc.activeElement;
            if (!state.pinned && focused !== state.trigger && !(state.portal && state.portal.contains(focused))) close(state, false);
        }, 300);
    }

    function setup(doc) {
        if (documents.has(doc)) return documents.get(doc);
        const state = {
            doc: doc, view: doc.defaultView || window, id: 'dashboard-exact-' + (++nextId),
            values: new WeakMap(), trigger: null, portal: null, pinned: false,
            restoring: false, awaitingAnchor: false, closeTimer: null, handlers: []
        };
        function listen(target, event, handler, capture) {
            target.addEventListener(event, handler, !!capture);
            state.handlers.push([target, event, handler, !!capture]);
        }
        listen(doc, 'pointerover', event => {
            const trigger = triggerFrom(state, event.target);
            if (trigger && event.pointerType !== 'touch' && (!state.pinned || state.trigger === trigger)) open(state, trigger, false);
            else if (state.portal && state.portal.contains(event.target) && state.closeTimer) {
                state.view.clearTimeout(state.closeTimer); state.closeTimer = null;
            }
        });
        listen(doc, 'pointerout', event => {
            if (!state.trigger) return;
            const from = event.target, to = event.relatedTarget;
            const involved = from === state.trigger || state.trigger.contains(from) || (state.portal && state.portal.contains(from));
            const retained = to && (state.trigger.contains(to) || (state.portal && state.portal.contains(to)));
            if (involved && !retained) scheduleClose(state);
        });
        listen(doc, 'focusin', event => {
            if (state.restoring) return;
            const trigger = triggerFrom(state, event.target);
            if (trigger) open(state, trigger, false);
            else if (state.trigger && !(state.portal && state.portal.contains(event.target))) close(state, false);
        });
        listen(doc, 'focusout', () => { if (state.trigger) scheduleClose(state); });
        listen(doc, 'click', event => {
            const trigger = triggerFrom(state, event.target);
            if (trigger) { event.preventDefault(); open(state, trigger, true); }
            else if (state.trigger && !(state.portal && state.portal.contains(event.target))) close(state, false);
        });
        listen(doc, 'keydown', event => {
            if (event.key === 'Escape' && state.trigger) { event.preventDefault(); close(state, true); }
        });
        listen(doc, 'scroll', () => position(state), true);
        listen(state.view, 'resize', () => position(state));
        documents.set(doc, state);
        activeDocuments.add(state);
        return state;
    }

    function value(doc, raw, options) {
        options = options || {};
        const parsed = parse(raw);
        const available = parsed && options.state !== 'NOT_APPLICABLE';
        const node = element(doc, available ? 'button' : 'span',
            'report-number' + (available ? ' exact-value' : ' unavailable-value') + (options.className ? ' ' + options.className : ''), format(raw, options));
        // Keep units explicit while allowing KPI typography to emphasize the
        // amount. The formatted text and exact unit remain unchanged.
        const suffix = options.showUnit === false ? '' : unitLabel(options.unit);
        if (available && suffix && node.textContent.endsWith(suffix)) {
            const content = node.textContent;
            node.textContent = content.slice(0, -suffix.length);
            node.appendChild(element(doc, 'span', 'report-number-unit', suffix));
        }
        if (options.id) node.id = options.id;
        if (options.state) node.dataset.state = options.state;
        if (!available) return node;
        const state = setup(doc);
        node.type = 'button';
        node.dataset.raw = parsed.original;
        if (options.unit) node.dataset.unit = options.unit;
        node.dataset.exactTrigger = 'value';
        node.setAttribute('aria-haspopup', 'dialog');
        node.setAttribute('aria-expanded', 'false');
        node.setAttribute('aria-controls', state.id);
        node.setAttribute('aria-label', 'نمایش مقدار دقیق: ' + format(raw, options));
        state.values.set(node, { raw: parsed.original, unit: options.unit, kind: 'value' });
        return node;
    }

    function identifier(doc, raw, label) {
        if (raw === null || raw === undefined) return element(doc, 'span', 'unavailable-value', 'در دسترس نیست');
        raw = String(raw);
        label = label || 'اثر انگشت منبع';
        const state = setup(doc);
        const node = element(doc, 'button', 'exact-identifier');
        const short = element(doc, 'span', 'identifier-short', raw.length > 20 ? raw.slice(0, 10) + '…' + raw.slice(-6) : raw);
        short.dir = 'ltr';
        const action = element(doc, 'span', 'identifier-action', 'نمایش و کپی');
        action.dir = 'rtl';
        node.append(short, action);
        node.type = 'button';
        node.dir = 'ltr';
        node.dataset.raw = raw;
        node.dataset.exactTrigger = 'identifier';
        node.setAttribute('aria-label', label + '، نمایش و کپی شناسه کامل');
        node.setAttribute('aria-haspopup', 'dialog');
        node.setAttribute('aria-expanded', 'false');
        node.setAttribute('aria-controls', state.id);
        state.values.set(node, { raw: raw, kind: 'identifier', label: label });
        return node;
    }

    function closeAll(doc) {
        activeDocuments.forEach(state => { if (!doc || state.doc === doc) close(state, false); });
    }

    function dispose(doc) {
        activeDocuments.forEach(state => {
            if (doc && state.doc !== doc) return;
            close(state, false);
            state.handlers.forEach(binding => binding[0].removeEventListener(binding[1], binding[2], binding[3]));
            if (state.portal) state.portal.remove();
            documents.delete(state.doc);
            activeDocuments.delete(state);
        });
    }

    window.DashboardNumbers = Object.freeze({
        format: format, exact: exact, compare: compare, value: value,
        identifier: identifier, closeAll: closeAll, dispose: dispose
    });
})(window);
