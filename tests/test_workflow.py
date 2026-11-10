import os, tempfile, time
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='foundry-tests-')
os.environ['BOOTSTRAP_PASSWORD']='test-password-123'
from fastapi.testclient import TestClient
from backend.main import app
from backend import db

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
        post(root+'/mock-sales')
        post(root+'/mock-sales')
        assert len(c.get(root).json()['matches'])==1
        post(root+'/feedback',{'quote':'紧急广播时，希望警示灯更醒目','source':'测试访谈（非真实）','provenance':'demo'})
        need=job(post(root+'/needs/generate',{'mode':'demo'}))[0]
        data={k:need['data'][k] for k in ('title','description','feedback_ids','allocation','status')}
        data['status']='confirmed'
        post(root+'/needs/'+need['id'],data)
        proposals=job(post(root+'/proposals/generate',{'mode':'demo'}))
        assert len(proposals)==2
        selected=proposals[1]
        post(root+'/reviews',{'target_id':selected['id'],'discipline':'工程','conclusion':'待评估','comment':'测试流程，生产参数待评审'})
        post(root+'/proposals/'+selected['id']+'/select')
        candidate=job(post(root+'/prd/generate',{'mode':'demo'}))
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
        cad=job(post(root+'/cad',{'parameters':{},'confirmed':True}))
        assert cad['data']['checks']['step_reopened']
        assert cad['data']['checks']['solids']==5
        operation=post(root+'/cad/'+cad['id']+'/propose',{'message':'扬声器区域加宽 20 mm，屏幕有效显示区不变','mode':'rules'})
        assert operation['operation']['data']['changes']=={'speaker_width':{'before':80.0,'after':100.0}}
        changed=job(post(root+'/cad/operations/'+operation['operation']['id']+'/apply'))
        assert changed['data']['parameters']['screen_width']==120
        assert abs(changed['data']['checks']['bbox_mm'][0]-cad['data']['checks']['bbox_mm'][0]-20)<1e-6
        restored=job(post(root+'/cad/'+cad['id']+'/restore'))
        assert restored['data']['parameters']==cad['data']['parameters']
        post(root+'/baselines',{'competitor_id':comp['id'],'reason':'更新参考资料'})
        assert db.record(prd['id'],pid)['data']['baseline_id']==base['id']
        post(root+'/cad',{'parameters':{},'confirmed':True},422)
        files=db.rows(pid,'cad_files')[0]['data']['files']
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

def test_geometry_constraints():
    from backend.cad_engine import validate,DEFAULTS
    import pytest
    with pytest.raises(ValueError,match='冲突'):validate(DEFAULTS|{'screen_height':150})

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
