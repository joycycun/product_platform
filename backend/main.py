import os, json, secrets, hashlib, hmac, time, shutil, re, difflib, io, zipfile, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from docx import Document
from . import db, schemas as s, adapters
from .cad_engine import generate as generate_cad, validate as validate_cad

pool=ThreadPoolExecutor(max_workers=3)
cad_lock=threading.Lock()

def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()

@asynccontextmanager
async def lifespan(app):
    db.init()
    if os.getenv('BOOTSTRAP_PASSWORD'):
        with db.connect() as c:
            c.execute('INSERT OR IGNORE INTO users VALUES(?,?,?)',(db.uid(),os.getenv('BOOTSTRAP_USER','admin'),password_hash(os.environ['BOOTSTRAP_PASSWORD'])))
    yield

app=FastAPI(title='Zycoo · 产品设计平台',version='0.1.0',lifespan=lifespan)
@app.exception_handler(ValueError)
async def invalid(request,exc):return JSONResponse(status_code=422,content={'detail':str(exc)})

@app.middleware('http')
async def security(request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS') and request.cookies.get('session'):
        origin=request.headers.get('origin')
        if origin and origin.split('://')[-1]!=request.headers.get('host'):return JSONResponse(status_code=403,content={'detail':'跨站写入被拒绝'})
    r=await call_next(request)
    r.headers['X-Content-Type-Options']='nosniff';r.headers['Referrer-Policy']='same-origin'
    return r

def user(request:Request):
    token=request.cookies.get('session','')
    with db.connect() as c:r=c.execute('SELECT u.id,u.name FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    if not r:raise HTTPException(401,'请先登录')
    return dict(r)

def access(pid,u,write=False,roles=None):
    with db.connect() as c:r=c.execute('SELECT role FROM members WHERE project_id=? AND user_id=?',(pid,u['id'])).fetchone()
    if not r:raise HTTPException(404,'项目不存在或无访问权限')
    if (write and r['role']=='viewer') or (roles and r['role'] not in roles):raise HTTPException(403,'当前角色无此操作权限')
    return r['role']

def project(pid):
    with db.connect() as c:r=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    if not r:raise ValueError('项目不存在')
    return dict(r)

def required(pid,kind):
    r=db.latest(pid,kind)
    if not r:raise ValueError('请先完成：'+kind)
    return r

def trace(pid):
    b=required(pid,'baseline');select=required(pid,'selection');plan=db.record(select['data']['proposal_id'],pid,'proposal')
    if plan['data']['baseline_id']!=b['id']:raise ValueError('premier 已更换，请重新评审并选择基于当前基准的方案')
    return {'baseline_id':b['id'],'proposal_id':plan['id'],'profile_id':required(pid,'profile')['id'],'need_ids':sorted({n for f in plan['data']['features'] for n in f['need_ids']})}

def register_file(pid,rid,path,mime=None):
    path=Path(path)
    mime=mime or {'svg':'image/svg+xml','json':'application/json','txt':'text/plain','pdf':'application/pdf'}.get(path.suffix[1:],'application/octet-stream')
    fid=db.uid()
    with db.connect() as c:c.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?)',(fid,pid,rid,path.name,str(path.relative_to(db.ROOT)),mime,db.now()))
    return {'id':fid,'name':path.name,'url':'/api/files/'+fid}

def submit(pid,kind,inputs,fn):
    jid=db.uid()
    with db.connect() as c:c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(jid,pid,kind,'queued',json.dumps(inputs,ensure_ascii=False),None,None,db.now(),None))
    def work():
        with db.connect() as c:c.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,))
        try:
            result=fn()
            with db.connect() as c:c.execute("UPDATE jobs SET status='completed',result=?,finished_at=? WHERE id=?",(json.dumps(result,ensure_ascii=False),db.now(),jid))
        except Exception as e:
            if isinstance(e,httpx.HTTPStatusError):message=f'外部服务返回 HTTP {e.response.status_code}；请检查凭据、配额或页面访问权限'
            elif isinstance(e,httpx.RequestError):message='外部服务连接失败或超时；请检查网络与配置'
            else:message=str(e)[:1200]
            with db.connect() as c:c.execute("UPDATE jobs SET status='failed',error=?,finished_at=? WHERE id=?",(message,db.now(),jid))
    pool.submit(work)
    return {'job_id':jid}
import httpx

