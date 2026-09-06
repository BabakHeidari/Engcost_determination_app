(() => {
  'use strict';
  const config = JSON.parse(document.getElementById('accessManagerConfig').textContent);
  const states = new Map();
  const permissionMap = {NONE: [], READ: ['READ'], WRITE: ['READ', 'WRITE'], MODIFY: ['READ', 'WRITE', 'MODIFY']};
  const admins = new Set(['IT_ADMIN', 'FINANCE_ECONOMIC_ADMIN']);
  const clone = value => JSON.parse(JSON.stringify(value));

  function selector(containerId, scope, factoryId, module, label) {
    const row = document.createElement('div'); row.className = 'module-row';
    const id = `${containerId}-${scope}-${factoryId || 'global'}-${module}`;
    const title = document.createElement('label'); title.htmlFor = id; title.textContent = label;
    const select = document.createElement('select'); select.id = id; select.className = 'form-select access-level';
    select.dataset.scope = scope; select.dataset.factoryId = factoryId || ''; select.dataset.module = module;
    config.levels.forEach(level => { const option=document.createElement('option'); option.value=level.value; option.textContent=level.label; select.append(option); });
    const state = states.get(containerId); select.value = scope === 'GLOBAL' ? (state.global[module] || 'NONE') : (state.factories[factoryId]?.[module] || 'NONE');
    select.addEventListener('change', () => { const target=scope === 'GLOBAL' ? state.global : state.factories[factoryId]; target[module]=select.value; renderSummary(containerId); });
    row.append(title, select); return row;
  }

  function summaryFor(modules) {
    const counts={READ:0,WRITE:0,MODIFY:0}; Object.values(modules || {}).forEach(level => {if(counts[level] !== undefined) counts[level]++;});
    return `${counts.READ} فقط مشاهده، ${counts.WRITE} ثبت اطلاعات، ${counts.MODIFY} ویرایش کامل`;
  }
  function renderSummary(containerId) {
    const root=document.getElementById(containerId), state=states.get(containerId);
    root.querySelectorAll('[data-access-summary]').forEach(node => {node.textContent=summaryFor(state.factories[node.dataset.accessSummary]);});
    const lines=[]; if(Object.values(state.global).some(level => level !== 'NONE')) lines.push(`دسترسی سراسری: ${summaryFor(state.global)}`);
    Object.keys(state.factories).sort().forEach(id => {const f=config.factories.find(item => item.id===id); lines.push(`${f?.name || 'کارخانه غیرفعال'}: ${summaryFor(state.factories[id])}`);});
    const summary=root.querySelector('.manager-summary'); if(summary) summary.textContent=lines.length ? lines.join(' | ') : 'هیچ دسترسی صریحی انتخاب نشده است.';
  }
  function render(containerId) {
    const root=document.getElementById(containerId), state=states.get(containerId); root.replaceChildren();
    const granular=document.createElement('div'); granular.className='granular-access';
    if(config.global_modules.length) { const section=document.createElement('section'); section.className='access-section'; section.innerHTML='<h4 class="fs-6">دسترسی سراسری</h4>'; config.global_modules.forEach(m => section.append(selector(containerId,'GLOBAL',null,m.value,m.label))); granular.append(section); }
    const cards=document.createElement('div'); cards.className='factory-access-cards';
    Object.keys(state.factories).sort().forEach(factoryId => { const factory=config.factories.find(item=>item.id===factoryId); const card=document.createElement('details'); card.className='factory-access-card'; card.open=true;
      const header=document.createElement('summary'); header.className='factory-card-header'; const inactive=factory && !factory.is_active ? ' — غیرفعال' : ''; header.innerHTML=`<strong>${factory?.name || 'کارخانه تاریخی'}${inactive}</strong><span class="access-summary" data-access-summary="${factoryId}"></span>`; card.append(header);
      const actions=document.createElement('div'); actions.className='access-actions my-2'; [['همه فقط مشاهده','READ'],['دسترسی کامل به همه','MODIFY'],['پاک کردن همه','NONE']].forEach(([text,level]) => {const b=document.createElement('button'); b.type='button'; b.className='btn btn-sm'; b.textContent=text; b.addEventListener('click',()=>{config.factory_modules.forEach(m=>state.factories[factoryId][m.value]=level); render(containerId);}); actions.append(b);});
      const remove=document.createElement('button'); remove.type='button'; remove.className='btn btn-sm btn-danger'; remove.textContent='حذف دسترسی این کارخانه'; remove.addEventListener('click',()=>{const hasAccess=Object.values(state.factories[factoryId]).some(v=>v!=='NONE'); if(!hasAccess || confirm('دسترسی‌های ثبت‌شده این کارخانه حذف شوند؟')) {delete state.factories[factoryId]; render(containerId);}}); actions.append(remove); card.append(actions);
      config.factory_modules.forEach(m=>card.append(selector(containerId,'FACTORY',factoryId,m.value,m.label))); cards.append(card);
    }); granular.append(cards);
    const addBox=document.createElement('div'); addBox.className='access-actions mt-3'; const choices=document.createElement('select'); choices.className='form-select'; choices.setAttribute('aria-label','انتخاب کارخانه برای افزودن'); const placeholder=document.createElement('option'); placeholder.value=''; placeholder.textContent='انتخاب کارخانه'; choices.append(placeholder); config.factories.filter(f=>f.is_active && !state.factories[f.id]).forEach(f=>{const o=document.createElement('option');o.value=f.id;o.textContent=`${f.name} (${f.code})`;choices.append(o);}); const add=document.createElement('button');add.type='button';add.className='btn';add.textContent='+ افزودن کارخانه';add.disabled=choices.options.length===1;add.addEventListener('click',()=>{if(!choices.value)return;state.factories[choices.value]={};config.factory_modules.forEach(m=>state.factories[choices.value][m.value]='NONE');render(containerId);}); addBox.append(choices,add);granular.append(addBox);
    const summary=document.createElement('p');summary.className='manager-summary alert alert-light mt-3';summary.setAttribute('aria-live','polite');granular.append(summary); root.append(granular);
    const admin=document.createElement('div');admin.className='admin-access-panel';admin.hidden=true;admin.innerHTML='<strong>دسترسی کامل سامانه</strong><p class="mb-0 mt-2">این کاربر به تمامی کارخانه‌ها، ماژول‌ها و داده‌های فعلی و آینده دسترسی کامل دارد.</p>';root.append(admin); renderSummary(containerId);
  }
  function load(containerId, state) { states.set(containerId, clone(state || {global:{},factories:{}})); render(containerId); }
  function toggleRole(containerId, role) { const root=document.getElementById(containerId), isAdmin=admins.has(role); root.querySelector('.granular-access').hidden=isAdmin; root.querySelector('.admin-access-panel').hidden=!isAdmin; }
  function serialize(containerId) { const state=states.get(containerId), grants=[]; Object.keys(state.global).sort().forEach(module=>{const level=state.global[module];if(level!=='NONE')grants.push({scope_type:'GLOBAL',factory_id:null,module,permissions:permissionMap[level]});});Object.keys(state.factories).sort().forEach(factoryId=>Object.keys(state.factories[factoryId]).sort().forEach(module=>{const level=state.factories[factoryId][module];if(level!=='NONE')grants.push({scope_type:'FACTORY',factory_id:factoryId,module,permissions:permissionMap[level]});}));return grants; }
  window.profileAccessManager={load,toggleRole,serialize};
})();
