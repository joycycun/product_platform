"""Create an explicitly labelled demo workspace; never invoke real upstream/model services."""
import sys, os, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
import httpx
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=60,trust_env=False) as c:
    def post(path,data=None):
        r=c.post('/api'+path,json=data or {});r.raise_for_status();return r.json()
    def job(result):
        for _ in range(300):
            r=c.get('/api/jobs/'+result['job_id']);r.raise_for_status();j=r.json()
            if j['status']=='completed':return j['result']
            if j['status']=='failed':raise RuntimeError(j['error'])
            time.sleep(.2)
        raise RuntimeError('任务超时，请在工作台查看')
    post('/auth/login',dict(name=os.environ['BOOTSTRAP_USER'],password=os.environ['BOOTSTRAP_PASSWORD']))
    name='【演示】学校走廊带屏 SIP 终端'
    projects=c.get('/api/projects').json()
    if any(p['name']==name for p in projects):
        print('已有同名演示项目，未重复创建');sys.exit(0)
    project=post('/projects',dict(name=name,direction='演示方向：学校走廊带屏 SIP 广播终端',constraints='全部客户、竞品与需求为演示；CAD 为真实概念几何，未完成工程审核'))
    root='/projects/'+project['id']
    post(root+'/profiles',dict(industry='教育',scenario='学校走廊',needs='紧急广播时远距离可见警示'))
    competitor=job(post(root+'/search',dict(mode='demo')))[0]
    post(root+'/baselines',dict(competitor_id=competitor['id'],reason='仅用于演示业务流程，非真实竞品决策'))
    post(root+'/mock-sales')
    post(root+'/feedback',dict(quote='演示反馈：紧急广播时，希望走廊警示灯更醒目。',source='模拟访谈，未接触真实客户',customer_key='mock-sales:DEMO-SCHOOL-001',provenance='demo'))
    need=job(post(root+'/needs/generate',dict(mode='demo')))[0]
    data={k:need['data'][k] for k in ('title','description','feedback_ids','allocation','status')};data['status']='confirmed'
    post(root+'/needs/'+need['id'],data)
    proposal=job(post(root+'/proposals/generate',dict(mode='demo')))[1]
    post(root+'/reviews',dict(target_id=proposal['id'],discipline='演示评审',conclusion='待评估',comment='仅用于验证功能链，不作为工程批准'))
    post(root+'/proposals/'+proposal['id']+'/select')
    prd=job(post(root+'/prd/generate',dict(mode='demo')))
    post(root+'/prd',dict(candidate_id=prd['id'],content=prd['data']['content'],note='演示项目数据生成，非真实模型输出'))
    post(root+'/prototype',dict(pages=[dict(title='设备状态',content='低保真演示：广播与警示状态',action='进入事件详情'),dict(title='事件详情',content='演示优先级与故障反馈',action='返回状态')]))
    cad=job(post(root+'/cad',dict(parameters={},confirmed=True,note='演示项目的人工确认概念尺寸；真实 CAD 几何')))
    operation=post(root+'/cad/'+cad['id']+'/propose',dict(message='扬声器区域加宽 20 mm，屏幕有效显示区不变',mode='rules'))
    job(post(root+'/cad/operations/'+operation['operation']['id']+'/apply'))
    print('演示项目已创建：'+project['id']+'；含 PRD 与两版真实 CAD。')