@app.post('/api/auth/login')
def login(body:s.Login,response:Response):
    with db.connect() as c:
        r=c.execute('SELECT * FROM users WHERE name=?',(body.name,)).fetchone()
        if not r or not hmac.compare_digest(password_hash(body.password,r['password'].split(':')[0]),r['password']):raise HTTPException(401,'账号或密码错误')
        token=secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),r['id'],time.time()+43200))
    response.set_cookie('session',token,httponly=True,samesite='strict',secure=os.getenv('COOKIE_SECURE')=='true',max_age=43200)
    return {'id':r['id'],'name':r['name']}
@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
    with db.connect() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get('session','').encode()).hexdigest(),))
    response.delete_cookie('session');return {'ok':True}
@app.get('/api/me')
def me(u=Depends(user)):return u
@app.get('/api/status')
def status(u=Depends(user)):return adapters.config()
@app.get('/api/projects')
def projects(u=Depends(user)):
    with db.connect() as c:return [dict(r) for r in c.execute('SELECT p.*,m.role FROM projects p JOIN members m ON m.project_id=p.id WHERE m.user_id=? ORDER BY p.rowid DESC',(u['id'],))]
@app.post('/api/projects')
def new_project(body:s.Project,u=Depends(user)):
    pid=db.uid()
    with db.connect() as c:
        c.execute('INSERT INTO projects VALUES(?,?,?,?,?)',(pid,body.name,body.direction,body.constraints,db.now()))
        c.execute('INSERT INTO members VALUES(?,?,?)',(pid,u['id'],'owner'))
    db.audit(pid,u['name'],'创建项目',body.model_dump())
    return project(pid)
@app.get('/api/projects/{pid}')
def workspace(pid:str,u=Depends(user)):
    role=access(pid,u)
    with db.connect() as c:
        matches=[json.loads(r['data']) for r in c.execute('SELECT data FROM matches WHERE project_id=?',(pid,))]
        jobs=[dict(r) for r in c.execute('SELECT id,kind,status,error,created_at,finished_at FROM jobs WHERE project_id=? ORDER BY rowid DESC LIMIT 30',(pid,))]
        members=[dict(r) for r in c.execute('SELECT u.name,m.role FROM users u JOIN members m ON m.user_id=u.id WHERE m.project_id=?',(pid,))]
    return {'project':project(pid),'role':role,'records':db.rows(pid),'matches':matches,'jobs':jobs,'members':members}
class Member(s.Login):role:str=Field(pattern='^(owner|product|sales|engineering|viewer)$')
@app.post('/api/projects/{pid}/members')
def member(pid:str,b:Member,u=Depends(user)):
    access(pid,u,roles=['owner'])
    with db.connect() as c:
        r=c.execute('SELECT id FROM users WHERE name=?',(b.name,)).fetchone()
        uid=r['id'] if r else db.uid()
        if not r:c.execute('INSERT INTO users VALUES(?,?,?)',(uid,b.name,password_hash(b.password)))
        if uid==u['id']:raise ValueError('不能通过此接口变更自己的项目角色')
        c.execute('INSERT INTO members VALUES(?,?,?) ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role',(pid,uid,b.role))
    db.audit(pid,u['name'],'成员权限更新',{'name':b.name,'role':b.role});return {'ok':True}
@app.post('/api/projects/{pid}/profiles')
def profile(pid:str,b:s.Profile,u=Depends(user)):
    access(pid,u,roles=['owner','product'])
    r=db.add(pid,'profile',b.model_dump()|{'version':len(db.rows(pid,'profile'))+1,'status':'published'},u['name'])
    db.audit(pid,u['name'],'发布画像，等待上游重匹配',{'profile_id':r['id']});return r
@app.get('/api/integrations/sales/profiles')
def upstream_profiles(request:Request):
    sales_auth(request)
    with db.connect() as c:pids=[r['id'] for r in c.execute('SELECT id FROM projects')]
    return [dict(project_id=p,profile=db.latest(p,'profile')) for p in pids if db.latest(p,'profile')]
def sales_auth(request):
    key=os.getenv('SALES_TOKEN','')
    if not key:raise HTTPException(503,'正式销售集成未配置')
    if not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+key):raise HTTPException(401,'上游身份校验失败')
