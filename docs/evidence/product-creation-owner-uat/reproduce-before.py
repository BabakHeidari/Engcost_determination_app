# Run against bc9f3f10f7fdcfcd7ca4ccb0a13289d1a3af4cb7 before applying this fix.
import json, tempfile
from pathlib import Path
from flask import Flask
from utils.profile_store import ProfileDataStore
from modules.product import routes as r
from utils import updaters

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder); data=root/'Data'; factory=data/'Factories'/'op'; factory.mkdir(parents=True)
    (data/'Overall').mkdir(); (data/'Overall'/'sample_product.json').write_text('{"_order":[],"data":{}}')
    store=ProfileDataStore(root/'profiles.json'); store.initialize({})
    store.create_factory({'id':'canonical','code':'F','name':'کارخانه','operational_key':'op','is_active':True})
    store.create_user({'id':'writer','username':'writer','email':'w@example.test','full_name':'کاربر','system_role':'USER','job_title':'کاربر','is_active':True,'must_change_password':False,'password_hash':'unused','password_scheme':'werkzeug','revision':1,'access_grants':[{'scope_type':'FACTORY','factory_id':'canonical','module':'product','permissions':['READ','WRITE']}]})
    app=Flask(__name__); app.config.update(APP_DATA_FILE=str(store.path) if hasattr(store,'path') else str(root/'profiles.json'),SECRET_KEY='fixture'); app.register_blueprint(r.product_bp)
    r.parent_path=updaters.parent_path=data
    client=app.test_client()
    with client.session_transaction() as session: session['user_id']='writer'
    steps=[('/add_category',{'factory':'canonical','category_name':'دسته'}),('/add_subcategory',{'factory':'canonical','category':'دسته','subcategory_name':'زیر دسته'}),('/add_product',{'factory':'canonical','category':'دسته','subcategory':'زیر دسته','product_name':'محصول','capacity':42})]
    for url,payload in steps:
        response=client.post(url,json=payload); print('Ubuntu',url,response.status_code,response.get_json())
    print('Canonical directories exist:', (factory/'دسته'/'زیر دسته').exists())
    # Isolate the confirmed Windows-tail failure on Ubuntu by replacing only
    # legacy backslash helpers with their equivalent Windows filesystem result.
    r.category_adder=lambda f,c:(data/'Factories'/f/c).mkdir()
    r.subcategory_adder=lambda f,c,s:(data/'Factories'/f/c/s).mkdir()
    r.product_adder=lambda p,f,c,s:(data/'Factories'/f/c/s/f'{p}.json').write_bytes((data/'Overall'/'sample_product.json').read_bytes())
    r.capacity_writer=lambda p,f,c,s,v:(data/'Factories'/f/c/s/f'{p}_meta.json').write_text(json.dumps({'capacity':v}))
    for url,payload in steps:
        response=client.post(url,json=payload); print('Windows helper semantics',url,response.status_code,response.get_json())
    print('BOM and capacity survive failed response:', sorted(p.name for p in (factory/'دسته'/'زیر دسته').iterdir()))
