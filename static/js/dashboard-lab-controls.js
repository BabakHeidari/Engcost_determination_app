(function(w){
    'use strict';
    function mount(target,onChange){
        const doc=target.ownerDocument;let parameters=[],type='none',axes=[],ranges=[];
        function node(tag,text){const e=doc.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
        function axis(initial={}){return {parameter_id:initial.parameter_id||'',mode:initial.mode||'absolute',raw:initial.raw||'',low:initial.low||'',high:initial.high||''};}
        function render(){target.replaceChildren();const details=node('details'),summary=node('summary','آزمایش‌های پیشرفته با خط‌مبنای مشترک');details.append(summary);
            details.open=type!=='none';const help=node('p','بازه‌ها و نقاط را صریح تعیین کنید. همه ورودی‌های دیگر خط‌مبنا ثابت‌اند. پیش‌نویس‌های A و B نیز در همین درخواست اجرا می‌شوند. تورنادو اهمیت عمومی یا احتمال نیست.');details.append(help);
            const label=node('label','نوع آزمایش'),select=node('select');select.id='lab-experiment-type';select.className='form-select';label.htmlFor=select.id;
            for(const [value,text] of [['none','بدون آزمایش'],['tornado','تورنادو — بازه‌های انتخابی'],['one_factor','منحنی پاسخ یک عامل'],['two_factor','نقشه دو عامل']]){const o=node('option',text);o.value=value;select.append(o);}select.value=type;
            select.addEventListener('change',()=>{type=select.value;axes=[axis(),axis()];ranges=[axis()];onChange();render();});details.append(label,select);
            const list=type==='tornado'?ranges:type==='one_factor'?axes.slice(0,1):type==='two_factor'?axes:[];
            list.forEach((a,i)=>{const row=node('fieldset');row.className='lab-axis';row.append(node('legend',(type==='tornado'?'بازه ':'عامل ')+(i+1)));
                const select=node('select');select.className='form-select';select.id='lab-parameter-'+i;const label=node('label','پارامتر مجاز و واحد منبع');label.htmlFor=select.id;
                const placeholder=node('option','پارامتر را انتخاب کنید');placeholder.value='';select.append(placeholder);
                parameters.forEach(p=>{const o=node('option',p.label+' — '+p.unit+(p.effect_state==='MATHEMATICAL_ZERO'?' — اثر پایه صفر':''));o.value=p.parameter_id;select.append(o);});select.value=a.parameter_id;
                select.addEventListener('change',()=>{a.parameter_id=select.value;onChange();});row.append(label,select);
                const mode=node('select');mode.className='form-select';mode.id='lab-mode-'+i;const ml=node('label','روش ورودی آزمایش');ml.htmlFor=mode.id;
                for(const [v,t] of [['absolute','مقدار نهایی'],['percent_change','تغییر درصدی از خط‌مبنا']]){const o=node('option',t);o.value=v;mode.append(o);}mode.value=a.mode;mode.addEventListener('change',()=>{a.mode=mode.value;onChange();});row.append(ml,mode);
                for(const field of type==='tornado'?['low','high']:['raw']){const id='lab-'+field+'-'+i,input=node(field==='raw'?'textarea':'input');input.id=id;input.className='form-control';input.dir='ltr';input.maxLength=8192;if(field!=='raw'){input.type='text';input.inputMode='decimal';}input.value=a[field];
                    const title=node('label',field==='low'?'حد پایین':field==='high'?'حد بالا':'مقادیر واقعی، هر نقطه در یک خط؛ حداکثر '+(type==='one_factor'?'۴۱':'۱۱')+' نقطه');title.htmlFor=id;
                    input.addEventListener('input',()=>{a[field]=input.value;onChange();});row.append(title,input);}
                details.append(row);
            });
            if(type==='tornado'){const add=node('button','افزودن بازه'),remove=node('button','حذف آخرین بازه');add.type=remove.type='button';add.className=remove.className='btn btn-outline-secondary btn-sm';add.disabled=ranges.length>=10;remove.disabled=ranges.length<=1;
                add.addEventListener('click',()=>{ranges.push(axis());onChange();render();});remove.addEventListener('click',()=>{ranges.pop();onChange();render();});details.append(add,remove);}
            const error=node('p');error.id='lab-experiment-error';error.role='status';details.append(error);target.append(details);
        }
        function prepare(){
            if(type==='none')return {valid:true,spec:null};
            try{
                const list=type==='tornado'?ranges:type==='one_factor'?axes.slice(0,1):axes;
                const parsed=list.map(a=>{const p=parameters.find(p=>p.parameter_id===a.parameter_id);if(!p)throw Error('هر عامل آزمایش باید از فهرست مجاز انتخاب شود.');
                    function normalize(raw){const r=w.DashboardSensitivityModel.normalizeInput(raw);if(!r.valid)throw Error('مقادیر آزمایش باید رشته اعشاری معتبر و غیرخالی باشند.');return r.value;}
                    if(type==='tornado'){const low=normalize(a.low),high=normalize(a.high);if(w.DashboardNumbers.compare(low,high)>0)throw Error('حد پایین نباید از حد بالا بیشتر باشد.');return {parameter_id:a.parameter_id,mode:a.mode,low,high};}
                    const values=a.raw.split(/\r?\n/).map(normalize);if(values.length>(type==='one_factor'?41:11))throw Error('تعداد نقاط از سقف آزمایش بیشتر است.');return {parameter_id:a.parameter_id,mode:a.mode,values};
                });
                if(new Set(parsed.map(a=>a.parameter_id)).size!==parsed.length)throw Error('دو عامل یکسان یا تکراری نمی‌توانند مستقل آزمایش شوند.');
                return {valid:true,spec:type==='tornado'?{type,ranges:parsed}:{type,axes:parsed}};
            }catch(e){return {valid:false,error:e.message};}
        }
        return {prepare,update(registry){parameters=registry;for(const a of [...axes,...ranges])if(!registry.some(p=>p.parameter_id===a.parameter_id))a.parameter_id='';render();},
            reset(){type='none';axes=[axis(),axis()];ranges=[axis()];render();},clear(){parameters=[];type='none';axes=[];ranges=[];target.replaceChildren();},showError(text){const e=target.querySelector('#lab-experiment-error');if(e)e.textContent=text||'';}};
    }
    w.DashboardLabControls=Object.freeze({mount});
})(window);