def receive_match(b,mock=False):
    p=db.record(b.profile_version,b.project_id,'profile')
    if required(b.project_id,'profile')['id']!=p['id']:raise HTTPException(409,'画像版本已过期，请重新匹配')
    if not mock and b.source_system!=os.getenv('SALES_SOURCE_SYSTEM','company-sales'):raise HTTPException(403,'来源系统与凭据不匹配')
    data=b.model_dump()|{'provenance':'mock_upstream' if mock else 'sales_upstream'}
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        event=c.execute('SELECT * FROM events WHERE id=?',(b.event_id,)).fetchone()
        if event:
            if (event['project_id'],event['source_system'],event['external_id'])!=(b.project_id,b.source_system,b.external_customer_id):raise HTTPException(409,'event_id 已被其他对象使用')
            return {'status':'duplicate'}
        prev=c.execute('SELECT updated_at FROM matches WHERE project_id=? AND source_system=? AND external_id=?',(b.project_id,b.source_system,b.external_customer_id)).fetchone()
        if prev and datetime.fromisoformat(prev['updated_at'])>=datetime.fromisoformat(b.updated_at):raise HTTPException(409,'推送时间不晚于已接收版本')
        c.execute('INSERT INTO matches VALUES(?,?,?,?,?) ON CONFLICT(project_id,source_system,external_id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at',(b.project_id,b.source_system,b.external_customer_id,json.dumps(data,ensure_ascii=False),b.updated_at))
        c.execute('INSERT INTO events VALUES(?,?,?,?,?)',(b.event_id,b.project_id,b.source_system,b.external_customer_id,db.now()))
    db.audit(b.project_id,b.source_system,'接收匹配客户',{'event_id':b.event_id,'action':b.action,'provenance':data['provenance']})
    return {'status':'accepted'}
@app.post('/api/integrations/sales/matches')
def sales_match(b:s.Match,request:Request):sales_auth(request);return receive_match(b)
@app.post('/api/projects/{pid}/mock-sales')
def mock_sales(pid:str,u=Depends(user)):
    access(pid,u,write=True)
    b=s.Match(event_id=db.uid(),project_id=pid,profile_version=required(pid,'profile')['id'],source_system='mock-sales',external_customer_id='DEMO-SCHOOL-001',customer_name='示例学校 · 模拟上游',industry='教育',region='示例地区',owner='演示销售',reasons=['画像行业命中：教育','场景偏好：走廊广播'],hard_conditions=['教育行业（模拟）'],preferences=['需要远距离警示（模拟匹配依据，非访谈事实）'],updated_at=db.now())
    return receive_match(b,True)
@app.post('/api/projects/{pid}/match-decisions')
def match_decision(pid:str,b:dict=Body(...),u=Depends(user)):
    access(pid,u,write=True)
    if b.get('decision') not in ('exclude','followup'):raise ValueError('decision 应为 exclude/followup')
    return db.add(pid,'match_decision',b,u['name'])
@app.post('/api/projects/{pid}/search')
def search(pid:str,b:s.Generation,u=Depends(user)):
    access(pid,u,write=True)
    query=b.query or project(pid)['direction']
    def run():return [db.add(pid,'competitor',x|{'query':query},u['name']) for x in adapters.search(query,b.mode)]
    return submit(pid,'竞品搜索',{'mode':b.mode,'query':query},run)
@app.post('/api/projects/{pid}/competitors')
def competitor(pid:str,b:s.Competitor,u=Depends(user)):
    access(pid,u,write=True);return db.add(pid,'competitor',b.model_dump(),u['name'])
@app.post('/api/projects/{pid}/competitors/{rid}/read')
def read_page(pid:str,rid:str,u=Depends(user)):
    access(pid,u,write=True);r=db.record(rid,pid,'competitor')
    def run():
        text=adapters.fetch_page(r['data']['url'])
        return db.add(pid,'source',{'competitor_id':rid,'url':r['data']['url'],'text':text,'provenance':'live_fetch','status':'read','locator':'正文段落','collected_at':db.now()},u['name'])
    return submit(pid,'读取竞品网页',{'competitor_id':rid,'url':r['data']['url']},run)
class SourceInput(s.Strict):
    competitor_id:str
    text:str=Field(min_length=20,max_length=60000)
    url:str=''
    locator:str='人工提供原文'
@app.post('/api/projects/{pid}/sources')
def source(pid:str,b:SourceInput,u=Depends(user)):
    access(pid,u,write=True);db.record(b.competitor_id,pid,'competitor')
    return db.add(pid,'source',b.model_dump()|{'provenance':'manual','collected_at':db.now()},u['name'])
class FactsResult(s.Strict):facts:list[s.Fact]
@app.post('/api/projects/{pid}/sources/{rid}/extract')
def extract(pid:str,rid:str,b:s.Generation,u=Depends(user)):
    access(pid,u,write=True);r=db.record(rid,pid,'source')
    def run():
        result=adapters.model_json('抽取最多 12 条可核对竞品事实。quote 必须逐字来自原文；source_id 为输入 id；status=pending。',r,FactsResult) if b.mode=='live' else {'facts':[{'text':r['data']['text'][:180],'quote':r['data']['text'][:180],'source_id':rid,'status':'pending'}]}
        for f in result['facts']:
            if f['quote'] not in r['data']['text'] or not f['quote']:raise ValueError('模型事实引用不在原文中，结果未采纳')
            f.update(source_id=rid,status='pending')
        return db.add(pid,'facts',result|{'source_id':rid,'competitor_id':r['data']['competitor_id'],'provenance':'model' if b.mode=='live' else 'demo'},u['name'])
    return submit(pid,'提取事实',{'source_id':rid,'mode':b.mode},run)
