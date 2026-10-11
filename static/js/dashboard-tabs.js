/* Local, accessible tabs; navigation does not depend on remote Bootstrap JS. */
(function (window, document) {
    'use strict';
    const list = document.querySelector('.dashboard-tabs[role="tablist"]');
    if (!list) return;
    const tabs = Array.from(list.querySelectorAll('[role="tab"]'));
    function activate(tab, focus) {
        if (!tabs.includes(tab) || tab.disabled) return;
        const previous = tabs.find(item => item.getAttribute('aria-selected') === 'true');
        tabs.forEach(item => {
            const selected = item === tab;
            item.setAttribute('aria-selected', String(selected));
            item.tabIndex = selected ? 0 : -1;
            item.classList.toggle('active', selected);
            const panel = document.getElementById(item.getAttribute('aria-controls'));
            if (panel) {
                panel.hidden = !selected;
                panel.classList.toggle('active', selected);
                panel.classList.toggle('show', selected);
            }
        });
        if (focus) tab.focus();
        if (previous === tab) return;
        if (window.DashboardNumbers) window.DashboardNumbers.closeAll(document);
        document.dispatchEvent(new CustomEvent('dashboard:tabchange', {
            detail: {panel: tab.getAttribute('aria-controls')}
        }));
        window.requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    }
    tabs.forEach(tab => {
        tab.addEventListener('click', event => {
            // Bootstrap's document delegate must not race the local hidden state.
            event.preventDefault();
            event.stopPropagation();
            activate(tab, false);
        });
        tab.addEventListener('keydown', event => {
            const index = tabs.indexOf(tab);
            const rtl = window.getComputedStyle(list).direction === 'rtl';
            let next;
            if (event.key === 'Home') next = 0;
            else if (event.key === 'End') next = tabs.length - 1;
            else if (event.key === 'ArrowRight') next = (index + (rtl ? -1 : 1) + tabs.length) % tabs.length;
            else if (event.key === 'ArrowLeft') next = (index + (rtl ? 1 : -1) + tabs.length) % tabs.length;
            else return;
            event.preventDefault();
            activate(tabs[next], true);
        });
    });
    activate(tabs.find(tab => tab.getAttribute('aria-selected') === 'true') || tabs[0], false);
})(window, document);
