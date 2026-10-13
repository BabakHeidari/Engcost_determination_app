/* Accepted exact backend datasets; Number is used only for plotting coordinates. */
(function (w) {
    'use strict';
    const N = () => w.DashboardNumbers;
    const FACTORS = Object.freeze({
        BOM: ['مواد و اقلام BOM', '#147f86'], AdministrativeandResearch: ['اداری و پژوهش', '#8c72b0'],
        Payroll: ['حقوق و دستمزد', '#496bb1'], Overhead: ['سربار', '#bb853b'],
        FinancialCosts: ['هزینه مالی', '#bd647d'], Depriciation: ['استهلاک', '#468875'],
        NonOperationalCostsandIncomes: ['هزینه و درآمد غیرعملیاتی', '#748296'], OTHER: ['سایر', '#a5afbb'],
        TECHNICAL_RECONCILIATION: ['تطبیق فنی دقت محاسبه', '#8b8b8b']
    });
    const label = id => FACTORS[id]?.[0] || id;
    const color = id => FACTORS[id]?.[1] || '#147f86';
    const identity = r => [r.factory_id, r.category, r.subcategory, r.product].join(' / ');
    const key = r => JSON.stringify([r.factory_id, r.category, r.subcategory, r.product]);
    function el(doc, tag, text, cls) { const x = doc.createElement(tag); if (text !== undefined) x.textContent = text; if (cls) x.className = cls; return x; }
    function numeric(value) { const n = value === null ? NaN : Number(value); if (!Number.isFinite(n)) throw Error('NON_FINITE_COORDINATE'); return n; }
    function shell(container) {
        const doc = container.ownerDocument, panels = [], listeners = [];
        let destroyed = false, active = !container.closest('[role="tabpanel"]')?.hidden;
        function panel(title, scope, rows, columns, options, action, lazy = false) {
            const box = el(doc, lazy ? 'details' : 'section', undefined, 'report-chart-card visual-panel');
            box.append(el(doc, lazy ? 'summary' : 'h2', title));
            box.append(el(doc, 'p', scope, 'report-chart-subtitle'));
            const chartNode = el(doc, 'div', undefined, 'report-chart'); chartNode.role = 'img'; chartNode.setAttribute('aria-label', title + '؛ جدول دقیق همراه');
            const note = el(doc, 'p', 'مقادیر کامل و کپی دقیق در جدول همراه در دسترس‌اند.', 'report-chart-note');
            const wrap = el(doc, 'div', undefined, 'table-responsive');
            const table = el(doc, 'table', undefined, 'table report-table'); table.append(el(doc, 'caption', title + ' — ' + scope));
            const head = el(doc, 'thead'), hr = el(doc, 'tr'); columns.forEach(c => { const th = el(doc, 'th', c.title); th.scope = 'col'; hr.append(th); });
            if (action) hr.append(el(doc, 'th', 'تمرکز محلی'));
            head.append(hr); table.append(head); const body = el(doc, 'tbody');
            let chart = null;
            rows.forEach((r, i) => {
                const tr = el(doc, 'tr');
                columns.forEach(c => { const td = el(doc, 'td'); const value = c.get(r), unit = typeof c.unit === 'function' ? c.unit(r) : c.unit; td.append(unit ? N().value(doc, value, {unit, compact: true}) : el(doc, 'span', value ?? 'در دسترس نیست')); tr.append(td); });
                if (action) { const td = el(doc, 'td'), button = el(doc, 'button', 'بررسی', 'btn btn-outline-secondary btn-sm'); button.type = 'button'; button.setAttribute('aria-label', 'بررسی ' + (columns[0].get(r) || i));
                    button.addEventListener('click', () => { if (chart) { chart.dispatchAction({type:'downplay'}); chart.dispatchAction({type:'highlight', dataIndex:i}); } action(r, i); }); td.append(button); tr.append(td); }
                body.append(tr);
            });
            table.append(body); wrap.append(table);
            const exactTable = el(doc, 'details', undefined, 'visual-exact-table'); exactTable.append(el(doc, 'summary', 'جدول مقادیر دقیق و بررسی با صفحه‌کلید'), wrap);
            box.append(chartNode, note, exactTable); container.append(box);
            function dispose() { if (chart) { try { chart.dispose(); } catch (_) {} chart = null; } }
            function draw() {
                dispose();
                if (destroyed || !active || (lazy && !box.open)) return;
                chartNode.hidden = false;
                try {
                    if (!w.echarts || !rows.length) throw Error('NO_CHART');
                    chart = w.echarts.init(chartNode);
                    const config = options();
                    if (!config) throw Error('NO_CHART');
                    for (const axis of [config.xAxis, config.yAxis].flat().filter(Boolean)) {
                        if (axis.type === 'value') axis.axisLabel = {...axis.axisLabel, formatter:value => N().format(String(value), {unit:axis.name?.includes('ریال') ? 'IRR' : undefined, compact:true}).replace(/ ریال$/, '')};
                        if (axis.type === 'category') axis.axisLabel = {...axis.axisLabel, width:140, overflow:'truncate'};
                    }
                    chart.setOption({...config, animation:false, textStyle:{fontFamily:'IRANSansX, Tahoma, sans-serif'},
                        tooltip:{trigger:'item', renderMode:'richText', confine:true, formatter:p => {
                            const r = p.data?.exactRow || rows[p.dataIndex];
                            if (r?.children) return r.name + ': ' + N().exact(r.value, 'IRR/period');
                            if (r?.identity && r.value !== undefined && !r.id && !r.unit_cost) return identity(r.identity) + ': ' + N().exact(r.value, 'IRR/period');
                            return r ? columns.map(c => c.title + ': ' + (c.unit ? N().exact(c.get(r), typeof c.unit === 'function' ? c.unit(r) : c.unit) : c.get(r))).join('\n') : '';
                        }}}, true);
                    if (action) chart.on('click', p => { const r = p.data?.exactRow || rows[p.dataIndex]; if (r) action(r, p.dataIndex); });
                    note.textContent = 'برای بررسی محلی، نمودار یا دکمه جدول را انتخاب کنید. مقادیر دقیق در جدول‌اند.';
                } catch (_) { dispose(); chartNode.hidden = true; exactTable.open = true; note.textContent = 'نمودار در دسترس نیست؛ جدول دقیق و کنش‌های آن قابل استفاده‌اند.'; }
            }
            if (lazy) box.addEventListener('toggle', () => { if (box.open) draw(); else dispose(); });
            const p = {draw, dispose, resize:() => chart?.resize(), box}; panels.push(p); if (!lazy) draw();
            return p;
        }
        const resize = () => panels.forEach(p => p.resize());
        const observer = w.ResizeObserver ? new w.ResizeObserver(resize) : null; observer?.observe(container);
        w.addEventListener('resize', resize); listeners.push(() => w.removeEventListener('resize', resize));
        return {panel, setActive(value) { active = value; panels.forEach(p => value ? p.draw() : p.dispose()); },
            destroy() { destroyed = true; panels.forEach(p => p.dispose()); observer?.disconnect(); listeners.forEach(f => f()); container.replaceChildren(); }, resize};
    }
    const textCol = (title, get) => ({title, get});
    const amountCol = (title, get, unit) => ({title, get, unit});
    function bars(rows, value, labels, unit, colors) {
        return {grid:{left:12,right:24,top:24,bottom:45,containLabel:true},
            xAxis:{type:'value', name:unit==='IRR/product'?'ریال / محصول':unit==='IRR/period'?'ریال / دوره':unit,nameLocation:'middle',nameGap:28}, yAxis:{type:'category',inverse:true,data:labels},
            series:[{type:'bar',data:rows.map((r,i) => ({value:numeric(value(r)), exactRow:r,itemStyle:{color:colors ? colors(r,i) : '#147f86'}}))}],
            ...(rows.length > 10 ? {dataZoom:[{type:'inside',yAxisIndex:0,filterMode:'none'},{type:'slider',yAxisIndex:0,filterMode:'none',startValue:0,endValue:9}]} : {})};
    }
    function cost(report, visuals, container, callbacks) {
        const doc = container.ownerDocument, workspace = shell(container), cb = callbacks || {};
        const coverage = (report.state === 'PARTIAL' ? 'مجموع جزئی؛ ' : '') + 'جمعیت منتخب محاسبه‌شده: ' + visuals.coverage.calculated + ' از ' + visuals.coverage.configured + '؛ دوره ' + (report.period?.id || '—');
        container.prepend(el(doc, 'p', coverage + ' — تمرکزها محلی‌اند؛ KPI، جمعیت تخصیص و CSV کامل تغییر نمی‌کنند.', 'dashboard-status is-neutral'));
        const focus = el(doc, 'section', undefined, 'visual-focus'); focus.hidden = true;
        const breadcrumb = el(doc, 'p'), back = el(doc, 'button', 'بازگشت / پاک کردن تمرکز', 'btn btn-outline-secondary'), detail = el(doc, 'div'); back.type = 'button';
        focus.append(breadcrumb, back, detail); container.append(focus);
        let focusView = null;
        function clearFocus() { focusView?.destroy(); focusView = null; detail.replaceChildren(); focus.hidden = true; cb.onResetFocus?.(); }
        back.addEventListener('click', clearFocus);
        function focusProduct(row) {
            clearFocus(); focus.hidden = false; breadcrumb.textContent = 'تمرکز محلی: ' + identity(row.identity); cb.onProductFocus?.(row.identity);
            const original = report.breakdowns.products.find(r => key(r.identity) === key(row.identity)); if (!original) return;
            focusView = shell(detail);
            const parts = visuals.factor_ids.map(id => ({id, value:row.unit_components[id]}));
            focusView.panel('اجزای هزینه واحد همین پیکربندی', 'ریال / محصول؛ مرز بررسی کارخانه فقط سهم تخصیص‌یافته pool است.', parts,
                [textCol('عامل',r=>label(r.id)),amountCol('سهم هزینه واحد',r=>r.value,'IRR/product')],
                () => bars(parts,r=>r.value,parts.map(r=>label(r.id)),'ریال / محصول',r=>color(r.id)));
            const bom = original.bom_components;
            focusView.panel('ردیف‌های مستقل BOM', 'ریال / محصول؛ ردیف‌های ماده تکراری مستقل باقی می‌مانند.', bom,
                [textCol('هویت ردیف',r=>r.row_id),textCol('ماده',r=>r.material),amountCol('هزینه ردیف',r=>r.live_cost_in_rial,'IRR/product')],
                () => bars(bom,r=>r.live_cost_in_rial,bom.map(r=>r.material+' / '+r.row_id),'ریال / محصول'));
            focus.scrollIntoView({block:'nearest'});
        }
        let compositionMode = visuals.composition_mode;
        const composition = workspace.panel('ترکیب هزینه پیش‌بینی‌شده', coverage + '؛ ریال / دوره؛ چهار عامل بزرگ و سایر، با جدول همه عوامل اصلی.', report.breakdowns.drivers,
            [textCol('عامل',r=>label(r.id)),amountCol('مبلغ',r=>r.value,'IRR/period'),amountCol('سهم از هزینه منتخب',r=>r.share,'percentage')], () => {
                const rows = visuals.composition;
                return compositionMode === 'donut' ? {series:[{type:'pie',radius:['45%','75%'],data:rows.map(r=>({name:label(r.id),value:numeric(r.value),exactRow:r,itemStyle:{color:color(r.id)}})),label:{show:false}}]} : bars(rows,r=>r.value,rows.map(r=>label(r.id)),'ریال / دوره',r=>color(r.id));
            });
        const toggle = el(doc,'button','نمای میله‌ای / حلقه‌ای','btn btn-outline-secondary btn-sm'); toggle.type='button'; toggle.disabled=visuals.composition_mode!=='donut';
        toggle.addEventListener('click',()=>{compositionMode=compositionMode==='donut'?'bar':'donut';composition.draw();});composition.box.insertBefore(toggle,composition.box.children[2]);
        let projected = false;
        const productRows = visuals.products;
        const productPanel = workspace.panel('ترکیب هزینه محصولات',coverage+'؛ اجزای BOM و شش pool برای هر هویت دقیق.',productRows,
            [textCol('پیکربندی',r=>identity(r.identity)),amountCol('هزینه واحد',r=>r.unit_cost,'IRR/product'),amountCol('هزینه دوره',r=>r.projected_cost,'IRR/period'),
                ...visuals.factor_ids.map(id=>amountCol(label(id)+' / واحد',r=>r.unit_components[id],'IRR/product')),
                ...visuals.factor_ids.map(id=>amountCol(label(id)+' / دوره',r=>r.projected_components[id],'IRR/period'))],()=>{
                const cfg=bars(productRows,r=>projected?r.projected_cost:r.unit_cost,productRows.map(r=>identity(r.identity)),projected?'ریال / دوره':'ریال / محصول');
                cfg.series=visuals.factor_ids.map(id=>({type:'bar',stack:'cost',name:label(id),itemStyle:{color:color(id)},data:productRows.map(r=>({value:numeric((projected?r.projected_components:r.unit_components)[id]),exactRow:r}))}));return cfg;
            },focusProduct);
        const mode=el(doc,'button','نمای فعلی: هزینه واحد؛ تغییر به هزینه دوره','btn btn-outline-secondary btn-sm');mode.type='button';
        mode.addEventListener('click',()=>{projected=!projected;mode.textContent=projected?'نمای فعلی: هزینه دوره؛ تغییر به هزینه واحد':'نمای فعلی: هزینه واحد؛ تغییر به هزینه دوره';productPanel.draw();});productPanel.box.insertBefore(mode,productPanel.box.children[2]);
        let hierarchyPath=[];
        const hierarchyMenu=el(doc,'div',undefined,'report-chart-actions');
        function hierarchyNodes(){let nodes=visuals.hierarchy;for(const name of hierarchyPath)nodes=nodes.find(r=>r.name===name)?.children||[];return nodes;}
        function drillHierarchy(r){
            if(r.identity){const product=productRows.find(p=>key(p.identity)===key(r.identity));if(product)focusProduct(product);}
            else{hierarchyPath.push(r.name);trail.textContent='تمرکز محلی: '+hierarchyPath.join(' / ');hierarchyPanel.draw();hierarchyButtons();}
        }
        function hierarchyButtons(){hierarchyMenu.replaceChildren();hierarchyNodes().forEach(r=>{const b=el(doc,'button','بررسی '+(r.name||r.identity.product),'btn btn-outline-secondary btn-sm');b.type='button';b.addEventListener('click',()=>drillHierarchy(r));hierarchyMenu.append(b);});}
        const hierarchyPanel=workspace.panel('کاوش سلسله‌مراتب هزینه',coverage+'؛ اندازه مستطیل: هزینه پیش‌بینی‌شده دوره، ریال / دوره.',productRows,
            [textCol('مسیر کامل',r=>identity(r.identity)),amountCol('هزینه دوره',r=>r.projected_cost,'IRR/period')],()=>{
                if(!visuals.treemap_available)return null;
                const nodes=hierarchyNodes();
                return {series:[{type:'treemap',nodeClick:false,roam:false,breadcrumb:{show:false},data:nodes.map(r=>({name:r.name||r.identity.product,value:numeric(r.value),exactRow:r,
                    itemStyle:{color:'#147f86'}}))}]};
            },drillHierarchy,true);
        const trail=el(doc,'p','تمرکز محلی: همه دسته‌ها'),hierBack=el(doc,'button','بازگشت / بازنشانی مسیر','btn btn-outline-secondary btn-sm');hierBack.type='button';
        hierBack.addEventListener('click',()=>{hierarchyPath.pop();trail.textContent='تمرکز محلی: '+(hierarchyPath.join(' / ')||'همه دسته‌ها');hierarchyPanel.draw();hierarchyButtons();});hierarchyPanel.box.insertBefore(trail,hierarchyPanel.box.children[2]);hierarchyPanel.box.insertBefore(hierBack,trail);hierarchyPanel.box.insertBefore(hierarchyMenu,trail);hierarchyButtons();
        workspace.panel('پارتوی مواد',coverage+'؛ ریال / دوره؛ مخرج درصد: مجموع BOM محاسبه‌شده منتخب. داده علامت‌دار یا مخرج نامثبت فقط میله دارد.',visuals.materials,
            [textCol('ماده',r=>r.material),amountCol('سهم هزینه دوره',r=>r.value,'IRR/period'),amountCol('سهم',r=>r.share,'percentage'),amountCol('سهم تجمعی',r=>r.cumulative_share,'percentage')],()=>{
                const rows=visuals.materials,cfg={grid:{left:12,right:55,bottom:65,top:25,containLabel:true},xAxis:{type:'category',data:rows.map(r=>r.material),axisLabel:{rotate:25}},yAxis:[{type:'value',name:'ریال / دوره'},{type:'value',name:'درصد'}],series:[{type:'bar',data:rows.map(r=>({value:numeric(r.value),exactRow:r})),itemStyle:{color:color('BOM')}}]};
                if(visuals.pareto_mode==='pareto')cfg.series.push({type:'line',yAxisIndex:1,data:rows.map(r=>({value:numeric(r.cumulative_share),exactRow:r}))});return cfg;
            },r=>{clearFocus();focus.hidden=false;breadcrumb.textContent='تمرکز محلی ماده: '+r.material;focusView=shell(detail);focusView.panel('ردیف‌های مشارکت‌کننده ماده',coverage+'؛ هیچ ردیف مستقل ادغام نشده است.',r.rows,
                [textCol('پیکربندی',p=>identity(p.identity)),textCol('ردیف BOM',p=>p.row_id),amountCol('هزینه واحد ردیف',p=>p.unit_contribution,'IRR/product'),amountCol('هزینه دوره ردیف',p=>p.projected_contribution,'IRR/period')],()=>bars(r.rows,p=>p.projected_contribution,r.rows.map(p=>p.row_id),'ریال / دوره'),p=>{const found=productRows.find(x=>key(x.identity)===key(p.identity));if(found)focusProduct(found);});},true);
        const heatRows=productRows.flatMap((r,y)=>visuals.factor_ids.map((id,x)=>({identity:r.identity,id,value:r.unit_components[id],x,y})));
        workspace.panel('محصول × عامل',coverage+'؛ هر خانه سهم هزینه واحد، ریال / محصول؛ رنگ فقط مقایسه دیداری است.',heatRows,
            [textCol('پیکربندی',r=>identity(r.identity)),textCol('عامل',r=>label(r.id)),amountCol('سهم هزینه واحد',r=>r.value,'IRR/product')],()=>{
                const values=heatRows.map(r=>numeric(r.value));return {grid:{left:12,right:25,bottom:90,top:15,containLabel:true},xAxis:{type:'category',data:visuals.factor_ids.map(label),axisLabel:{rotate:30}},yAxis:{type:'category',data:productRows.map(r=>identity(r.identity))},visualMap:{min:Math.min(...values),max:Math.max(...values),calculable:true,orient:'horizontal',bottom:0,inRange:{color:['#edf4f5','#147f86']}},series:[{type:'heatmap',data:heatRows.map(r=>({value:[r.x,r.y,numeric(r.value)],exactRow:r}))}]};
            },r=>focusProduct(productRows.find(p=>key(p.identity)===key(r.identity))),true);
        workspace.panel('تولید و هزینه',coverage+'؛ افقی: تولید پیش‌بینی‌شده (محصول / دوره)، عمودی: هزینه واحد (ریال / محصول)، مساحت حباب: هزینه دوره. مقدار علامت‌دار با نقطه ثابت نمایش داده می‌شود.',productRows,
            [textCol('هویت کامل',r=>identity(r.identity)),amountCol('تولید',r=>r.prediction,'product/period'),amountCol('هزینه واحد',r=>r.unit_cost,'IRR/product'),amountCol('هزینه دوره',r=>r.projected_cost,'IRR/period')],()=>{
                const maximum=Math.max(0,...productRows.map(r=>numeric(r.projected_cost)));return {grid:{left:12,right:30,bottom:50,containLabel:true},xAxis:{type:'value',name:'محصول / دوره'},yAxis:{type:'value',name:'ریال / محصول'},series:[{type:'scatter',symbolSize:(v,p)=>p.data.area, data:productRows.map(r=>({value:[numeric(r.prediction),numeric(r.unit_cost)],exactRow:r,area:numeric(r.projected_cost)<0?8:Math.max(4,Math.sqrt(numeric(r.projected_cost)/(maximum||1))*48)})),itemStyle:{color:'#147f86'}}]};
            },focusProduct,true);
        return {destroy(){focusView?.destroy();workspace.destroy();},resize:workspace.resize,clearFocus,setActive(v){workspace.setActive(v);focusView?.setActive(v);}};
    }
    function adaptCost(raw) {
        const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
        const keys = (x, required, optional = []) => object(x) && required.every(k => Object.hasOwn(x, k)) && Object.keys(x).every(k => required.includes(k) || optional.includes(k));
        const dec = x => typeof x === 'string' && /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(x);
        const nullable = x => x === null || dec(x);
        const unique = xs => new Set(xs).size === xs.length;
        const factors = Object.keys(FACTORS).filter(id => !['OTHER', 'TECHNICAL_RECONCILIATION'].includes(id));
        const same = (a, b, fields) => object(a) && object(b) && fields.every(k => a[k] === b[k]);
        const id = x => keys(x, ['factory_id', 'category', 'subcategory', 'product']) && Object.values(x).every(x => typeof x === 'string' && x.length > 0);
        const invalid = () => { throw Error('VISUAL_SCHEMA'); };
        const v = raw?.visuals, r = raw?.analysis;
        if (!keys(raw, ['version', 'analysis', 'visuals']) || raw.version !== '1' || !w.DashboardReport.validate(r) ||
            !keys(v, ['version', 'population', 'coverage', 'period', 'factor_ids', 'composition', 'composition_mode', 'products', 'hierarchy', 'hierarchy_unit',
                'treemap_available', 'materials', 'pareto_denominator', 'pareto_denominator_scope', 'pareto_mode', 'material_reconciliation', 'excluded']) ||
            v.version !== '1' || v.population !== 'selected_calculated_configurations' || !same(v.coverage, r.coverage, ['configured', 'calculated', 'excluded', 'percentage']) ||
            !(v.period === null && r.period === null || same(v.period, r.period, ['id', 'start', 'end'])) ||
            !Array.isArray(v.factor_ids) || v.factor_ids.length !== 7 || !unique(v.factor_ids) || !v.factor_ids.every(x => factors.includes(x)) ||
            !Array.isArray(v.products) || v.products.length !== r.coverage.calculated || !Array.isArray(v.excluded) || v.excluded.length !== r.coverage.excluded ||
            !Array.isArray(v.composition) || v.composition.length !== (r.coverage.calculated ? 5 : 0) || !unique(v.composition.map(x => x?.id)) ||
            !['bar', 'donut'].includes(v.composition_mode) || !['pareto', 'signed_bar'].includes(v.pareto_mode) || typeof v.treemap_available !== 'boolean' ||
            v.hierarchy_unit !== 'IRR/period' || v.pareto_denominator_scope !== 'selected_calculated_projected_BOM_total' ||
            !Array.isArray(v.hierarchy) || !Array.isArray(v.materials) || !nullable(v.pareto_denominator) || !nullable(v.material_reconciliation)) invalid();
        const originals = new Map(r.breakdowns.products.map(p => [key(p.identity), p]));
        if (!unique(v.products.map(p => id(p?.identity) ? key(p.identity) : null))) invalid();
        for (const p of v.products) {
            const original = id(p?.identity) && originals.get(key(p.identity));
            if (!original || !keys(p, ['identity', 'unit_cost', 'prediction', 'projected_cost', 'unit_components', 'projected_components', 'reconciliation']) ||
                !['unit_cost', 'prediction', 'projected_cost', 'reconciliation'].every(k => dec(p[k])) ||
                !same(p, original, ['unit_cost', 'prediction', 'projected_cost']) ||
                !keys(p.unit_components, factors) || !keys(p.projected_components, factors) || !factors.every(k => dec(p.unit_components[k]) && dec(p.projected_components[k])) ||
                p.unit_components.BOM !== original.bom_total || original.driver_components.some(d =>
                    p.unit_components[d.pool_id] !== d.per_unit_contribution || p.projected_components[d.pool_id] !== d.product_period_contribution)) invalid();
        }
        const excluded = new Map(r.detail_rows.filter(p => p.state !== 'OK').map(p => [key(p.identity), p]));
        if (!unique(v.excluded.map(p => id(p?.identity) ? key(p.identity) : null)) || v.excluded.some(p =>
            !id(p?.identity) || !excluded.has(key(p.identity)) || JSON.stringify(p) !== JSON.stringify(excluded.get(key(p.identity))))) invalid();
        const members = [];
        for (const p of v.composition) {
            if (!nullable(p?.share) || !dec(p?.value) || p.unit !== 'IRR/period') invalid();
            if (p.id === 'OTHER') {
                if (!keys(p, ['id', 'value', 'share', 'unit', 'members']) || !Array.isArray(p.members) || p.members.length !== 3 || !unique(p.members) || !p.members.every(id => factors.includes(id))) invalid();
                members.push(...p.members);
            } else {
                const original = r.breakdowns.drivers.find(d => d.id === p.id);
                if (!keys(p, ['id', 'value', 'share', 'unit', 'population']) || !original || !same(p, original, ['value', 'share', 'unit', 'population'])) invalid();
                members.push(p.id);
            }
        }
        if (r.coverage.calculated && (members.length !== 7 || !unique(members))) invalid();
        const positive = x => w.DashboardNumbers.compare(x, '0') > 0;
        const nonnegative = x => w.DashboardNumbers.compare(x, '0') >= 0;
        const total = r.kpis.partial_total ?? r.kpis.projected_total;
        if (v.composition_mode !== (total !== null && positive(total) && r.breakdowns.drivers.every(p => nonnegative(p.value)) ? 'donut' : 'bar') ||
            v.treemap_available !== (v.products.every(p => nonnegative(p.projected_cost)) && v.products.some(p => positive(p.projected_cost)))) invalid();
        const leaves = [], categories = new Set();
        for (const category of v.hierarchy) {
            if (!keys(category, ['name', 'value', 'children']) || typeof category.name !== 'string' || !dec(category.value) || !Array.isArray(category.children) || !category.children.length || categories.has(category.name)) invalid();
            categories.add(category.name); const subs = new Set();
            for (const sub of category.children) {
                if (!keys(sub, ['name', 'value', 'children']) || typeof sub.name !== 'string' || !dec(sub.value) || !Array.isArray(sub.children) || !sub.children.length || subs.has(sub.name)) invalid();
                subs.add(sub.name);
                for (const p of sub.children) {
                    const original = id(p?.identity) && originals.get(key(p.identity));
                    if (!keys(p, ['identity', 'value']) || !original || p.identity.category !== category.name || p.identity.subcategory !== sub.name || p.value !== original.projected_cost) invalid();
                    leaves.push(key(p.identity));
                }
            }
        }
        if (leaves.length !== v.products.length || !unique(leaves)) invalid();
        const bomRows = new Map(r.breakdowns.products.flatMap(p => p.bom_components.map(b => [JSON.stringify([key(p.identity), b.row_id]), b])));
        const materialRows = [];
        if (!unique(v.materials.map(p => p?.material))) invalid();
        for (const m of v.materials) {
            if (!keys(m, ['material', 'value', 'rows', 'share', 'cumulative_share']) || typeof m.material !== 'string' || !dec(m.value) || !nullable(m.share) || !nullable(m.cumulative_share) || !Array.isArray(m.rows) || !m.rows.length) invalid();
            for (const p of m.rows) {
                const rowKey = id(p?.identity) && JSON.stringify([key(p.identity), p.row_id]), original = bomRows.get(rowKey);
                if (!keys(p, ['identity', 'row_id', 'unit_contribution', 'projected_contribution']) || !original || original.material !== m.material ||
                    p.unit_contribution !== original.live_cost_in_rial || !dec(p.projected_contribution)) invalid();
                materialRows.push(rowKey);
            }
        }
        const bomTotal = r.breakdowns.drivers.find(p => p.id === 'BOM')?.value ?? null;
        if (materialRows.length !== bomRows.size || !unique(materialRows) || v.pareto_denominator !== bomTotal ||
            (bomTotal === null ? v.material_reconciliation !== null : v.material_reconciliation === null) ||
            v.pareto_mode !== (bomTotal !== null && positive(bomTotal) && v.materials.every(p => nonnegative(p.value)) ? 'pareto' : 'signed_bar')) invalid();
        const accepted = JSON.parse(JSON.stringify(raw));
        function freeze(value) { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; }
        return freeze(accepted);
    }
    w.DashboardVisuals=Object.freeze({cost,shell,bars,FACTORS,label,color,identity,numeric,textCol,amountCol,adaptCost});
})(window);