@app.post('/api/projects/{pid}/baselines')
def baseline(pid:str,b:s.Baseline,u=Depends(user)):
    access(pid,u,roles=['owner','product']);c=db.record(b.competitor_id,pid,'competitor')
    for fact in b.facts:
        if fact.source_id:
            source=db.record(fact.source_id,pid,'source')
            if source['data']['competitor_id']!=b.competitor_id:raise ValueError('事实来源不属于此竞品')
            if not fact.quote or fact.quote not in source['data']['text']:raise ValueError('事实引文必须出现在指定原文中')
        if fact.status=='verified' and not fact.source_id:raise ValueError('已核实事实必须关联证据原文')
    old=db.latest(pid,'baseline')
    r=db.add(pid,'baseline',b.model_dump()|{'competitor':c['data'],'previous_id':old['id'] if old else None,'provenance':c['data']['provenance'],'impacted_ids':[x['id'] for x in db.rows(pid) if old and x['kind'] in ('proposal','prd','cad')]},u['name'])
    db.audit(pid,u['name'],'冻结 premier 基准',{'baseline_id':r['id']});return r
@app.post('/api/projects/{pid}/feedback')
def feedback(pid:str,b:s.Feedback,u=Depends(user)):
    access(pid,u,write=True);return db.add(pid,'feedback',b.model_dump(),u['name'])
@app.post('/api/projects/{pid}/needs/generate')
def gen_needs(pid:str,b:s.Generation,u=Depends(user)):
    access(pid,u,write=True);base=required(pid,'baseline');fs=db.rows(pid,'feedback')
    if not fs:raise ValueError('请先录入有来源的反馈')
    def run():
        result=s.NeedResult(needs=adapters.needs(fs,base,b.mode)).model_dump()['needs']
        for n in result:
            for rid in n['feedback_ids']:db.record(rid,pid,'feedback')
            n.update(status='pending',baseline_id=base['id'],provenance='model' if b.mode=='live' else 'demo')
        return [db.add(pid,'need',n,u['name']) for n in result]
    return submit(pid,'需求提取与软硬件拆解',{'mode':b.mode,'baseline_id':base['id'],'feedback_ids':[f['id'] for f in fs]},run)
@app.post('/api/projects/{pid}/needs/{rid}')
def edit_need(pid:str,rid:str,b:s.Need,u=Depends(user)):
    access(pid,u,roles=['owner','product','engineering']);old=db.record(rid,pid,'need')
    for fid in b.feedback_ids:db.record(fid,pid,'feedback')
    r=db.add(pid,'need',old['data']|b.model_dump()|{'supersedes':rid,'reviewed_by':u['name']},u['name'])
    return r

def current_needs(pid):
    needs=db.rows(pid,'need');superseded={r['data'].get('supersedes') for r in needs}
    return [r for r in needs if r['id'] not in superseded]
@app.post('/api/projects/{pid}/proposals/generate')
def gen_proposals(pid:str,b:s.Generation,u=Depends(user)):
    access(pid,u,write=True);base=required(pid,'baseline');ns=[n for n in current_needs(pid) if n['data']['status']=='confirmed']
    if not ns:raise ValueError('请先确认至少一条需求及实现拆解')
    if any(n['data']['baseline_id']!=base['id'] for n in ns):raise ValueError('已确认需求引用旧基准，请基于新基准重新提取和确认需求')
    def run():
        result=s.Proposals(proposals=adapters.proposals(ns,base,project(pid)['constraints'],b.mode)).model_dump()['proposals']
        allowed={n['id'] for n in ns}
        for p in result:
            if any(not set(f['need_ids'])<=allowed for f in p['features']):raise ValueError('方案引用了未确认或不存在的需求')
            p.update(baseline_id=base['id'],provenance='model' if b.mode=='live' else 'demo',status='pending')
        return [db.add(pid,'proposal',p,u['name']) for p in result]
    return submit(pid,'生成候选功能方案',{'mode':b.mode,'baseline_id':base['id'],'need_ids':[n['id'] for n in ns]},run)
