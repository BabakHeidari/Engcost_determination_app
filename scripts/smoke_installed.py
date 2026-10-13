"""Exercise the actual frozen/installed executable with isolated user data.

The harness uses Python/Playwright; the launched application sees only OS tools,
no PYTHONPATH, developer packages, Git, Node or browser cache. Fixture generation
is deliberate test preparation, never a customer startup operation.
"""
import argparse
from http.cookiejar import CookieJar
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import ProxyHandler, Request, HTTPCookieProcessor, build_opener

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'Native-Fixture-Password-123'


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and p.suffix != '.lock'}


class Native:
    def __init__(self, executable, config, cwd, env):
        self.executable, self.config, self.cwd, self.env = executable, config, cwd, env
        self.http = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        self.process = None

    def launch(self):
        started = time.perf_counter()
        self.process = subprocess.Popen([str(self.executable), '--config-root', str(self.config), '--no-browser'],
                                        cwd=self.cwd, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                self.record = json.loads((self.config / 'instance.json').read_text())
                self.base = 'http://127.0.0.1:' + str(self.record['port'])
                status, data = self.call('/_local/health', headers={'X-Engcost-Capability': self.record['token']})
                if status == 200 and data['instance_id'] == self.record['instance_id']:
                    break
            except (OSError, ValueError, KeyError):
                if self.process.poll() is not None:
                    raise RuntimeError('Frozen executable exited before readiness')
                time.sleep(0.025)
        else:
            raise RuntimeError('Frozen executable readiness timed out')
        elapsed = time.perf_counter() - started
        assert self.call('/_local/authorize', {'capability': self.record['token']}, json_body=True)[0] == 200
        return elapsed

    def call(self, path, data=None, *, json_body=False, headers=None, method=None, raw_body=False):
        headers = {**(headers or {})}
        if data is not None:
            headers['Origin'] = self.base
            headers['Content-Type'] = 'application/json' if json_body else 'application/x-www-form-urlencoded'
            data = json.dumps(data).encode() if json_body else urlencode(data).encode()
        req = Request(self.base + quote(path, safe='/?&=%:+-'), data=data, headers=headers, method=method)
        try:
            response = self.http.open(req, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            kind = response.headers.get('Content-Type', '')
            body = raw if raw_body else json.loads(raw) if 'application/json' in kind else raw.decode('utf-8', errors='replace')
            return response.status, body

    def csrf(self):
        status, body = self.call('/_local/panel'); assert status == 200
        return re.search(r'name="csrf" value="([^"]+)"', body).group(1)

    def wait_business(self):
        started = time.perf_counter(); deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            status, data = self.call('/_local/status')
            if data['state'] == 'ready':
                assert self.call('/login')[0] == 200
                return time.perf_counter() - started
            assert data['state'] != 'error', 'Business initialization failed'
            time.sleep(0.025)
        raise RuntimeError('Business readiness timeout')

    def stop(self):
        if self.process and self.process.poll() is None:
            assert self.call('/_local/stop', {'csrf': self.csrf()})[0] == 200
            self.process.wait(timeout=60)
            assert self.process.returncode == 0

    def login(self):
        status, body = self.call('/login', {'username':'native-owner', 'password':PASSWORD})
        assert status == 200 and 'خوش آمدید' in body


def fixture(root):
    # Import services only in the harness, never the operational application.
    sys.path.insert(0, str(ROOT))
    from scripts.dashboard_benchmark_fixture import install_fixture, FACTORY, OPERATIONAL
    from utils.auth import set_password
    from utils.factory_configuration import POOL_IDS, ensure_factory_configuration_v2
    from utils.profile_store import ProfileDataStore
    f = install_fixture(root, configurations=200, selected_bom_rows=500)
    (root / 'instance').mkdir()
    shutil.move(f.profiles, root / 'instance/app_data.json')
    shutil.move(f.bindings, root / 'instance/costing_period_bindings.json')
    store = ProfileDataStore(root / 'instance/app_data.json')
    user = {'username':'native-owner', 'email':'native@example.test', 'full_name':'مدیر آزمایشی',
            'system_role':'IT_ADMIN', 'is_active':True, 'must_change_password':False}
    set_password(user, PASSWORD); store.create_user(user)
    config = f.factory / 'configuration'
    for source, target in [('category_weights.json','category_weights.json'),
                           ('production_prediction.json','ProductionPrediction.json')]:
        shutil.copyfile(config / source, f.factory / target)
    for pool in POOL_IDS:
        shutil.copyfile(config / 'cost_pools' / (pool + '.json'), f.factory / ('Factory_Data_' + pool + '.json'))
    shutil.rmtree(config)
    ensure_factory_configuration_v2(FACTORY, OPERATIONAL, data_root=f.data)
    for p in f.factory.glob('Factory_Data_*.json'): p.unlink()
    (f.factory / 'category_weights.json').unlink(); (f.factory / 'ProductionPrediction.json').unlink()
    for p in [f.data / 'Overall/material_costs.json', *f.factory.glob('category/sub/*.json')]:
        document = json.loads(p.read_text()); document['_order'] = list(document['data'])
        p.write_text(json.dumps(document))
    for p in (ROOT / 'packaging/blank/Overall').glob('*.json'):
        if not (f.data / 'Overall' / p.name).exists():
            shutil.copyfile(p, f.data / 'Overall' / p.name)
    return f.selection


def browser_evidence(native, output, chromium):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=str(chromium) if chromium else None, headless=True,
                                          args=['--no-sandbox','--disable-dev-shm-usage','--disable-background-networking'])
        results = []
        for width in (1440, 390):
            context = browser.new_context(viewport={'width':width, 'height':1000}, timezone_id='Asia/Tehran', accept_downloads=True)
            external, failures, errors = [], [], []
            def network(route):
                if not route.request.url.startswith(native.base + '/'):
                    external.append(route.request.url); route.abort()
                else:
                    route.continue_()
            context.route('**/*', network)
            page = context.new_page();page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('response', lambda response: failures.append(response.url) if response.status >= 400 else None)
            usable_started=time.perf_counter()
            page.goto(native.base + '/_local/#' + native.record['token'], wait_until='networkidle')
            page.wait_for_url('**/login')
            usable=time.perf_counter()-usable_started
            page.screenshot(path=str(output / f'login-{width}.png'), full_page=True)
            page.locator('[name=username]').fill('native-owner');page.locator('[name=password]').fill(PASSWORD)
            page.locator('form button').click();page.wait_for_load_state('networkidle')
            for name, path in [('desk','/workdesk'),('profile','/profile/profile'),('product','/product/production_selection'),
                               ('factory','/factory_parameters/'),('general','/general_parameters/'),
                               ('cost','/cost/cost_calculation'),('dashboard','/dashboard')]:
                response = page.goto(native.base + path, wait_until='networkidle')
                assert response.status == 200, (name, response.status)
                page.screenshot(path=str(output / f'{name}-{width}.png'), full_page=True)
                if not page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'):
                    (output/f'overflow-{name}-{width}.json').write_text(json.dumps(page.evaluate('''() => Array.from(document.querySelectorAll('*')).filter(e=>e.getBoundingClientRect().right>innerWidth+2 && getComputedStyle(e).display!=='none').slice(-20).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right}))'''),indent=2))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), name
                assert page.evaluate('document.fonts.check("14px IRANSansX")')
                if name == 'dashboard':
                    assert page.evaluate('echarts.version') == '5.6.0'
                    page.select_option('#factorySelect','benchmark-factory')
                    for selector in ['#categorySelect','#subcategorySelect','#productSelect']:
                        page.wait_for_function('(s)=>!document.querySelector(s).disabled',arg=selector)
                        page.select_option(selector,'__ALL__')
                    page.wait_for_function("!document.querySelector('#analyzeBtn').disabled")
                    page.locator('#analyzeBtn').click();page.locator('#costDashboard').wait_for(state='visible')
                    with page.expect_download() as download:
                        page.locator('#downloadCsvBtn').click()
                    download.value.save_as(str(output/f'cost-{width}.csv'))
                    # Exercise the shipped chart failure fallback on the installed app.
                    page.evaluate('() => { window.echarts.init = () => { throw new Error("fixture chart failure"); }; }')
                    page.locator('#analyzeBtn').click();page.wait_for_timeout(500)
                    assert page.locator('#downloadCsvBtn').is_enabled()
                page.screenshot(path=str(output / f'{name}-{width}.png'), full_page=True)
            assert not external and not failures and not errors, (external, failures, errors)
            results.append({'width':width,'first_usable_navigation_seconds':usable,'external_requests':len(external),'failed_requests':len(failures),'javascript_errors':len(errors)})
            context.close()
        browser.close()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--chromium', type=Path)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--network-block-library', type=Path, help='Linux native connect-blocking validation library')
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True);output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    env = {key:value for key,value in os.environ.items() if key in {
        'SystemRoot','WINDIR','LOCALAPPDATA','APPDATA','USERPROFILE','USERDOMAIN','USERNAME','TEMP','TMP',
        'LANG','LC_ALL','DISPLAY','XAUTHORITY','LD_PRELOAD','ENGCOST_NETWORK_REPORT'}}
    env['PATH'] = str(Path(env['SystemRoot']) / 'System32') if os.name == 'nt' else '/nonexistent'
    if args.network_block_library:
        env['LD_PRELOAD'] = str(args.network_block_library.resolve(strict=True))
    summary = {'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
               'host':platform.platform(), 'isolated_runtime_path':True, 'native_installer_environment':'see CI job/validation report'}
    with tempfile.TemporaryDirectory(prefix='Engcost آزمون با فاصله ') as folder:
        root=Path(folder);cwd=root/'unrelated working directory';cwd.mkdir()
        native=Native(executable,root/'تنظیمات',cwd,env)
        occupied=socket.socket();occupied.bind(('127.0.0.1',5000));occupied.listen()
        try:
            summary['first_setup_server_ready_seconds']=native.launch()
            assert native.record['port'] != 5000
            assert native.call('/_local/admin', {'csrf':native.csrf(), 'username':'bad'})[0] == 409
            workspace=root/'فضای کاری'
            assert native.call('/_local/workspace', {'csrf':native.csrf(),'workspace':str(workspace),'mode':'fresh'})[0] == 200
            assert native.call('/_local/status')[1]['state']=='admin'
            if args.browser:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser=p.chromium.launch(executable_path=str(args.chromium) if args.chromium else None, headless=True,args=['--no-sandbox'])
                    page=browser.new_page();page.goto(native.base+'/_local/#'+native.record['token']);page.wait_for_url('**/panel')
                    page.screenshot(path=str(output/'setup-admin.png'),full_page=True);browser.close()
            values={'csrf':native.csrf(),'username':'native-owner','full_name':'مدیر آزمایشی','email':'native@example.test',
                    'password':PASSWORD,'confirmation':PASSWORD}
            assert native.call('/_local/admin',values)[0]==200
            summary['setup_to_business_ready_seconds']=native.wait_business();native.login()
            assert native.call('/_local/admin',values)[0]==409
            assert native.call('/api/profile/factories', {'code':'FRESH','name':'کارخانه تازه','location':'تهران'}, json_body=True)[0]==201
            assert native.call('/add_category', {'factory':'FRESH','category_name':'دسته'}, json_body=True)[0]==200
            assert native.call('/add_subcategory', {'factory':'FRESH','category':'دسته','subcategory_name':'زیر دسته'},json_body=True)[0]==200
            payload={'factory':'FRESH','category':'دسته','subcategory':'زیر دسته','product_name':'محصول','capacity':50}
            assert native.call('/add_product',payload,json_body=True)[0]==200
            bom=workspace/'Data/Factories/FRESH/دسته/زیر دسته/محصول.json';before=bom.read_bytes()
            assert native.call('/add_product',payload,json_body=True)[0]==409 and bom.read_bytes()==before
            material={'material':'fixture-lead','unit':'kg','currency':'IRR - Iranian Rial','cost_per_unit_in_currency':100}
            assert native.call('/save_materials',{'added':[material],'edited':[],'deleted':[],
                               'last_modification_date':'2026-10-13T00:00:00Z'},json_body=True)[0]==200
            assert json.loads((workspace/'Data/Overall/material_costs.json').read_text())['data']['material']==['fixture-lead']
            assert native.call('/product/محصول',{'factory':'FRESH','category':'دسته','subcategory':'زیر دسته'})[0]==200
            live={'_order':['materials','usage','lost_percentage','recycability_percentage'],
                  'data':{'materials':['fixture-lead'],'usage':[1],'lost_percentage':[0],'recycability_percentage':[0]}}
            assert native.call('/save_bom',live,json_body=True)[0]==200
            import io,zipfile
            status,excel=native.call('/api/profile/export.xlsx',raw_body=True)
            assert status==200 and 'xl/workbook.xml' in zipfile.ZipFile(io.BytesIO(excel)).namelist()
            for file,endpoint in [('category_weights.json','category-weights'),('production_prediction.json','production-prediction')]:
                document=json.loads((workspace/'Data/Factories/FRESH/configuration'/file).read_text())
                document['data']={'category':['دسته'],'selling_share_of_category':[50]} if endpoint=='category-weights' else {'Product Name':['محصول'],'Predicted Production':[10]}
                assert native.call('/factory_parameters/FRESH/'+endpoint,document,json_body=True,method='PUT')[0]==200
            for pool in sorted((workspace/'Data/Factories/FRESH/configuration/cost_pools').glob('*.json')):
                document={'data':{'id':['fixture-item'],'subject':['هزینه آزمایشی'],'cost':[100]}}
                assert native.call('/factory_parameters/FRESH/cost-pools/'+pool.stem,document,json_body=True,method='PUT')[0]==200
            status,cost=native.call('/cost/get_cost',{'Factory':'FRESH','Category':'دسته','Subcategory':'زیر دسته','Product_Name':'محصول'},json_body=True)
            assert status==200 and cost['state'] in {'OK','MISSING_INPUT','AMBIGUOUS_INPUT','INVALID_INPUT'}
            secret=json.loads((workspace/'instance/standalone.json').read_text())['secret']
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=4) as clicks:
                results=list(clicks.map(lambda _:subprocess.run([str(executable),'--config-root',str(native.config),'--no-browser'],cwd=cwd,env=env,timeout=40).returncode, range(4)))
                assert results==[0]*4
            native.stop();occupied.close()
            warm=[];business=[]
            for _ in range(5):
                warm.append(native.launch());business.append(native.wait_business());native.stop()
                assert json.loads((workspace/'instance/standalone.json').read_text())['secret']==secret
            summary['restart_server_ready_seconds']=warm;summary['restart_business_additional_seconds']=business
            # A stale record must not redirect to a port or keep a nonexistent owner alive.
            (native.config/'instance.json').write_text(json.dumps({'application':'unrelated','port':5000}))
            native.launch();native.wait_business();native.stop()
            existing=root/'Existing داده';selection=fixture(existing)
            baseline=snapshot(existing)
            native.launch();native.wait_business()
            assert native.call('/_local/workspace', {'csrf':native.csrf(),'workspace':str(existing),'mode':'existing'})[0] == 409
            native.stop()
            # New selection controller; existing authentication is retained.
            native=Native(executable,root/'تنظیمات دوم',cwd,env);native.launch()
            assert native.call('/_local/workspace', {'csrf':native.csrf(),'workspace':str(existing),'mode':'existing'})[0]==200
            native.wait_business();native.login()
            assert native.call('/_local/admin',values | {'csrf':native.csrf()})[0]==409
            assert all(snapshot(existing).get(key)==value for key,value in baseline.items() if key.startswith('Data/'))
            assert json.loads((existing/'instance/standalone.json').read_text())['secret'] != secret
            times={}
            for name,path,body in [('cost-analysis','/api/cost_analysis?'+urlencode(selection),None),
                                   ('A-B','/api/dashboard/sensitivity/visual-analysis',selection|{'scenarios':[{'id':'A','overrides':[]},{'id':'B','overrides':[]}], 'experiment':None})]:
                samples=[]
                before=snapshot(existing/'Data')
                for _ in range(10):
                    started=time.perf_counter();status,data=native.call(path,body,json_body=True)
                    assert status==200, (name,status,data)
                    samples.append(time.perf_counter()-started)
                assert snapshot(existing/'Data')==before
                times[name]=samples
            params=native.call('/api/dashboard/sensitivity/parameters?'+urlencode(selection))[1]['parameters']
            ids=[next(p['parameter_id'] for p in params if p['parameter_id'].startswith(prefix)) for prefix in ['prediction:','category_share:']]
            matrix=selection|{'scenarios':[{'id':'A','overrides':[]},{'id':'B','overrides':[]}], 'experiment':{'type':'two_factor','axes':[
                {'parameter_id':ids[0],'mode':'absolute','values':['10','20']}, {'parameter_id':ids[1],'mode':'absolute','values':['25','50']}]}}
            before=snapshot(existing/'Data');samples=[]
            for _ in range(10):
                started=time.perf_counter();status,data=native.call('/api/dashboard/sensitivity/visual-analysis',matrix,json_body=True)
                assert status==200 and len(data['experiment']['points'])==4;samples.append(time.perf_counter()-started)
            assert snapshot(existing/'Data')==before;times['matrix']=samples
            summary['requests_seconds']=times
            if args.browser: summary['browser']=browser_evidence(native,output,args.chromium)
            native.stop()
            # Actual frozen recovery path: corrupt stores remain byte-for-byte.
            corrupt=existing/'instance/app_data.json';corrupt.write_text('{corrupt-fixture')
            before=corrupt.read_bytes();native.launch()
            deadline=time.monotonic()+20
            while native.call('/_local/status')[1]['state']=='preparing' and time.monotonic()<deadline:time.sleep(.025)
            assert native.call('/_local/status')[1]['state']=='select'
            assert corrupt.read_bytes()==before;native.stop()
            # Resume an intentional incomplete fresh installation, without resetting it.
            empty_config=root/'resume config';empty_workspace=root/'resume فضای کاری'
            native=Native(executable,empty_config,cwd,env);native.launch()
            assert native.call('/_local/workspace',{'csrf':native.csrf(),'workspace':str(empty_workspace),'mode':'fresh'})[0]==200
            native.stop();native.launch()
            deadline=time.monotonic()+20
            while native.call('/_local/status')[1]['state']=='preparing' and time.monotonic()<deadline:time.sleep(.025)
            assert native.call('/_local/status')[1]['state']=='admin';native.stop()
            summary['checks']='fresh setup/login, V2-only factory/category/subcategory/product/retry, general material/BOM/financial edits, costing and Profile Excel, simultaneous clicks, occupied port, stale record, unrelated CWD, Persian paths, existing workspace/auth preservation, secret persistence/uniqueness, setup disabled, corrupt/incomplete recovery, restart/stop, real Cost Analysis/A-B/matrix, analytical data hashes, local fonts/charts/CSV and chart fallback'
        finally:
            occupied.close()
            if native.process and native.process.poll() is None:
                native.process.terminate();native.process.wait(timeout=60)
    (output/'native-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
