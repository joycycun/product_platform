import {useEffect,useState} from 'react';
type Account={id:string;name:string;role:string;active:boolean;project_ids:string[]};
type Project={id:string;name:string};
export default function Accounts({request}:{request:(path:string,body?:any)=>Promise<any>}){
 const [accounts,setAccounts]=useState<Account[]>([]),[projects,setProjects]=useState<Project[]>([]);
 const [id,setId]=useState(''),[name,setName]=useState(''),[password,setPassword]=useState(''),[role,setRole]=useState('sales'),[active,setActive]=useState(true),[selected,setSelected]=useState<string[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function load(){const data=await request('/admin/accounts');setAccounts(data.accounts);setProjects(data.projects)}
 useEffect(()=>{load().catch(e=>setError(e.message))},[]);
 function reset(){setId('');setName('');setPassword('');setRole('sales');setActive(true);setSelected([])}
 function edit(a:Account){setId(a.id);setName(a.name);setPassword('');setRole(a.role);setActive(Boolean(a.active));setSelected(a.project_ids);setNotice('');setError('')}
 async function save(e:React.FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError('');setNotice('');try{
   const body={role,active,project_ids:selected,password,...(!id?{name}:{})};
   await request('/admin/accounts'+(id?'/'+id:''),body);await load();reset();setNotice('账户配置已保存。修改后的账户需要重新登录。');
 }catch(e:any){setError(e.message)}finally{setBusy(false)}}
 return <><p>创建销售、市场登录账户，并指定可访问的项目。未分配项目的账户无法查看项目资料。</p>
 {error&&<div className="error" role="alert">{error}</div>}{notice&&<div className="notice" role="status">{notice}</div>}
 <div className="grid"><article><h3>{id?'编辑账户':'添加账户'}</h3><form onSubmit={save}>
 <label>登录账户<input required minLength={2} maxLength={80} autoComplete="off" value={name} disabled={!!id} onChange={e=>setName(e.target.value)}/></label>
 <label>{id?'重置密码（留空保留原密码）':'初始密码（至少 8 位）'}<input type="password" required={!id} minLength={8} maxLength={200} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>
 <label>账户角色<select value={role} onChange={e=>setRole(e.target.value)}><option value="sales">销售</option><option value="marketing">市场</option></select></label>
 <label className="check"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/>启用账户</label>
 <fieldset><legend>可访问项目</legend>{projects.length?projects.map(p=><label className="check" key={p.id}><input type="checkbox" checked={selected.includes(p.id)} onChange={e=>setSelected(e.target.checked?[...selected,p.id]:selected.filter(x=>x!==p.id))}/>{p.name}</label>):<p>当前没有项目，可先创建账户，之后再分配。</p>}</fieldset>
 <p>销售、市场可录入反馈、搜索及补充资料；方案批准、PRD 保存和 工程文件上传与评审由产品或研发负责。</p>
 <button disabled={busy}>{busy?'正在保存…':id?'保存配置':'创建账户'}</button>{id&&<button type="button" disabled={busy} onClick={reset}>取消编辑</button>}
 </form></article><article><h3>已有账户 · {accounts.length}</h3>{accounts.map(a=><div className="account-row" key={a.id}><div><strong>{a.name}</strong><p>{({admin:'管理员',sales:'销售',marketing:'市场',member:'项目成员'} as Record<string,string>)[a.role]||a.role} · {a.active?'启用':'停用'}</p><small>{a.project_ids.length} 个项目</small></div>{['sales','marketing'].includes(a.role)&&<button disabled={busy} onClick={()=>edit(a)}>配置</button>}</div>)}</article></div></>
}