@app.post('/api/projects/{pid}/proposals/{rid}/revise')
def revise_proposal(pid:str,rid:str,b:s.Proposal,u=Depends(user)):
    access(pid,u,roles=['owner','product','engineering']);old=db.record(rid,pid,'proposal')
    for f in b.features:
        for nid in f.need_ids:db.record(nid,pid,'need')
    return db.add(pid,'proposal',old['data']|b.model_dump()|{'supersedes':rid},u['name'])
class Review(s.Strict):
    target_id:str
    discipline:str=Field(min_length=1,max_length=100)
    conclusion:str=Field(pattern='^(待评估|通过|否决)$')
    comment:str=Field(min_length=2,max_length=4000)
@app.post('/api/projects/{pid}/reviews')
def review(pid:str,b:Review,u=Depends(user)):
    access(pid,u,roles=['owner','product','engineering']);db.record(b.target_id,pid)
    return db.add(pid,'review',b.model_dump(),u['name'])
@app.post('/api/projects/{pid}/proposals/{rid}/select')
def select(pid:str,rid:str,u=Depends(user)):
    access(pid,u,roles=['owner','product']);r=db.record(rid,pid,'proposal')
    if r['data']['baseline_id']!=required(pid,'baseline')['id']:raise ValueError('方案基于旧 premier，请重新生成')
    reviews=[r for r in db.rows(pid,'review') if r['data']['target_id']==rid]
    if not reviews:raise ValueError('请先提交至少一条评审意见')
    if any(r['data']['conclusion']=='否决' for r in {r['data']['discipline']:r for r in reviews}.values()):raise ValueError('该方案仍有专业评审为否决，请先解决对应评审')
    return db.add(pid,'selection',{'proposal_id':rid,'status':'selected_draft','review_ids':[r['id'] for r in reviews]},u['name'])

def prd_text(pid,t):
    p=project(pid);base=db.record(t['baseline_id'],pid);profile=db.record(t['profile_id'],pid);plan=db.record(t['proposal_id'],pid)
    ns=[db.record(n,pid) for n in t['need_ids']]
    lines=[f'# {p["name"]} · PRD', '\n状态：待评审草稿。方案选择不等于工程批准。', '\n## 1. 项目目标',p['direction'],'\n## 2. 约束与范围',p['constraints'] or '待补充','\n## 3. 目标客户画像',json.dumps(profile['data'],ensure_ascii=False,indent=2),'\n## 4. Premier 基准',f'{base["data"]["competitor"]["brand"]} / {base["data"]["competitor"]["model"]}',f'基准 ID: {base["id"]}；来源：{base["data"]["provenance"]}', '选择依据：'+base['data']['reason']]
    for f in base['data']['facts']:lines.append(f'- [{f["status"]}] {f["text"]} | 引文：{f["quote"]} | 证据：{f["source_id"]}')
    lines+=['未知项：'+'；'.join(base['data']['unknowns']),'\n## 5. 用户需求与原始依据']
    for n in ns:
        lines += [f'### {n["data"]["title"]} [{n["id"]}]',n['data']['description'],f'状态：{n["data"]["status"]}；内容来源：{n["data"]["provenance"]}']
        for fid in n['data']['feedback_ids']:
            f=db.record(fid,pid);lines.append(f'> {f["data"]["quote"]}（来源：{f["data"]["source"]}，{f["id"]}，{f["data"]["provenance"]}）')
        for k,v in n['data']['allocation'].items():lines.append(f'- {k}: {v}')
    lines+=['\n## 6. 功能方案与基准差异',plan['data']['name']]
    for f in plan['data']['features']:lines.extend([f'### {f["name"]} · {f["relationship"]}',f'premier：{f["premier_behavior"]}',f'公司方案：{f["our_behavior"]}',f'依据：{f["rationale"]}',f'风险：{f["risks"]}',f'需求引用：{", ".join(f["need_ids"])}'])
    lines+=['\n## 7. 评审与决策']
    for r in db.rows(pid,'review'):
        if r['data']['target_id']==plan['id']:lines.append(f'{r["author"]} / {r["data"]["discipline"]} / {r["data"]["conclusion"]}: {r["data"]["comment"]}')
    lines+=['\n## 8. 页面流程与原型','设备状态 → 事件详情 → 配置 → 异常恢复（低保真待确认）','\n## 9. CAD 与结构约束','支持矩形带屏终端参数模型。屏幕/扬声器为占位包络；尺寸须人工确认。制造、电气、声学、散热、公差待工程审核。','\n## 10. 验收与未决事项','按每条需求的联合验收执行，缺少阈值、责任人与条件的条目不视为验收通过。','\n## 11. 追溯快照',json.dumps(t,ensure_ascii=False,indent=2)]
    return '\n\n'.join(lines)
