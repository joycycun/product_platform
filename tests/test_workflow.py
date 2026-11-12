import os, tempfile, time, json
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='foundry-tests-')
os.environ['BOOTSTRAP_PASSWORD']='test-password-123'
os.environ['COOKIE_SECURE']='false'  # TestClient uses HTTP; production HTTPS cookie policy is unchanged.
from fastapi.testclient import TestClient
from backend.main import app
from backend import db

def tone_body(baseline_id):
    return dict(baseline_id=baseline_id,target_users='学校用户',core_value='可靠广播',positioning='标准价位',design_principles='清晰易用',differentiation='快速部署',constraints='兼容现有设备',out_of_scope='不做监控',rationale='客户反馈与公司能力',confirmed=True,generation_mode='demo')

def test_complete_workflow():
    with TestClient(app) as c:
        def post(url,data=None,code=200):
            r=c.post(url,json={} if data is None else data)
            assert r.status_code==code,r.text
            return r.json()
        def job(x):
            for _ in range(240):
                r=c.get('/api/jobs/'+x['job_id']).json()
                if r['status']=='completed':return r['result']
                assert r['status']!='failed',r
                time.sleep(.1)
            assert False,'job timeout'
        post('/api/auth/login',{'name':'admin','password':'test-password-123'})
        pid=post('/api/projects',{'name':'测试学校终端','direction':'学校走廊带屏 SIP 终端'})['id']
        root='/api/projects/'+pid
        profile=post(root+'/profiles',{'industry':'教育'})
        comp=job(post(root+'/search',{'mode':'demo'}))[0]
        base=post(root+'/baselines',{'competitor_id':comp['id'],'reason':'演示业务链，事实待核实'})
        post(root+'/needs/generate',{'mode':'demo'},422)
        tone=post(root+'/product-tones',tone_body(base['id']))
        initial_needs=job(tone['next_job'])
        assert initial_needs and all(n['data']['feedback_ids']==[] for n in initial_needs)
        assert all(n['data']['allocation']['software'] and n['data']['allocation']['hardware'] for n in initial_needs)
        assert post(root+'/needs/ensure')['status']=='ready'
        post(root+'/mock-sales')
        post(root+'/mock-sales')
        assert len(c.get(root).json()['matches'])==1
        feedback=post(root+'/feedback',{'quote':'紧急广播时，希望警示灯更醒目','source':'测试访谈（非真实）','provenance':'demo'})
        need=job(feedback['next_job'])[0]
        data={k:need['data'][k] for k in ('title','description','feedback_ids','allocation','status')}
        data['status']='confirmed'
        confirmed=post(root+'/needs/'+need['id'],data)
        proposals=job(confirmed['next_job'])
        assert len(proposals)==2
        selected=proposals[1]
        post(root+'/reviews',{'target_id':selected['id'],'discipline':'工程','conclusion':'通过','comment':'测试方案通过，工程文件另行评审'})
        selection=post(root+'/proposals/'+selected['id']+'/select')
        candidate=job(selection['next_job'])
        assert '"profile_id"' not in candidate['data']['content']
        assert '"competitor_id"' not in candidate['data']['content']
        assert '目标客户画像' in candidate['data']['content']
        prd=post(root+'/prd',{'candidate_id':candidate['id'],'content':candidate['data']['content']+'\n人工优先内容','note':'人工校订'})
        doc=c.get(root+'/prd/'+prd['id']+'/docx')
        assert doc.status_code==200 and doc.content[:2]==b'PK'
        imported=c.post(root+'/prd/import',files={'file':('PRD.docx',doc.content,'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
        assert imported.status_code==200,imported.text
        assert '人工优先内容' in imported.json()['data']['content']
        diff=c.get(root+'/prd/'+candidate['id']+'/diff').json()
        assert '-人工优先内容' in diff['diff']
        post(root+'/prd',{'content':'冲突覆盖','note':'测试冲突'},409)
        assert db.latest(pid,'prd')['id']==prd['id']
        meta=dict(purpose='design',note='专业工具设计首版',need_ids=[confirmed['id']],proposal_id=selected['id'],hardware_feature_indexes=[0],prd_id=prd['id'])
        uploaded=c.post(root+'/files',files={'file':('terminal.step',b'ISO-10303-21; test original')},data={'metadata':json.dumps(meta)})
        assert uploaded.status_code==200,uploaded.text
        first=uploaded.json();rid=first['record']['id']
        assert first['record']['data']['preview_status']=='unsupported_download_original'
        post(root+'/reviews',{'target_id':rid,'discipline':'结构','conclusion':'通过','comment':'首版文件评审通过'})
        new=c.post(root+'/files',files={'file':('terminal.step',b'ISO-10303-21; revised')},data={'metadata':json.dumps(meta|{'previous_id':rid,'note':'设计人员调整尺寸'})})
        assert new.status_code==200,new.text
        versions=c.get(root+'/files/'+rid+'/versions').json()
        assert [v['data']['version'] for v in versions]==[1,2]
        assert versions[0]['reviews'] and not versions[1]['reviews']
        assert c.get(first['url']).content==b'ISO-10303-21; test original'
        assert c.post(root+'/files',files={'file':('terminal.step',b'conflict')},data={'metadata':json.dumps(meta|{'previous_id':rid})}).status_code==409
        changed_tone=post(root+'/product-tones',tone_body(base['id'])|{'core_value':'更清晰的广播体验'})
        assert changed_tone['data']['previous_id']==tone['id']
        post(root+'/proposals/'+selected['id']+'/select',code=422)
        post(root+'/prd/generate',{'mode':'demo'},422)
        assert db.record(prd['id'],pid)['data']['tone_id']==tone['id']
        post(root+'/baselines',{'competitor_id':comp['id'],'reason':'更新参考资料'})
        assert db.record(prd['id'],pid)['data']['baseline_id']==base['id']
        post(root+'/needs/generate',{'mode':'demo'},422)
        files=[first,new.json()]
        for f in files:assert c.get(f['url']).status_code==200
        with db.connect() as conn:
            row=conn.execute('SELECT path FROM files WHERE id=?',(files[0]['id'],)).fetchone()
            assert not row['path'].startswith('/')
            conn.execute('UPDATE files SET path=? WHERE id=?',('/previous-host/data/'+row['path'],files[0]['id']))
        assert c.get(files[0]['url']).status_code==200
        post(root+'/members',{'name':'viewer','password':'viewer-password','role':'viewer'})
        with TestClient(app) as other:
            other.post('/api/auth/login',json={'name':'viewer','password':'viewer-password'})
            assert other.post(root+'/profiles',json={}).status_code==403
            assert other.get(files[0]['url']).status_code==200
        with TestClient(app) as anonymous:
            assert anonymous.get(root).status_code==401
            assert anonymous.get(files[0]['url']).status_code==401

def test_missing_configuration(monkeypatch):
    from backend import adapters
    monkeypatch.delenv('TAVILY_API_KEY',raising=False)
    monkeypatch.delenv('MODEL_API_KEY',raising=False)
    import pytest
    with pytest.raises(ValueError,match='未配置'):adapters.search('SIP terminal','live')
    assert adapters.config()['model']=='unconfigured'

def test_existing_confirmed_tone_without_needs_is_recovered():
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        pid=c.post('/api/projects',json={'name':'旧项目自动补拆解','direction':'学校音频广播设备'}).json()['id'];root='/api/projects/'+pid
        comp=c.post(root+'/competitors',json={'brand':'演示品牌','model':'DEMO-1000','provenance':'demo'}).json()
        base=c.post(root+'/baselines',json={'competitor_id':comp['id'],'reason':'旧版项目基准'}).json()
        tone=db.add(pid,'product_tone',tone_body(base['id'])|{'status':'confirmed'},'admin')
        scheduled=c.post(root+'/needs/ensure',json={}).json()
        for _ in range(100):
            task=c.get('/api/jobs/'+scheduled['job_id']).json()
            if task['status'] in ('completed','failed'):break
            time.sleep(.05)
        assert task['status']=='completed',task
        assert all(n['data']['tone_id']==tone['id'] for n in task['result'])
        assert c.post(root+'/needs/ensure',json={}).json()['status']=='ready'

def test_tone_deduplication_and_archived_need_versions():
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        pid=c.post('/api/projects',json={'name':'版本移除测试','direction':'学校音频广播设备'}).json()['id'];root='/api/projects/'+pid
        comp=c.post(root+'/competitors',json={'brand':'演示品牌','model':'DEMO-1000','provenance':'demo'}).json()
        base=c.post(root+'/baselines',json={'competitor_id':comp['id'],'reason':'测试基准版本'}).json()
        base_again=c.post(root+'/baselines',json={'competitor_id':comp['id'],'reason':'测试基准版本'}).json()
        assert base_again['id']==base['id'] and base_again['unchanged'] is True
        first=c.post(root+'/product-tones',json=tone_body(base['id'])).json()
        same=c.post(root+'/product-tones',json=tone_body(base['id'])).json()
        assert same['id']==first['id'] and same['unchanged'] is True
        newer=c.post(root+'/product-tones',json=tone_body(base['id'])|{'core_value':'清晰可靠的广播'}).json()
        need_data={'title':'人工补充需求','description':'产品经理确认的紧急广播需求','allocation':{'software':'广播配置与状态显示','hardware':'警示灯与扬声器','interface':'广播控制接口','acceptance':'现场播放与告警验收'}}
        need=c.post(root+'/needs',json=need_data).json()
        assert need['data']['provenance']=='manual' and need['data']['tone_id']==newer['id']
        revised=c.post(root+'/needs/'+need['id'],json=need_data|{'status':'pending'}).json()
        assert revised['data']['supersedes']==need['id']
        assert c.delete(root+'/needs/'+revised['id']).status_code==200
        visible=c.get(root).json()['records']
        assert not any(r['id'] in (need['id'],revised['id']) for r in visible)
        assert db.record(need['id'],pid,'need')['id']==need['id']  # Historical references remain resolvable.
        assert c.delete(root+'/product-tones/'+newer['id']).status_code==200
        assert db.latest(pid,'product_tone')['id']==first['id']
        assert c.delete(root+'/product-tones/'+newer['id']).status_code==422
        assert c.delete(root+'/baselines/'+base['id']).status_code==200
        assert db.latest(pid,'baseline') is None

def test_removed_last_need_is_not_automatically_recreated():
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        pid=c.post('/api/projects',json={'name':'需求删除保留测试','direction':'学校广播设备'}).json()['id'];root='/api/projects/'+pid
        comp=c.post(root+'/competitors',json={'brand':'测试品牌','model':'T-100','provenance':'demo'}).json()
        base=c.post(root+'/baselines',json={'competitor_id':comp['id'],'reason':'测试产品基准'}).json()
        db.add(pid,'product_tone',tone_body(base['id'])|{'status':'confirmed'},'admin')
        need_data={'title':'人工需求','description':'现场可靠广播','allocation':{'software':'配置广播','hardware':'安装扬声器','interface':'状态上报','acceptance':'现场声音验收'}}
        need=c.post(root+'/needs',json=need_data).json()
        assert c.delete(root+'/needs/'+need['id']).status_code==200
        assert c.post(root+'/needs/ensure',json={}).json()['status']=='empty'

def test_authorized_project_translation_uses_cache(monkeypatch):
    from backend import adapters
    calls=[]
    monkeypatch.setattr(adapters,'config',lambda:{'model':'ready','model_data_allowed':True})
    def fake_translate(task,context,schema):
        calls.append(context['texts'])
        return {'translations':['English result '+str(i) for i,_ in enumerate(context['texts'])]}
    monkeypatch.setattr(adapters,'model_json',fake_translate)
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        pid=c.post('/api/projects',json={'name':'翻译权限测试','direction':'学校广播设备'}).json()['id']
        url='/api/projects/'+pid+'/translate'
        first=c.post(url,json={'texts':['学校广播需求','扬声器功能']})
        assert first.status_code==200 and first.json()['translations']['学校广播需求']=='English result 0'
        assert c.post(url,json={'texts':['学校广播需求','扬声器功能']}).json()==first.json()
        assert calls==[['学校广播需求','扬声器功能']]
        assert c.post('/api/projects/no-such-project/translate',json={'texts':['私有资料']}).status_code==404
        other=c.post('/api/projects',json={'name':'未授权翻译项目','direction':'企业广播设备'}).json()['id']
        c.post('/api/projects/'+pid+'/members',json={'name':'translation-viewer','password':'translation-viewer-password','role':'viewer'})
        with TestClient(app) as viewer:
            viewer.post('/api/auth/login',json={'name':'translation-viewer','password':'translation-viewer-password'})
            assert viewer.post('/api/projects/'+other+'/translate',json={'texts':['私有项目资料']}).status_code==404
    with TestClient(app) as anonymous:
        assert anonymous.post(url,json={'texts':['学校广播需求']}).status_code==401

def test_audio_search_accepts_official_model_pages_only():
    from backend.adapters import official_audio_product
    algo={'title':'8180 SIP Audio Alerter | Algo','url':'https://www.algosolutions.com/product/8180-sip-audio-alerter','content':'SIP speaker'}
    zenitel={'title':'ZIPS-H | IP Horn Speaker','url':'https://www.zenitel.com/product/zips-h-ip-horn-speaker','content':'IP speaker'}
    article={'title':'Best IP speakers 2026','url':'https://example.com/blog/best-ip-speakers-2026','content':'Algo 8180'}
    category={'title':'Network speakers | Axis','url':'https://www.axis.com/products/network-speakers','content':'Audio product category'}
    support={'title':'AXIS C7050 Network Speaker','url':'https://www.axis.com/products/axis-c7050-mk-ii/support','content':'speaker support'}
    assert official_audio_product(algo)['model']=='8180'
    assert official_audio_product(zenitel)['model']=='ZIPS-H'
    assert official_audio_product(article) is None
    assert official_audio_product(category) is None
    assert official_audio_product(support) is None

def test_select_premier_analyzes_product_page(monkeypatch):
    from backend import adapters
    page='8180 IP Audio Alerter is a SIP speaker for paging. ' * 8
    monkeypatch.setattr(adapters,'extract_product_page',lambda url:page)
    def analysis(task,context,schema):
        assert 'source_text' in context and context['source_text']==page
        return dict(premier_summary='网页描述 SIP 音频警示产品，更多规格待核实',target_users='学校广播场景用户',
            core_value='清晰的广播和状态提示',positioning='价格和细分定位待确认',design_principles='方便理解和维护',
            differentiation='结合项目需求评估差异',constraints='规格和兼容性需核实',out_of_scope='未经核实的功能不纳入',
            rationale='基于官网原文与项目目标提出草稿',facts=[dict(text='官网描述为 SIP speaker',quote='8180 IP Audio Alerter is a SIP speaker for paging.')],
            unknowns=['功率和价格待核实'])
    monkeypatch.setattr(adapters,'model_json',analysis)
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        pid=c.post('/api/projects',json={'name':'Premier 选择测试','direction':'学校 SIP 音频广播终端'}).json()['id']
        root='/api/projects/'+pid
        comp=c.post(root+'/competitors',json={'brand':'Algo','model':'8180','url':'https://www.algosolutions.com/product/8180-sip-audio-alerter'}).json()
        queued=c.post(root+'/competitors/'+comp['id']+'/premier',json={'mode':'live'}).json()
        for _ in range(100):
            result=c.get('/api/jobs/'+queued['job_id']).json()
            if result['status'] in ('completed','failed'):break
            time.sleep(.05)
        assert result['status']=='completed',result
        selected=result['result']
        assert selected['baseline']['data']['competitor_id']==comp['id']
        assert selected['baseline']['data']['facts'][0]['source_id']==selected['source']['id']
        assert selected['candidate']['data']['baseline_id']==selected['baseline']['id']
        assert selected['candidate']['data']['core_value']=='清晰的广播和状态提示'

def test_cad_generation_removed():
    with TestClient(app) as c:
        assert not any('/cad' in path for path in c.get('/openapi.json').json()['paths'])
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        status=c.get('/api/status').json()
        assert status['cad_generation'] is False and status['cad_chat_editing'] is False
        assert status['model_training_required'] is False

def test_sales_contract(monkeypatch):
    monkeypatch.setenv('SALES_TOKEN','test-sales-secret')
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        p=c.post('/api/projects',json={'name':'销售契约测试','direction':'测试客户画像'}).json()
        root='/api/projects/'+p['id']
        profile=c.post(root+'/profiles',json={'industry':'教育'}).json()
        event=dict(event_id='evt-sales-contract',project_id=p['id'],profile_version=profile['id'],source_system='company-sales',external_customer_id='customer-123',customer_name='契约测试摘要',updated_at='2026-11-09T10:00:00+00:00')
        url='/api/integrations/sales/matches';headers={'Authorization':'Bearer test-sales-secret'}
        assert c.post(url,json=event).status_code==401
        assert c.post(url,json=event,headers=headers).json()['status']=='accepted'
        assert c.post(url,json=event,headers=headers).json()['status']=='duplicate'
        assert c.post(url,json=event|{'event_id':'evt-withdraw','action':'withdraw','updated_at':'2026-11-09T11:00:00+00:00'},headers=headers).status_code==200
        assert c.get(root).json()['matches'][0]['action']=='withdraw'
        c.post(root+'/profiles',json={'industry':'医疗'})
        assert c.post(url,json=event|{'event_id':'evt-stale'},headers=headers).status_code==409
        other=c.post('/api/projects',json={'name':'无权项目','direction':'客户资料不可泄漏'}).json()
        c.post(root+'/members',json={'name':'isolated','password':'isolated-password','role':'sales'})
        with TestClient(app) as stranger:
            stranger.post('/api/auth/login',json={'name':'isolated','password':'isolated-password'})
            assert stranger.get('/api/projects/'+other['id']).status_code==404
            assert all(a['project_id']!=other['id'] for a in stranger.get('/api/assets').json())

def test_admin_account_configuration():
    with TestClient(app) as admin:
        login=admin.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        assert login.json()['account_role']=='admin'
        assert admin.get('/api/me').json()['account_role']=='admin'
        project=admin.post('/api/projects',json={'name':'账户权限验证','direction':'验证销售与市场项目授权'}).json()
        second=admin.post('/api/projects',json={'name':'未分配项目','direction':'验证跨项目权限隔离'}).json()
        config={'role':'sales','project_ids':[project['id']],'active':True,'password':'initial-password'}
        created=admin.post('/api/admin/accounts',json={'name':'configured-sales',**config})
        assert created.status_code==200,created.text
        uid=created.json()['id']
        assert admin.post('/api/admin/accounts',json={'name':'configured-sales',**config}).status_code==409
        listing=admin.get('/api/admin/accounts').json()
        assert 'password' not in str(listing)
        assert any(p['id']==project['id'] for p in listing['projects'])
        with TestClient(app) as sales:
            assert sales.post('/api/auth/login',json={'name':'configured-sales','password':'initial-password'}).status_code==200
            assert sales.get('/api/admin/accounts').status_code==403
            assert sales.post('/api/admin/accounts',json={'name':'escalated-user',**config}).status_code==403
            assert sales.post('/api/admin/accounts/'+uid,json=config).status_code==403
            assert sales.get('/api/projects/'+project['id']).status_code==200
            assert sales.get('/api/projects/'+second['id']).status_code==404
            assert sales.post('/api/projects/'+project['id']+'/feedback',json={'quote':'销售客户原话测试','source':'权限验证'}).status_code==200
            assert sales.post('/api/projects/'+project['id']+'/profiles',json={}).status_code==403
            assert sales.post('/api/projects',json={'name':'越权创建','direction':'不允许自行成为负责人'}).status_code==403
            assert admin.post('/api/admin/accounts/'+uid,json=config|{'role':'marketing','project_ids':[second['id']],'password':'new-password'}).status_code==200
            assert sales.get('/api/me').status_code==401
            assert sales.post('/api/auth/login',json={'name':'configured-sales','password':'initial-password'}).status_code==401
            assert sales.post('/api/auth/login',json={'name':'configured-sales','password':'new-password'}).json()['account_role']=='marketing'
            assert sales.get('/api/projects/'+project['id']).status_code==404
            assert sales.get('/api/projects/'+second['id']).json()['role']=='marketing'
            assert sales.post('/api/projects/'+second['id']+'/feedback',json={'quote':'市场场景反馈测试','source':'权限验证'}).status_code==200
            assert sales.post('/api/projects/'+second['id']+'/profiles',json={}).status_code==403
            assert admin.post('/api/admin/accounts/'+uid,json=config|{'active':False,'password':''}).status_code==200
            assert sales.get('/api/me').status_code==401
            assert sales.post('/api/auth/login',json={'name':'configured-sales','password':'new-password'}).status_code==401
        assert admin.post('/api/admin/accounts/'+login.json()['id'],json=config).status_code==403
        assert admin.post('/api/admin/accounts',json={'name':'bad-project-user',**config,'project_ids':['missing']}).status_code==422
        assert admin.post('/api/admin/accounts',json={'name':'bad-role-user',**config,'role':'admin'}).status_code==422
        with TestClient(app) as anonymous:assert anonymous.get('/api/admin/accounts').status_code==401

def test_existing_short_password_login():
    from backend.main import password_hash
    with TestClient(app) as c:
        with db.connect() as conn:
            conn.execute('INSERT INTO users VALUES(?,?,?)',(db.uid(),'legacy-short',password_hash('short')))
        assert c.post('/api/auth/login',json={'name':'legacy-short','password':'short'}).status_code==200
        assert c.post('/api/auth/login',json={'name':'legacy-short','password':'wrong'}).status_code==401
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        assert c.post('/api/admin/accounts',json={'name':'short-new','role':'sales','password':'short'}).status_code==422

def test_admin_password_recovery():
    from scripts.reset_admin_password import reset
    import pytest
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        with pytest.raises(ValueError):reset('short')
        assert c.get('/api/me').status_code==200
        try:
            reset('recovery-password-123')
            assert c.get('/api/me').status_code==401
            assert c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'}).status_code==401
            assert c.post('/api/auth/login',json={'name':'admin','password':'recovery-password-123'}).json()['account_role']=='admin'
        finally:reset('test-password-123')


def test_knowledge_permissions_and_assistant(monkeypatch):
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        pid=c.post('/api/projects',json={'name':'知识权限','direction':'知识资料复用测试'}).json()['id'];root='/api/projects/'+pid
        body=dict(title='公司模块',content='公司支持警示灯模块',source_system='catalog',external_id='module',source_version='1',locator='内部产品说明')
        first=c.post(root+'/knowledge',json=body).json()
        assert c.post(root+'/knowledge',json=body).json()['id']==first['id']
        assert c.post(root+'/knowledge',json=body|{'content':'同版不一致'}).status_code==409
        second=c.post(root+'/knowledge',json=body|{'content':'增加接口定义','source_version':'2'}).json()
        assert second['data']['previous_id']==first['id']
        other=c.post('/api/projects',json={'name':'引用资料项目','direction':'跨项目资料引用'}).json()['id']
        ref=c.post('/api/projects/'+other+'/references',json={'source_project_id':pid,'source_record_id':second['id'],'conditions':'仅作设计参考'}).json()
        before=c.get('/api/projects/'+other+'/agent-context').json()
        assert before['records'][0]['source']['id']==second['id']
        textfile=c.post(root+'/files',files={'file':('capabilities.md','模块能力与工程约束'.encode())}).json()
        context=c.get(root+'/agent-context').json()
        assert second['id'] in [r['id'] for r in context['records']]
        assert first['id'] not in [r['id'] for r in context['records']]
        assert any(r['data'].get('upload_id')==textfile['record']['id'] for r in context['records'])
        assert c.get(textfile['url']+'?inline=true').headers['content-type'].startswith('text/plain')
        response=c.post(root+'/assistant',json={'mode':'demo','query':'项目有什么公司资料？','tool':'question'}).json()
        assert response['provenance']=='demo' and response['citations']
        captured=[]
        def model(task,context,schema):
            captured.append(context)
            return {'answer':'有引用依据的回答','citations':[second['id']]}
        monkeypatch.setattr('backend.adapters.model_json',model)
        answer=c.post(root+'/assistant',json={'mode':'live','query':'有哪些模块？'})
        assert answer.status_code==200 and second['id'] in answer.json()['citations']
        assert second['id'] in [r['id'] for r in captured[0]['records']]
        monkeypatch.setattr('backend.adapters.model_json',lambda *args:{'answer':'无效引用','citations':['unauthorized-id']})
        assert c.post(root+'/assistant',json={'mode':'live','query':'问题'}).status_code==422
        with db.connect() as conn:conn.execute('DELETE FROM members WHERE project_id=?',(pid,))
        assert ref['id'] not in [r['id'] for r in c.get('/api/projects/'+other+'/agent-context').json()['records']]
        assert c.get(textfile['url']).status_code==404
        assert all(r['project_id']!=pid for r in c.get('/api/assets').json())


def test_file_links_and_preview():
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        pid=c.post('/api/projects',json={'name':'上传权限验证','direction':'预览和文件关联'}).json()['id'];root='/api/projects/'+pid
        assert c.post(root+'/files',files={'file':('model.step',b'file')},data={'metadata':'bad json'}).status_code==422
        assert c.post(root+'/files',files={'file':('model.step',b'file')},data={'metadata':json.dumps({'hardware_feature_indexes':[0]})}).status_code==422
        assert c.post(root+'/files',files={'file':('model.step',b'file')},data={'metadata':json.dumps({'need_ids':['foreign-id']})}).status_code==422
        assert c.post(root+'/files',files={'file':('empty.step',b'')}).status_code==422
        assert c.post(root+'/files',files={'file':('payload.exe',b'anything')}).status_code==422
        original=c.post(root+'/files',files={'file':('drawing.step',b'professional file')}).json()
        preview=c.post(root+'/files',files={'file':('preview.svg',b'<svg xmlns="http://www.w3.org/2000/svg"/>')},data={'metadata':json.dumps({'preview_of_id':original['record']['id']})}).json()
        r=c.get(preview['url']+'?inline=true')
        assert 'sandbox' in r.headers['content-security-policy'] and 'inline' in r.headers['content-disposition']
        assert c.get(original['url']+'?inline=true').headers['content-disposition'].startswith('attachment')
        c.post(root+'/members',json={'name':'file-viewer','password':'file-viewer-password','role':'viewer'})
        c.post('/api/auth/login',json={'name':'file-viewer','password':'file-viewer-password'})
        assert c.get(preview['url']).status_code==200
        assert c.post(root+'/files',files={'file':('note.txt',b'note')}).status_code==403
        assert c.post(root+'/product-tones',json=tone_body('missing')).status_code==403


def test_file_version_concurrency():
    from concurrent.futures import ThreadPoolExecutor
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'name':'admin','password':'test-password-123'})
        pid=c.post('/api/projects',json={'name':'并发上传测试','direction':'文件不可变版本'}).json()['id'];root='/api/projects/'+pid
        first=c.post(root+'/files',files={'file':('notes.txt',b'original')}).json()
        def update(value):return c.post(root+'/files',files={'file':('notes.txt',value)},data={'metadata':json.dumps({'previous_id':first['record']['id'],'note':'上传新版本'})})
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(update,[b'first',b'second']))
        assert sorted(r.status_code for r in results)==[200,409]
        assert len(c.get(root+'/files/'+first['record']['id']+'/versions').json())==2
