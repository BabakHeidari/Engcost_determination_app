(function(w){
    'use strict';
    const fields=['version','formula_version','state','identity','period','calculated_at','source_lineage','non_persistent','permissions','parameters','unsupported_parameters','baseline','issues'];
    const decimal=v=>typeof v==='string'&&/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(v);
    function oldReport(raw,scenario=null,delta=null,effective=[]){
        const result=Object.fromEntries(fields.map(f=>[f,raw[f]]));return {...result,scenario,delta,effective_overrides:effective};
    }
    function adaptedSide(raw,id){
        const side=raw.scenarios.find(s=>s.id===id),d=raw.comparisons[id+'_minus_baseline'].unit_cost;
        return w.DashboardSensitivityModel.adapt(oldReport(raw,side.result,{amount:d.amount,percentage:d.percentage,percentage_state:d.percentage_state,unit:'IRR/product',direction:'scenario_minus_baseline'},side.effective_overrides));
    }
    const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
    const keys = (v, required) => object(v) && required.every(k => Object.hasOwn(v, k)) && Object.keys(v).every(k => required.includes(k));
    const unique = values => new Set(values).size === values.length;
    const count = v => Number.isSafeInteger(v) && v >= 0;
    const factors = ['BOM', 'AdministrativeandResearch', 'Payroll', 'Overhead', 'FinancialCosts', 'Depriciation', 'NonOperationalCostsandIncomes'];
    const zero = v => w.DashboardNumbers.compare(v, '0') === 0;
    const nonnegative = v => w.DashboardNumbers.compare(v, '0') >= 0;
    function delta(d, unit, direction, reference, target) {
        return keys(d, ['amount', 'reference', 'target', 'unit', 'direction', 'percentage_denominator', 'percentage', 'percentage_state']) &&
            d.unit === unit && d.direction === direction && ['amount', 'reference', 'target', 'percentage_denominator'].every(k => decimal(d[k])) &&
            d.reference === reference && d.target === target && d.percentage_denominator === reference &&
            (zero(reference) ? d.percentage_state === 'NOT_APPLICABLE' && d.percentage === null : d.percentage_state === 'OK' && decimal(d.percentage));
    }
    function adapt(raw) {
        if (raw?.state !== 'OK') return {context:w.DashboardSensitivityModel.adapt(raw), lab:null};
        const invalid = () => { throw Error('LAB_SCHEMA'); };
        if (!keys(raw, [...fields, 'visual_version', 'scenarios', 'comparisons', 'experiment', 'evaluation_budget', 'baseline_context']) ||
            raw.visual_version !== '1' || raw.baseline_context !== 'fresh_inputs_captured_once_for_this_request' ||
            !Array.isArray(raw.scenarios) || raw.scenarios.length !== 2 || !unique(raw.scenarios.map(s => s?.id)) ||
            !raw.scenarios.every(s => keys(s, ['id', 'result', 'effective_overrides']) && ['A', 'B'].includes(s.id)) ||
            !keys(raw.comparisons, ['A_minus_baseline', 'B_minus_baseline', 'B_minus_A'])) invalid();
        const aResult = raw.scenarios.find(s => s.id === 'A').result, bResult = raw.scenarios.find(s => s.id === 'B').result;
        for (const [direction, reference, target] of [['A_minus_baseline', raw.baseline, aResult], ['B_minus_baseline', raw.baseline, bResult], ['B_minus_A', aResult, bResult]]) {
            const c = raw.comparisons[direction], f = c?.waterfall;
            if (!reference || !target || !keys(c, ['unit_cost', 'projected_cost', 'waterfall']) ||
                !delta(c.unit_cost, 'IRR/product', direction, reference.unit_cost, target.unit_cost) ||
                !delta(c.projected_cost, 'IRR/period', direction, reference.projected_cost, target.projected_cost) ||
                !keys(f, ['reference', 'target', 'components', 'technical_reconciliation', 'reconciliation', 'unit', 'direction', 'meaning']) ||
                f.unit !== 'IRR/product' || f.direction !== direction || f.meaning !== 'output_component_differences_not_independent_input_effects' ||
                f.reference !== reference.unit_cost || f.target !== target.unit_cost || !decimal(f.reconciliation) ||
                !Array.isArray(f.components) || f.components.length !== 7 || !unique(f.components.map(r => r?.id)) || !f.components.every(r => factors.includes(r?.id)) ||
                f.technical_reconciliation?.id !== 'TECHNICAL_RECONCILIATION' || f.technical_reconciliation.value !== f.reconciliation) invalid();
            let previous = f.reference;
            for (const row of [...f.components, f.technical_reconciliation]) {
                if (!keys(row, ['id', 'value', 'start', 'end', 'offset', 'size']) || !['value', 'start', 'end', 'offset', 'size'].every(k => decimal(row[k])) ||
                    row.start !== previous || !nonnegative(row.size)) invalid();
                previous = row.end;
            }
        }
        // The established PR-08 validator enforces registry/grant redaction on
        // both results. Extensions below never infer or reconstruct source inputs.
        const a = adaptedSide(raw, 'A'); adaptedSide(raw, 'B');
        if (a.baseline.state !== 'OK' || a.scenario.state !== 'OK' || bResult.state !== 'OK') invalid();
        const registry = new Map(a.parameters.map(p => [p.parameter_id, p]));
        function input(i) {
            const p = registry.get(i?.parameter_id);
            return keys(i, ['parameter_id', 'mode', 'value', 'unit', 'final_value']) && p && p.unit === i.unit && p.supported_modes.includes(i.mode) && decimal(i.value) && decimal(i.final_value);
        }
        function effective(i, inputs) {
            const p = registry.get(i?.parameter_id), supplied = inputs.find(v => v.parameter_id === i?.parameter_id);
            return keys(i, ['parameter_id', 'mode', 'value', 'baseline_value', 'final_value', 'unit', 'provenance_state']) && p && supplied &&
                i.provenance_state === 'HYPOTHETICAL_OVERRIDE' && ['value', 'baseline_value', 'final_value'].every(k => decimal(i[k])) &&
                ['mode', 'value', 'final_value', 'unit'].every(k => i[k] === supplied[k]) && i.baseline_value === p.baseline_value;
        }
        const e = raw.experiment;
        if (e !== null) {
            if (!['tornado', 'one_factor', 'two_factor'].includes(e?.type) ||
                !keys(e, ['type', 'points', 'valid_count', 'invalid_count', 'unit_cost_unit', 'projected_cost_unit', 'reference', ...(e.type === 'tornado' ? ['ranking'] : [])]) ||
                !Array.isArray(e.points) || !e.points.length || e.points.length > ({tornado:20, one_factor:41, two_factor:121}[e.type]) ||
                e.reference !== 'captured_baseline_other_inputs_fixed' || e.unit_cost_unit !== 'IRR/product' || e.projected_cost_unit !== 'IRR/period' ||
                !count(e.valid_count) || !count(e.invalid_count) || e.valid_count !== e.points.filter(p => p.state === 'OK').length ||
                e.invalid_count !== e.points.filter(p => p.state === 'INVALID_INPUT').length || e.valid_count + e.invalid_count !== e.points.length) invalid();
            for (const p of e.points) {
                const valid = p?.state === 'OK';
                if (!keys(p, ['inputs', e.type === 'tornado' ? 'side' : 'indices', 'state', 'unit_cost', 'projected_cost', 'effective_inputs', 'issue', ...(valid ? ['unit_delta', 'projected_delta'] : [])]) ||
                    !Array.isArray(p.inputs) || p.inputs.length !== (e.type === 'two_factor' ? 2 : 1) || !p.inputs.every(input) || !unique(p.inputs.map(i => i.parameter_id)) ||
                    !Array.isArray(p.effective_inputs) || !unique(p.effective_inputs.map(i => i?.parameter_id))) invalid();
                if (valid) {
                    if (!decimal(p.unit_cost) || !decimal(p.projected_cost) || p.issue !== null || p.effective_inputs.length !== p.inputs.length || !p.effective_inputs.every(i => effective(i, p.inputs)) ||
                        !delta(p.unit_delta, 'IRR/product', 'point_minus_baseline', raw.baseline.unit_cost, p.unit_cost) ||
                        !delta(p.projected_delta, 'IRR/period', 'point_minus_baseline', raw.baseline.projected_cost, p.projected_cost)) invalid();
                } else if (p.state !== 'INVALID_INPUT' || p.unit_cost !== null || p.projected_cost !== null || p.effective_inputs.length ||
                    !keys(p.issue, ['code', 'message']) || p.issue.code !== 'SAMPLE_OUT_OF_DOMAIN' || typeof p.issue.message !== 'string') invalid();
            }
            if (e.type === 'tornado') {
                if (e.points.length % 2 || !Array.isArray(e.ranking) || e.ranking.length !== e.points.length / 2 ||
                    !unique(e.ranking.map(r => r?.parameter_id))) invalid();
                const ranges = new Map();
                for (const p of e.points) {
                    if (!['low', 'high'].includes(p.side)) invalid();
                    const id = p.inputs[0].parameter_id, range = ranges.get(id) || {};
                    if (range[p.side]) invalid(); range[p.side] = p; ranges.set(id, range);
                }
                if (ranges.size !== e.ranking.length) invalid();
                for (const r of e.ranking) {
                    const pair = ranges.get(r?.parameter_id), lo = pair?.low?.inputs[0], hi = pair?.high?.inputs[0];
                    if (!keys(r, ['parameter_id', 'impact', 'state']) || !lo || !hi || lo.mode !== hi.mode || w.DashboardNumbers.compare(lo.value, hi.value) > 0 ||
                        r.state !== (pair.low.state === 'OK' && pair.high.state === 'OK' ? 'OK' : 'INVALID_INPUT') ||
                        (r.state === 'OK' ? !decimal(r.impact) || !nonnegative(r.impact) : r.impact !== null)) invalid();
                }
            } else {
                const width = e.type === 'two_factor' ? 2 : 1, positions = new Set(), axes = Array.from({length:width}, () => new Map());
                for (const p of e.points) {
                    if (!Array.isArray(p.indices) || p.indices.length !== width || !p.indices.every(i => count(i) && i < (width === 2 ? 11 : 41))) invalid();
                    const position = JSON.stringify(p.indices); if (positions.has(position)) invalid(); positions.add(position);
                    p.inputs.forEach((i, axis) => {
                        const values = axes[axis], previous = values.get(p.indices[axis]);
                        if (previous && ['parameter_id', 'mode', 'value', 'unit', 'final_value'].some(k => previous[k] !== i[k])) invalid();
                        values.set(p.indices[axis], i);
                    });
                }
                for (const values of axes) {
                    if (Array.from(values.keys()).some(i => i >= values.size) || !Array.from(values.values()).every(i => i.parameter_id === values.get(0).parameter_id && i.mode === values.get(0).mode)) invalid();
                }
                if (e.points.length !== axes.reduce((size, values) => size * values.size, 1) || (width === 2 && axes[0].get(0).parameter_id === axes[1].get(0).parameter_id)) invalid();
            }
        }
        const budget = raw.evaluation_budget;
        if (!keys(budget, ['reserved', 'executed', 'maximum']) || budget.maximum !== 200 || !count(budget.reserved) || budget.reserved > budget.maximum ||
            budget.reserved !== 3 + (e?.points.length || 0) || !count(budget.executed) || budget.executed < 3 + (e?.valid_count || 0) || budget.executed > budget.reserved) invalid();
        const frozen = JSON.parse(JSON.stringify(raw));
        function freeze(v) { if (v && typeof v === 'object') { Object.values(v).forEach(freeze); Object.freeze(v); } return v; }
        return {context:a, lab:freeze(frozen)};
    }
    function mount(container){
        let workspace=null,snapshot=null,active=true;
        const V=w.DashboardVisuals,doc=container.ownerDocument,N=w.DashboardNumbers;
        function el(tag,text,cls){const x=doc.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;}
        function clear(){N.closeAll(doc);workspace?.destroy();workspace=null;snapshot=null;container.replaceChildren();container.hidden=true;}
        function render(raw){clear();snapshot=raw;container.hidden=false;workspace=V.shell(container);
            const context=V.identity(raw.identity)+'؛ دوره '+raw.period.id+'؛ فرضی و غیرماندگار؛ ورودی مشترک همین درخواست';
            const sides=[{id:'baseline',label:'خط‌مبنا',result:raw.baseline},...raw.scenarios.map(s=>({...s,label:'سناریو '+s.id}))];
            for(const [field,title,unit] of [['unit_cost','مقایسه هزینه واحد','IRR/product'],['projected_cost','مقایسه هزینه دوره همین پیکربندی','IRR/period']]){
                workspace.panel(title,context,sides,[V.textCol('وضعیت',r=>r.label),V.amountCol(title,r=>r.result[field],unit)],()=>V.bars(sides,r=>r.result[field],sides.map(r=>r.label),unit,(_,i)=>['#748296','#147f86','#496bb1'][i]));
            }
            const components=Object.keys(V.FACTORS).filter(id=>!['OTHER','TECHNICAL_RECONCILIATION'].includes(id)).map(id=>({id,
                values:sides.map(s=>id==='BOM'?s.result.bom_total:s.result.breakdown.driver_components.find(r=>r.pool_id===id).per_unit_contribution)}));
            workspace.panel('اجزای هزینه واحد؛ خط‌مبنا / A / B',context+'؛ ریال / محصول؛ رنگ ثابت هر عامل، تیرگی متفاوت سناریوها.',components,
                [V.textCol('عامل',r=>V.label(r.id)),...sides.map((s,i)=>V.amountCol(s.label,r=>r.values[i],'IRR/product'))],()=>{
                    const cfg=V.bars(components,r=>r.values[0],components.map(r=>V.label(r.id)),'ریال / محصول');cfg.legend={data:sides.map(s=>s.label)};
                    cfg.series=sides.map((s,i)=>({type:'bar',name:s.label,itemStyle:{color:'#748296',opacity:[0.4,0.75,1][i]},data:components.map(r=>({value:V.numeric(r.values[i]),exactRow:r,itemStyle:{color:V.color(r.id),opacity:[0.4,0.75,1][i]}}))}));return cfg;
                });
            const bomRows=sides.flatMap(s=>s.result.breakdown.bom_components.map(r=>({...r,scenario:s.label})));
            workspace.panel('ردیف‌های مستقل BOM در مقایسه',context+'؛ ردیف‌های ماده تکراری مستقل‌اند؛ ریال / محصول.',bomRows,
                [V.textCol('سناریو',r=>r.scenario),V.textCol('هویت ردیف',r=>r.row_id),V.textCol('ماده',r=>r.material),V.amountCol('هزینه ردیف',r=>r.live_cost_in_rial,'IRR/product')],
                ()=>V.bars(bomRows,r=>r.live_cost_in_rial,bomRows.map(r=>r.scenario+' / '+r.row_id),'ریال / محصول',()=>V.color('BOM')),undefined,true);
            for(const direction of ['A_minus_baseline','B_minus_baseline','B_minus_A']){
                const c=raw.comparisons[direction],title={A_minus_baseline:'خط‌مبنا ← A',B_minus_baseline:'خط‌مبنا ← B',B_minus_A:'A ← B'}[direction];
                const rows=[{name:'اختلاف هزینه واحد',...c.unit_cost},{name:'اختلاف هزینه دوره',...c.projected_cost}];
                workspace.panel('اختلاف: '+title,context+'؛ جهت: '+direction+'؛ مخرج درصد: مقدار مرجع همین مقایسه؛ مرجع صفر: نامربوط.',rows,
                    [V.textCol('معیار',r=>r.name),V.textCol('واحد',r=>r.unit),V.amountCol('اختلاف دقیق',r=>r.amount,r=>r.unit),V.amountCol('مرجع / مخرج درصد',r=>r.reference,r=>r.unit),V.amountCol('درصد',r=>r.percentage,'percentage')],()=>null,undefined,true);
                const f=c.waterfall,bars=[{id:'REFERENCE',value:f.reference,offset:'0',size:f.reference,start:'0',end:f.reference},...f.components,f.technical_reconciliation,
                    {id:'TARGET',value:f.target,offset:'0',size:f.target,start:'0',end:f.target}];
                workspace.panel('آبشار هزینه واحد: '+title,context+'؛ ریال / محصول؛ اختلاف اجزای خروجی، نه اثر مستقل علی هر تغییر ورودی. تطبیق فنی جدا و صریح است.',bars,
                    [V.textCol('جزء',r=>r.id==='REFERENCE'?'مرجع':r.id==='TARGET'?'هدف':V.label(r.id)),V.amountCol('تغییر / هزینه',r=>r.value,'IRR/product'),V.amountCol('شروع',r=>r.start,'IRR/product'),V.amountCol('پایان',r=>r.end,'IRR/product')],()=>{
                        const cfg=V.bars(bars,r=>r.size,bars.map(r=>r.id==='REFERENCE'?'مرجع':r.id==='TARGET'?'هدف':V.label(r.id)),'ریال / محصول');
                        cfg.series=[{type:'bar',stack:'waterfall',silent:true,itemStyle:{color:'transparent'},data:bars.map(r=>V.numeric(r.offset))},
                            {type:'bar',stack:'waterfall',data:bars.map(r=>({value:V.numeric(r.size),exactRow:r,itemStyle:{color:V.color(r.id)}}))}];return cfg;
                    },undefined,true);
            }
            const experiment=raw.experiment;
            if(experiment){
                const e=experiment,parameters=new Map(raw.parameters.map(p=>[p.parameter_id,p]));
                const points=e.type==='tornado'?e.ranking.flatMap(r=>e.points.filter(p=>p.inputs[0].parameter_id===r.parameter_id)):e.points;
                const inputLabel=p=>p.inputs.map(i=>parameters.get(i.parameter_id).label+': '+N.exact(i.value,i.mode==='percent_change'?'percentage':i.unit)+' ← مقدار نهایی: '+N.exact(i.final_value,i.unit)).join(' × ');
                const axesDescription=e.type==='tornado'?'حد پایین و بالا نسبت به خط‌مبنا':points[0]?.inputs.map((i,index)=>(index===0?'محور افقی: ':'محور عمودی: ')+parameters.get(i.parameter_id).label+' ('+i.unit+')').join('؛ ');
                container.append(el('p','آزمایش با سایر ورودی‌های ثابت خط‌مبنا؛ '+e.valid_count+' نقطه معتبر و '+e.invalid_count+' نامعتبر. بازه‌ها انتخاب کاربرند؛ اهمیت جهانی یا احتمال نیستند.','dashboard-status is-neutral'));
                for(const [field,title,unit] of [['unit_cost','هزینه واحد','IRR/product'],['projected_cost','هزینه دوره','IRR/period']]){
                    workspace.panel((e.type==='tornado'?'تورنادو':e.type==='one_factor'?'منحنی پاسخ واقعی':'نقشه دو عامل')+' — '+title,context+'؛ '+unit+'؛ '+axesDescription+'؛ نقاط نامعتبر صفر نیستند.',points,
                        [V.textCol('ورودی‌های آزمایش',inputLabel),V.textCol('وضعیت',p=>p.state==='OK'?'معتبر':'خارج از دامنه / در دسترس نیست'),V.amountCol(title,p=>p[field],unit)],()=>{
                            if(e.type==='tornado'){
                                const ranked=e.ranking.filter(r=>r.state==='OK');const cfg=V.bars(ranked,r=>r.impact,ranked.map(r=>parameters.get(r.parameter_id).label),unit);
                                cfg.series=['low','high'].map(side=>({type:'bar',name:side==='low'?'حد پایین':'حد بالا',data:ranked.map(r=>{const p=points.find(p=>p.inputs[0].parameter_id===r.parameter_id&&p.side===side);return {value:V.numeric((field==='unit_cost'?p.unit_delta:p.projected_delta).amount),exactRow:p};}),itemStyle:{color:side==='low'?'#147f86':'#496bb1'}}));return cfg;
                            }
                            if(e.type==='one_factor')return {grid:{left:75,right:25,top:25,bottom:60,containLabel:true},xAxis:{type:'value',name:points[0]?.inputs[0]?.unit,nameLocation:'middle',nameGap:30},yAxis:{type:'value',name:unit==='IRR/product'?'ریال / محصول':'ریال / دوره',nameLocation:'middle',nameGap:55},series:[{type:'line',connectNulls:false,data:points.map(p=>({value:[V.numeric(p.inputs[0].final_value),p.state==='OK'?V.numeric(p[field]):null],exactRow:p}))}]};
                            const valid=points.filter(p=>p.state==='OK'),values=valid.map(p=>V.numeric(p[field]));if(!valid.length)return null;
                            const axisValues=index=>Array.from(new Map(points.map(p=>[p.indices[index],p.inputs[index].final_value])).entries()).sort((a,b)=>a[0]-b[0]).map(r=>r[1]);
                            return {grid:{left:75,right:25,bottom:100,top:25,containLabel:true},xAxis:{type:'category',data:axisValues(0),name:points[0].inputs[0].unit,nameLocation:'middle',nameGap:30},yAxis:{type:'category',data:axisValues(1),name:points[0].inputs[1].unit,nameLocation:'middle',nameGap:45},visualMap:{min:Math.min(...values),max:Math.max(...values),calculable:true,bottom:0,orient:'horizontal',inRange:{color:['#edf4f5','#147f86']}},series:[{type:'heatmap',data:valid.map(p=>({value:[p.indices[0],p.indices[1],V.numeric(p[field])],exactRow:p}))}]};
                        },undefined,true);
                }
            }
            const metadata=el('details',undefined,'sens-card');metadata.append(el('summary','زمینه مجاز و نسخه محاسبه'));
            metadata.append(el('p',V.identity(raw.identity)),el('p','دوره: '+raw.period.id+'؛ '+w.JalaliDate.formatDateOnly(raw.period.start)+' تا '+w.JalaliDate.formatDateOnly(raw.period.end)),el('p','نسخه فرمول: '+raw.formula_version));
            raw.source_lineage.forEach(r=>metadata.append(el('p',r.source+' — '+r.fingerprint)));
            container.append(metadata);
            workspace.setActive(active);
        }
        return {clear,render,destroy:clear,setActive(v){active=v;workspace?.setActive(v);}};
    }
    function csv(raw){
        adapt(raw);const rows=[];const V=w.DashboardVisuals;
        const metadata=[raw.identity.factory_id,raw.identity.category,raw.identity.subcategory,raw.identity.product,raw.period.id,raw.period.start,raw.period.end,'true','شبیه‌سازی غیرماندگار',raw.formula_version];
        function push(type,scope,metric,value,unit,direction='',reference='',state='OK'){
            rows.push([...metadata,type,scope,metric,value,unit,direction,reference,state]);
        }
        for(const s of [{id:'baseline',result:raw.baseline},...raw.scenarios]){
            for(const [metric,unit] of [['unit_cost','IRR/product'],['projected_cost','IRR/period']])push('result',s.id,metric,s.result[metric],unit);
            push('component',s.id,'BOM',s.result.bom_total,'IRR/product');s.result.breakdown.driver_components.forEach(r=>push('component',s.id,r.pool_id,r.per_unit_contribution,'IRR/product'));
            s.result.breakdown.bom_components.forEach(r=>push('BOM_row',s.id,r.row_id+' / '+r.material,r.live_cost_in_rial,'IRR/product'));
            (s.effective_overrides||[]).forEach(r=>{push('override',s.id,r.parameter_id,r.value,r.mode==='percent_change'?'percent':r.unit,r.mode);push('effective_override',s.id,r.parameter_id,r.final_value,r.unit);});
        }
        Object.entries(raw.comparisons).forEach(([direction,c])=>{
            for(const metric of ['unit_cost','projected_cost']){const d=c[metric];push('delta',direction,metric,d.amount,d.unit,d.direction,d.reference);push('percentage',direction,metric,d.percentage,'percent',d.direction,d.percentage_denominator,d.percentage_state);}
            c.waterfall.components.forEach(r=>push('waterfall',direction,r.id,r.value,'IRR/product',direction));push('reconciliation',direction,'technical',c.waterfall.reconciliation,'IRR/product',direction);
        });
        raw.experiment?.points.forEach((p,i)=>{const scope=raw.experiment.type+'/'+i;
            p.inputs.forEach(r=>push('experiment_input',scope,r.parameter_id,r.value,r.mode==='percent_change'?'percent':r.unit,r.mode,'',p.state));
            p.inputs.forEach(r=>push('experiment_final_input',scope,r.parameter_id,r.final_value,r.unit,r.mode,'',p.state));
            p.effective_inputs.forEach(r=>push('experiment_effective_input',scope,r.parameter_id,r.final_value,r.unit,r.mode,'',p.state));
            push('experiment',scope,'unit_cost',p.unit_cost,'IRR/product','','',p.state);push('experiment',scope,'projected_cost',p.projected_cost,'IRR/period','','',p.state);
            if(p.state==='OK')for(const [metric,d] of [['unit_cost',p.unit_delta],['projected_cost',p.projected_delta]]){
                push('experiment_delta',scope,metric,d.amount,d.unit,d.direction,d.reference);push('experiment_percentage',scope,metric,d.percentage,'percent',d.direction,d.percentage_denominator,d.percentage_state);
            }
        });
        const headers=['factory_id','category','subcategory','product','period_id','start','end','non_persistent','label','formula_version','row_type','scope','metric','value','unit','direction','reference','state'];
        const quote=(value,index)=>{let text=value==null?'':String(value);if(!([13,16].includes(index)&&decimal(text))&&/^[\s\u0000-\u001f]*[=+\-@]|^[\u0000-\u001f]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"';};
        return '\uFEFF'+[headers,...rows].map(r=>r.map(quote).join(',')).join('\r\n')+'\r\n';
    }
    w.DashboardLab=Object.freeze({adapt,mount,csv,oldReport});
})(window);