class TextResult(s.Strict):content:str=Field(min_length=100,max_length=100000)
@app.post('/api/projects/{pid}/prd/generate')
def gen_prd(pid:str,b:s.Generation,u=Depends(user)):
    access(pid,u,write=True);t=trace(pid);text=prd_text(pid,t)
    def run():
        content=adapters.model_json('根据全部结构化依据生成完整 Markdown PRD，保留对象ID、来源和未决事项。不能把演示或建议写成事实。',{'draft_from_project':text},TextResult)['content'] if b.mode=='live' else text
        return db.add(pid,'prd_candidate',t|{'content':content,'provenance':'model' if b.mode=='live' else 'project_template','status':'pending'},u['name'])
    return submit(pid,'生成 PRD 待合并草稿',{'mode':b.mode,**t},run)
class PRDSave(s.Strict):
    content:str=Field(min_length=1,max_length=200000)
    base_id:str=''
    candidate_id:str=''
    note:str=Field(min_length=2,max_length=1000)
    status:str=Field(default='draft',pattern='^(draft|released)$')
@app.post('/api/projects/{pid}/prd')
def save_prd(pid:str,b:PRDSave,u=Depends(user)):
    access(pid,u,roles=['owner','product']);candidate=db.record(b.candidate_id,pid) if b.candidate_id else None
    if candidate and candidate['kind'] not in ('prd_candidate','prd'):raise ValueError('无效 PRD 候选')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        current=c.execute("SELECT id,data FROM records WHERE project_id=? AND kind='prd' ORDER BY rowid DESC LIMIT 1",(pid,)).fetchone()
        if (current['id'] if current else '')!=b.base_id:raise HTTPException(409,'文档已被更新，请刷新并比较最新版本')
        t={k:(candidate['data'][k] if candidate else json.loads(current['data'])[k]) for k in ('baseline_id','proposal_id','profile_id','need_ids')} if candidate or current else trace(pid)
        r=db.add(pid,'prd',t|b.model_dump()|{'provenance':'human_edited','previous_id':b.base_id},u['name'],c)
    return r
@app.get('/api/projects/{pid}/prd/{rid}/docx')
def export_docx(pid:str,rid:str,u=Depends(user)):
    access(pid,u);r=db.record(rid,pid,'prd');folder=db.FILES/rid;folder.mkdir(exist_ok=True);p=folder/'PRD.docx'
    doc=Document()
    for line in r['data']['content'].splitlines():
        if line.startswith('#'):doc.add_heading(line.lstrip('# '),level=min(3,len(line)-len(line.lstrip('#'))))
        else:doc.add_paragraph(line)
    doc.save(p);return FileResponse(p,filename='PRD.docx')
@app.get('/api/projects/{pid}/prd/{rid}/diff')
def prd_diff(pid:str,rid:str,u=Depends(user)):
    access(pid,u);candidate=db.record(rid,pid)
    if candidate['kind'] not in ('prd','prd_candidate'):raise ValueError('无效文档')
    current=db.latest(pid,'prd')
    before=current['data']['content'] if current else ''
    return {'base_id':current['id'] if current else '', 'diff':'\n'.join(difflib.unified_diff(before.splitlines(),candidate['data']['content'].splitlines(),fromfile='当前保存版本',tofile='候选版本',lineterm=''))}
@app.post('/api/projects/{pid}/prd/import')
async def import_prd(pid:str,file:UploadFile=File(...),u=Depends(user)):
    access(pid,u,roles=['owner','product']);blob=await file.read(5_000_001)
    if len(blob)>5_000_000:raise ValueError('PRD 最大 5 MB')
    if not (file.filename or '').lower().endswith('.docx'):raise ValueError('仅支持 DOCX 可编辑内容导入')
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            if sum(i.file_size for i in z.infolist())>20_000_000:raise ValueError('DOCX 解压内容超过限制')
        d=Document(io.BytesIO(blob));content='\n\n'.join(p.text for p in d.paragraphs)
        for table in d.tables:
            for row in table.rows:content+='\n'+' | '.join(c.text for c in row.cells)
    except (zipfile.BadZipFile,KeyError):raise ValueError('DOCX 文件无效')
    current=required(pid,'prd');t={k:current['data'][k] for k in ('baseline_id','proposal_id','profile_id','need_ids')}
    r=db.add(pid,'prd_candidate',t|{'content':content,'provenance':'uploaded_docx','filename':file.filename,'base_id':current['id']},u['name'])
    folder=db.FILES/r['id'];folder.mkdir();path=folder/'original.docx';path.write_bytes(blob);register_file(pid,r['id'],path)
    return r
