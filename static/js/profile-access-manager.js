(() => {
  'use strict';

  const configNode = document.getElementById('accessManagerConfig');
  if (!configNode) return;

  const config = JSON.parse(configNode.textContent);
  const states = new Map();
  const permissionMap = Object.freeze({
    NONE: [], READ: ['READ'], WRITE: ['READ', 'WRITE'],
    MODIFY: ['READ', 'WRITE', 'MODIFY']
  });
  const admins = new Set(['IT_ADMIN', 'FINANCE_ECONOMIC_ADMIN']);
  const clone = value => JSON.parse(JSON.stringify(value));
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function selectedLevel(state, scope, factoryId, module) {
    const stored = scope === 'GLOBAL'
      ? state.global[module.value]
      : state.factories[factoryId]?.[module.value];
    return stored || (module.minimum_level === 'READ' ? 'READ' : 'NONE');
  }

  function selector(containerId, scope, factoryId, module) {
    const state = states.get(containerId);
    const row = element('div', 'module-row');
    const id = `${containerId}-${scope}-${factoryId || 'global'}-${module.value}`;
    const label = element('label', '', module.label);
    label.htmlFor = id;
    if (module.minimum_level === 'READ') {
      label.append(element('small', 'mandatory-access-note', 'حداقل اجباری: فقط مشاهده'));
    }
    const select = element('select', 'form-select access-level');
    select.id = id;
    select.dataset.scope = scope;
    select.dataset.factoryId = factoryId || '';
    select.dataset.module = module.value;
    config.levels
      .filter(level => module.minimum_level !== 'READ' || level.value !== 'NONE')
      .forEach(level => {
        const option = element('option', '', level.label);
        option.value = level.value;
        select.append(option);
      });
    select.value = selectedLevel(state, scope, factoryId, module);
    select.addEventListener('change', () => {
      const target = scope === 'GLOBAL' ? state.global : state.factories[factoryId];
      // Baseline Desk READ is effective policy, not a redundant persisted grant.
      target[module.value] = module.minimum_level === 'READ' && select.value === 'READ'
        ? 'NONE' : select.value;
      renderSummary(containerId);
    });
    row.append(label, select);
    return row;
  }

  function summaryFor(modules) {
    const counts = {READ: 0, WRITE: 0, MODIFY: 0};
    Object.values(modules || {}).forEach(level => {
      if (counts[level] !== undefined) counts[level] += 1;
    });
    return `${counts.READ} فقط مشاهده، ${counts.WRITE} ثبت اطلاعات، ${counts.MODIFY} ویرایش کامل`;
  }

  function renderSummary(containerId) {
    const root = document.getElementById(containerId);
    const state = states.get(containerId);
    root.querySelectorAll('[data-access-summary]').forEach(node => {
      node.textContent = summaryFor(state.factories[node.dataset.accessSummary]);
    });
    const lines = [];
    if (Object.values(state.global).some(level => level !== 'NONE')) {
      lines.push(`دسترسی سراسری: ${summaryFor(state.global)}`);
    }
    Object.keys(state.factories).sort().forEach(id => {
      const factory = config.factories.find(item => item.id === id);
      lines.push(`${factory?.name || 'کارخانه غیرفعال'}: ${summaryFor(state.factories[id])}`);
    });
    const summary = root.querySelector('.manager-summary');
    if (summary) summary.textContent = lines.length
      ? lines.join(' | ')
      : 'فقط دسترسی پایه میز کار برقرار است؛ دسترسی صریح دیگری انتخاب نشده است.';
  }

  function factoryCard(containerId, factoryId) {
    const state = states.get(containerId);
    const factory = config.factories.find(item => item.id === factoryId);
    const card = element('details', 'factory-access-card');
    card.open = true;
    const header = element('summary', 'factory-card-header');
    header.append(
      element('strong', '', `${factory?.name || 'کارخانه تاریخی'}${factory && !factory.is_active ? ' — غیرفعال' : ''}`),
      element('span', 'access-summary')
    );
    header.lastElementChild.dataset.accessSummary = factoryId;
    card.append(header);

    const actions = element('div', 'access-actions my-2');
    [['همه فقط مشاهده', 'READ'], ['دسترسی کامل به همه', 'MODIFY'], ['پاک کردن همه', 'NONE']]
      .forEach(([text, level]) => {
        const button = element('button', 'btn btn-sm', text);
        button.type = 'button';
        button.addEventListener('click', () => {
          config.factory_modules.forEach(module => { state.factories[factoryId][module.value] = level; });
          render(containerId);
        });
        actions.append(button);
      });
    const remove = element('button', 'btn btn-sm btn-danger', 'حذف دسترسی این کارخانه');
    remove.type = 'button';
    remove.addEventListener('click', () => {
      const hasAccess = Object.values(state.factories[factoryId]).some(value => value !== 'NONE');
      if (!hasAccess || window.confirm('دسترسی‌های ثبت‌شده این کارخانه حذف شوند؟')) {
        delete state.factories[factoryId];
        render(containerId);
      }
    });
    actions.append(remove);
    card.append(actions);
    config.factory_modules.forEach(module => card.append(selector(containerId, 'FACTORY', factoryId, module)));
    return card;
  }

  function render(containerId) {
    const root = document.getElementById(containerId);
    const state = states.get(containerId);
    root.replaceChildren();
    const granular = element('div', 'granular-access');

    if (config.global_modules.length) {
      const section = element('section', 'access-section');
      section.append(element('h4', 'fs-6', 'دسترسی سراسری'));
      config.global_modules.forEach(module => section.append(selector(containerId, 'GLOBAL', null, module)));
      granular.append(section);
    }
    const cards = element('div', 'factory-access-cards');
    Object.keys(state.factories).sort().forEach(factoryId => cards.append(factoryCard(containerId, factoryId)));
    granular.append(cards);

    const addBox = element('div', 'access-actions mt-3');
    const choices = element('select', 'form-select');
    choices.setAttribute('aria-label', 'انتخاب کارخانه برای افزودن');
    const placeholder = element('option', '', 'انتخاب کارخانه');
    placeholder.value = '';
    choices.append(placeholder);
    config.factories
      .filter(factory => factory.is_active && !state.factories[factory.id])
      .forEach(factory => {
        const option = element('option', '', `${factory.name} (${factory.code})`);
        option.value = factory.id;
        choices.append(option);
      });
    const add = element('button', 'btn', '+ افزودن کارخانه');
    add.type = 'button';
    add.disabled = choices.options.length === 1;
    add.addEventListener('click', () => {
      if (!choices.value) return;
      state.factories[choices.value] = {};
      config.factory_modules.forEach(module => { state.factories[choices.value][module.value] = 'NONE'; });
      render(containerId);
    });
    addBox.append(choices, add);
    granular.append(addBox);

    const summary = element('p', 'manager-summary alert alert-light mt-3');
    summary.setAttribute('aria-live', 'polite');
    granular.append(summary);
    root.append(granular);

    const admin = element('div', 'admin-access-panel');
    admin.hidden = true;
    admin.append(
      element('strong', '', 'دسترسی کامل سامانه'),
      element('p', 'mb-0 mt-2', 'این کاربر به تمامی کارخانه‌ها، ماژول‌ها و داده‌های فعلی و آینده دسترسی کامل دارد.')
    );
    root.append(admin);
    renderSummary(containerId);
  }

  function load(containerId, state) {
    states.set(containerId, clone(state || {global: {}, factories: {}}));
    render(containerId);
  }

  function toggleRole(containerId, role) {
    const root = document.getElementById(containerId);
    const isAdmin = admins.has(role);
    root.querySelector('.granular-access').hidden = isAdmin;
    root.querySelector('.admin-access-panel').hidden = !isAdmin;
  }

  function serialize(containerId) {
    const state = states.get(containerId);
    const grants = [];
    Object.keys(state.global).sort().forEach(module => {
      const level = state.global[module];
      if (level !== 'NONE') grants.push({scope_type: 'GLOBAL', factory_id: null, module, permissions: permissionMap[level]});
    });
    Object.keys(state.factories).sort().forEach(factoryId => {
      Object.keys(state.factories[factoryId]).sort().forEach(module => {
        const level = state.factories[factoryId][module];
        if (level !== 'NONE') grants.push({scope_type: 'FACTORY', factory_id: factoryId, module, permissions: permissionMap[level]});
      });
    });
    return grants;
  }

  window.profileAccessManager = Object.freeze({load, toggleRole, serialize});
})();