class Prototype(s.Strict):
    pages:list[dict]=Field(min_length=1,max_length=12)
@app.post('/api/projects/{pid}/prototype')
def prototype(pid:str,b:Prototype,u=Depends(user)):
    access(pid,u,write=True);return db.add(pid,'prototype',trace(pid)|b.model_dump()|{'provenance':'editable_template'},u['name'])

def cad_record(pid,params,t,u,note,parent=None,operation=None):
    folder=db.FILES/db.uid()
    with cad_lock:checks=generate_cad(params,folder)
    result=db.add(pid,'cad',t|{'parameters':params,'checks':checks,'note':note,'parent_id':parent,'operation_id':operation,'provenance':'real_cad','status':'engineering_draft'},u['name'])
    files=[register_file(pid,result['id'],f) for f in folder.iterdir()]
    # File references live in immutable child record, never mutate historical CAD data.
    db.add(pid,'cad_files',{'cad_id':result['id'],'files':files},u['name'])
    return result
@app.post('/api/projects/{pid}/cad')
def cad(pid:str,b:s.CADRequest,u=Depends(user)):
    access(pid,u,roles=['owner','product','engineering'])
    if not b.confirmed:raise ValueError('请确认概念尺寸后再建模')
    p=b.parameters.model_dump();validate_cad(p);t=trace(pid)
    return submit(pid,'真实 CAD 建模',{'parameters':p,**t},lambda:cad_record(pid,p,t,u,b.note))
class CADChat(s.Strict):
    message:str=Field(min_length=2,max_length=2000)
    mode:str=Field(default='rules',pattern='^(rules|live)$')
class CADPatch(s.Strict):
    parameters:s.CADParams
    explanation:str
@app.post('/api/projects/{pid}/cad/{rid}/propose')
def cad_propose(pid:str,rid:str,b:CADChat,u=Depends(user)):
    access(pid,u,roles=['owner','product','engineering']);r=db.record(rid,pid,'cad');old=r['data']['parameters'];p=old.copy()
    if b.mode=='live':
        patch=adapters.model_json('只修改明确要求的参数，未提及参数保留；不能执行代码。只支持当前模板参数。',{'parameters':p,'instruction':b.message},CADPatch);p=patch['parameters']
    else:
        patterns=[('speaker_width',r'(?:扬声器|喇叭)(?:区域)?(?:加宽|增加)\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)'),('depth',r'(?:外壳)?深度(?:改为|设为)\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)'),('screen_width',r'屏幕宽度(?:改为|设为)\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)')]
        matched=False
        for key,pattern in patterns:
            m=re.search(pattern,b.message,re.I)
            if m:p[key]=old[key]+float(m.group(1)) if key=='speaker_width' else float(m.group(1));matched=True
        if not matched:raise ValueError('规则解析器目前支持：“扬声器区域加宽 20 mm”“深度改为 65 mm”“屏幕宽度改为 130 mm”。其他指令请配置模型或直接创建新参数版。')
    validate_cad(p)
    changes={k:{'before':old[k],'after':v} for k,v in p.items() if old[k]!=v}
    if not changes:raise ValueError('参数没有变化')
    folder=db.FILES/db.uid()
    with cad_lock:checks=generate_cad(p,folder)
    op=db.add(pid,'cad_operation',{'cad_id':rid,'instruction':b.message,'parameters':p,'changes':changes,'checks':checks,'provenance':'model' if b.mode=='live' else 'rules','status':'preview_only','impacts':['外壳包络随屏幕/扬声器宽度变化','显示区保持原值，除非指令明确修改','安装孔随外壳边界移动'],'folder':str(folder)},u['name'])
    preview=register_file(pid,op['id'],folder/'drawing.svg')
    return {'operation':op,'preview':preview}
@app.post('/api/projects/{pid}/cad/operations/{rid}/apply')
def cad_apply(pid:str,rid:str,u=Depends(user)):
    access(pid,u,roles=['owner','product','engineering']);op=db.record(rid,pid,'cad_operation');base=db.record(op['data']['cad_id'],pid,'cad')
    if any(r['data'].get('operation_id')==rid for r in db.rows(pid,'cad')):raise HTTPException(409,'该修改已应用')
    t={k:base['data'][k] for k in ('baseline_id','proposal_id','profile_id','need_ids')}
    return submit(pid,'应用 CAD 参数变更',{'operation_id':rid},lambda:cad_record(pid,op['data']['parameters'],t,u,op['data']['instruction'],base['id'],rid))
@app.post('/api/projects/{pid}/cad/{rid}/restore')
def cad_restore(pid:str,rid:str,u=Depends(user)):
    access(pid,u,roles=['owner','product','engineering']);base=db.record(rid,pid,'cad');t={k:base['data'][k] for k in ('baseline_id','proposal_id','profile_id','need_ids')}
    return submit(pid,'恢复 CAD 历史参数',{'from':rid},lambda:cad_record(pid,base['data']['parameters'],t,u,'恢复历史参数，新增版本',rid))
@app.post('/api/projects/{pid}/files')
async def upload(pid:str,file:UploadFile=File(...),u=Depends(user)):
    access(pid,u,write=True);name=Path(file.filename or 'file').name;ext=Path(name).suffix.lower()
    if ext not in ('.step','.stp','.svg','.pdf','.txt','.json','.docx','.png','.jpg'):raise ValueError('不支持该文件类型')
    blob=await file.read(20_000_001)
    if len(blob)>20_000_000:raise ValueError('文件最大 20 MB')
    r=db.add(pid,'upload',{'name':name,'format':ext,'provenance':'user_upload','editability':'归档附件；中性几何不恢复特征树，未进行参数建模','preview_status':'未解析'},u['name'])
    folder=db.FILES/r['id'];folder.mkdir();path=folder/name;path.write_bytes(blob)
    f=register_file(pid,r['id'],path)
    db.add(pid,'upload_file',{'upload_id':r['id'],'file':f},u['name']);return f
@app.get('/api/files/{fid}')
def download(fid:str,inline:bool=False,u=Depends(user)):
    with db.connect() as c:r=c.execute('SELECT * FROM files WHERE id=?',(fid,)).fetchone()
    if not r:raise HTTPException(404,'文件不存在')
    access(r['project_id'],u)
    stored=Path(r['path'])
    if not stored.is_absolute():stored=db.ROOT/stored
    elif not stored.exists():
        # Legacy records used host absolute paths; preserve downloads after mounting data in Docker.
        stored=db.FILES/stored.parent.name/stored.name
    if not stored.is_file():raise HTTPException(404,'文件不存在')
    return FileResponse(stored,media_type=r['mime'],filename=r['name'],content_disposition_type='inline' if inline and r['mime'] in ('image/svg+xml','application/pdf','text/plain','application/json') else 'attachment',headers={'Content-Security-Policy':"sandbox; default-src 'none'; style-src 'unsafe-inline'"})
@app.get('/api/jobs/{jid}')
def job(jid:str,u=Depends(user)):
    with db.connect() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
    if not r:raise HTTPException(404,'任务不存在')
    access(r['project_id'],u);d=dict(r)
    for key in ('input','result'):d[key]=json.loads(d[key]) if d[key] else None
    return d
@app.get('/api/assets')
def assets(q:str='',u=Depends(user)):
    with db.connect() as c:rs=c.execute("SELECT r.*,p.name project_name FROM records r JOIN members m ON m.project_id=r.project_id JOIN projects p ON p.id=r.project_id WHERE m.user_id=? AND r.kind IN ('need','proposal','prd','cad','review','feedback','source','validation','reference') ORDER BY r.rowid DESC",(u['id'],)).fetchall()
    return [dict(r)|{'data':json.loads(r['data'])} for r in rs if q.lower() in r['data'].lower()][:100]
class Ref(s.Strict):source_project_id:str;source_record_id:str;conditions:str=Field(min_length=2)
@app.post('/api/projects/{pid}/references')
def reference(pid:str,b:Ref,u=Depends(user)):
    access(pid,u,write=True);access(b.source_project_id,u);r=db.record(b.source_record_id,b.source_project_id)
    return db.add(pid,'reference',b.model_dump()|{'source_kind':r['kind'],'status':'reference_only_not_confirmed'},u['name'])
class Validation(s.Strict):
    target_id:str
    result:str=Field(min_length=2,max_length=5000)
    status:str=Field(pattern='^(待验证|通过|失败)$')
@app.post('/api/projects/{pid}/validations')
def validation(pid:str,b:Validation,u=Depends(user)):
    access(pid,u,write=True);db.record(b.target_id,pid);return db.add(pid,'validation',b.model_dump(),u['name'])
@app.get('/api/projects/{pid}/export')
def export(pid:str,u=Depends(user)):
    access(pid,u);return workspace(pid,u)

DIST=Path(__file__).resolve().parent.parent/'frontend'/'dist'
if DIST.exists():app.mount('/',StaticFiles(directory=DIST,html=True),name='ui')
