import {useEffect,useState} from 'react';
import {RecordContent,recordTitle} from './BusinessUI';
export type Row={id:string;kind:string;data:any;created_at:string;author?:string;project_id?:string;project_name?:string};
type Request=(path:string,body?:any,method?:string)=>Promise<any>;
type Props={pid:string;rows:Row[];role:string;request:Request;refresh:()=>Promise<any>;generationMode?:string;onConfirmed?:()=>void};
const decide=(role:string)=>['owner','product'].includes(role);
const engineer=(role:string)=>['owner','product','engineering'].includes(role);
function useAction(refresh:()=>Promise<any>){
 const [error,setError]=useState(''),[busy,setBusy]=useState(false);
 const run=async(fn:()=>Promise<any>)=>{setError('');setBusy(true);try{const result=await fn();await refresh();return result}catch(e:any){setError(e.message)}finally{setBusy(false)}};
 return {run,busy,error};
}
function ErrorLine({message}:{message:string}){return message?<p className="error" role="alert">{message}</p>:null}
const toneFields=[['target_users','目标用户与场景'],['core_value','核心价值'],['positioning','定位与价位'],['design_principles','体验和外观原则'],['differentiation','差异化重点'],['constraints','必须满足的约束'],['out_of_scope','明确不做的事项'],['rationale','选择与取舍依据']];
export function ProductTone({pid,rows,role,request,refresh,generationMode,onConfirmed}:Props){
 const baseline=rows.filter(r=>r.kind==='baseline').at(-1),tones=rows.filter(r=>r.kind==='product_tone'),current=tones.at(-1);
 const candidate=rows.filter(r=>r.kind==='product_tone_candidate'&&r.data.baseline_id===baseline?.id).at(-1);
 const [draft,setDraft]=useState<Record<string,string>>({}),[confirm,setConfirm]=useState(false);const {run,busy,error}=useAction(refresh);
 useEffect(()=>{setDraft(current&&current.data.baseline_id===baseline?.id?current.data:candidate?.data||{});setConfirm(false)},[pid,current?.id,baseline?.id,candidate?.id]);
 const valid=current?.data.baseline_id===baseline?.id&&!!baseline;
 return <article><span className="badge">产品经理决策</span><h3>确认产品基调</h3><p>结合公司知识、竞品和客户反馈确认方向。功能及软硬件拆解将引用这一版本；最终方案仍由产品经理决定。</p>
 <p>{valid?'当前基调已确认':'尚未确认当前 premier 对应的产品基调'}</p><ErrorLine message={error}/>
 {candidate&&<details open><summary>Premier 官网分析草稿 · 请核对来源</summary><p>{candidate.data.premier_summary}</p>{candidate.data.url&&<a href={candidate.data.url} target="_blank" rel="noreferrer">打开 Premier 产品页 ↗</a>}{candidate.data.source_id&&<p>网页正文已存入项目资料。</p>}{(candidate.data.facts||[]).map((f:any,i:number)=><p key={i}>{f.text}<br/><small>原文引句：{f.quote}</small></p>)}<p>待核实：{(candidate.data.unknowns||[]).join('；')}</p></details>}
 <form onSubmit={e=>{e.preventDefault();run(()=>request(`/projects/${pid}/product-tones`,{...Object.fromEntries(toneFields.map(([key])=>[key,draft[key]||''])),baseline_id:baseline?.id,confirmed:confirm,generation_mode:generationMode||'live'})).then(result=>{if(result)onConfirmed?.()})}}>
 <div className="grid">{toneFields.map(([key,label])=><label key={key}>{label}<textarea aria-label={label} required minLength={2} value={draft[key]||''} onChange={e=>setDraft({...draft,[key]:e.target.value})}/></label>)}</div>
 <label className="check"><input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)}/>我已核对依据，确认此版产品基调</label>
 <button disabled={busy||!decide(role)||!baseline||!confirm}>确认并保存基调版本</button></form>
 {!!tones.length&&<section className="tone-history"><h4>已确认的基调版本</h4>{tones.slice().reverse().map((tone,i)=><details key={tone.id}><summary>{tone.id===current?.id?'当前版本':'历史版本'} · {tone.data.core_value||'未填写核心价值'} · {tone.created_at.slice(0,16).replace('T',' ')}</summary><p>{tone.author} · {tone.created_at}</p><RecordContent row={tone} records={rows}/>{tone.data.impacted_ids?.length>0&&<p>需要重新评审的历史对象：{tone.data.impacted_ids.length} 项</p>}{decide(role)&&<button type="button" className="secondary danger" disabled={busy} onClick={()=>run(()=>request(`/projects/${pid}/product-tones/${tone.id}`,undefined,'DELETE'))}>删除该基调版本</button>}</details>)}</section>}</article>
}
export function CompanyKnowledge({pid,rows,role,request,refresh}:Props){
 const [q,setQ]=useState(''),[assets,setAssets]=useState<Row[]>([]);const {run,busy,error}=useAction(refresh);
 const load=async()=>setAssets(await request('/assets?q='+encodeURIComponent(q)));
 useEffect(()=>{load().catch(()=>{})},[pid]);
 return <><p>通过接口、文件和人工资料积累公司产品知识。搜索仅返回有权限的项目；引用保留来源与适用条件。</p><ErrorLine message={error}/>
 <div className="toolbar"><input aria-label="公司知识搜索" placeholder="搜索公司产品、客户反馈、评审与设计文件" value={q} onChange={e=>setQ(e.target.value)}/><button onClick={()=>run(load)}>搜索公司产品库</button></div>
 {!pid&&<p>选择项目后可接入资料，或将其他授权项目的资料引用到当前项目。</p>}
 {pid&&role!=='viewer'&&<div className="grid"><article><h3>接入公司产品资料</h3><p>接口与此表单使用相同的来源系统、外部编号和版本去重规则。</p><form onSubmit={e=>{e.preventDefault();const form=e.currentTarget;run(async()=>{await request(`/projects/${pid}/knowledge`,Object.fromEntries(new FormData(form)));await load();form.reset()})}}>
 {([['title','资料标题',''],['source_system','来源系统','manual'],['external_id','来源对象编号',''],['source_version','来源版本','1'],['locator','原文位置或链接','']] as const).map(([name,label,value])=><label key={name}>{label}<input name={name} defaultValue={value} required={name!=='locator'}/></label>)}
 <label>资料原文<textarea name="content" required minLength={2}/></label><button disabled={busy}>存入公司产品库</button></form></article>
 <article><h3>上传已有产品资料</h3><p>文本、Markdown、JSON 和 DOCX 可提取文字。PDF、图片和工程文件保留原件；未解析文件不会被声称已理解。</p>
 <input aria-label="上传公司产品资料" type="file" accept=".txt,.md,.json,.docx,.pdf,.png,.jpg,.jpeg,.svg" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f){const b=new FormData();b.append('file',f);b.append('metadata',JSON.stringify({purpose:'knowledge',note:'公司产品资料接入'}));run(async()=>{await request(`/projects/${pid}/files`,b);await load()})}}}/>
 <h3>当前项目已引用的资料</h3>{rows.filter(r=>r.kind==='reference').map(r=><details key={r.id}><summary>已引用资料</summary><RecordContent row={r} records={rows}/></details>)}</article></div>}
 {assets.map(r=><article key={r.id}><span className="badge">{r.project_name} · {recordTitle(r)}</span><h3>{recordTitle(r)}</h3><details><summary>查看内容与来源</summary><RecordContent row={r} records={rows}/><small>{r.created_at}</small></details>{pid&&role!=='viewer'&&<button disabled={busy} onClick={()=>run(async()=>{const conditions=prompt('请说明该资料用于当前项目的适用条件','作为参考材料，需结合本项目重新确认');if(conditions)await request(`/projects/${pid}/references`,{source_project_id:r.project_id,source_record_id:r.id,conditions})})}>引用到当前项目</button>}</article>)}</>
}
const emptyFile={previous_id:'',note:'首次上传',need_ids:[] as string[],proposal_id:'',hardware_feature_indexes:[] as number[],prd_id:'',preview_of_id:''};
export function DesignFiles({pid,rows,role,request,refresh}:Props){
 const uploads=rows.filter(r=>r.kind==='upload'),plans=rows.filter(r=>r.kind==='proposal'),allNeeds=rows.filter(r=>r.kind==='need'),prds=rows.filter(r=>r.kind==='prd');
 const supersededNeeds=new Set(allNeeds.map(r=>r.data.supersedes).filter(Boolean));
 const needs=allNeeds.filter(r=>!supersededNeeds.has(r.id));
 const files=new Map(rows.filter(r=>r.kind==='upload_file').map(r=>[r.data.upload_id,r.data.file]));
 const latest=new Map<string,Row>();uploads.forEach(r=>latest.set(r.data.asset_id||r.id,r));
 const [meta,setMeta]=useState({...emptyFile}),[file,setFile]=useState<File>(),[preview,setPreview]=useState<any>();const {run,busy,error}=useAction(refresh);
 const plan=plans.find(r=>r.id===meta.proposal_id);const current=rows.find(r=>r.kind==='selection'&&r.data.proposal_id===meta.proposal_id);
 function selectParent(id:string){const p=uploads.find(r=>r.id===id);setMeta(p?{...emptyFile,...Object.fromEntries(Object.keys(emptyFile).map(k=>[k,p.data[k]??(emptyFile as any)[k]])),previous_id:id,note:''}:{...emptyFile})}
 return <><p>CAD、STEP、结构图由设计人员在专业工具中完成。平台负责上传、下载、可用格式预览、版本和评审；修改后上传新版本。</p><ErrorLine message={error}/>
 {engineer(role)&&<article><h3>上传设计文件</h3><form onSubmit={e=>{e.preventDefault();if(!file)return;const b=new FormData();b.append('file',file);b.append('metadata',JSON.stringify({...meta,purpose:'design'}));run(async()=>{await request(`/projects/${pid}/files`,b);setMeta({...emptyFile});setFile(undefined)})}}>
 <label>版本归属<select aria-label="版本归属" value={meta.previous_id} onChange={e=>selectParent(e.target.value)}><option value="">创建新文件</option>{Array.from(latest.values()).map(r=><option key={r.id} value={r.id}>{r.data.name} · v{r.data.version||1} 的新版本</option>)}</select></label>
 <label>设计原件或预览附件<input aria-label="设计文件" type="file" required onChange={e=>setFile(e.target.files?.[0])}/></label>
 <label>变更说明<input required minLength={2} value={meta.note} onChange={e=>setMeta({...meta,note:e.target.value})}/></label>
 <div className="grid"><label>关联功能方案<select aria-label="关联功能方案" value={meta.proposal_id} onChange={e=>setMeta({...meta,proposal_id:e.target.value,hardware_feature_indexes:[],need_ids:[],prd_id:''})}><option value="">暂不关联</option>{plans.map(r=><option key={r.id} value={r.id}>{r.data.name}</option>)}</select></label>
 <label>关联 PRD 版本<select aria-label="关联 PRD 版本" value={meta.prd_id} onChange={e=>setMeta({...meta,prd_id:e.target.value})}><option value="">暂不关联</option>{prds.filter(r=>!meta.proposal_id||r.data.proposal_id===meta.proposal_id).map((r,i)=><option key={r.id} value={r.id}>PRD 版本 {i+1} · {r.created_at.slice(0,10)}</option>)}</select></label></div>
 {plan&&<fieldset><legend>关联硬件功能（方案内功能及其硬件拆解）</legend>{plan.data.features.map((f:any,i:number)=><label className="check" key={i}><input type="checkbox" checked={meta.hardware_feature_indexes.includes(i)} onChange={e=>{const indexes=e.target.checked?[...meta.hardware_feature_indexes,i]:meta.hardware_feature_indexes.filter(n=>n!==i);setMeta({...meta,hardware_feature_indexes:indexes,need_ids:Array.from(new Set(indexes.flatMap(j=>plan.data.features[j].need_ids))) as string[]})}}/>{f.name}</label>)}<small>{current?'已被产品选择的方案':'该方案尚未被选为最终方案'}</small></fieldset>}
 <fieldset><legend>关联项目需求</legend>{needs.map(r=><label className="check" key={r.id}><input type="checkbox" checked={meta.need_ids.includes(r.id)} onChange={e=>setMeta({...meta,need_ids:e.target.checked?[...meta.need_ids,r.id]:meta.need_ids.filter(id=>id!==r.id)})}/>{r.data.title}</label>)}</fieldset>
 <label>这是哪个原件版本的预览附件？<select aria-label="这是哪个原件版本的预览附件？" value={meta.preview_of_id} onChange={e=>setMeta({...meta,preview_of_id:e.target.value})}><option value="">本文件为原件</option>{uploads.map(r=><option key={r.id} value={r.id}>{r.data.name} · v{r.data.version||1}</option>)}</select></label>
 <button disabled={busy||!file}>上传并保存新版本</button></form></article>}
 {preview&&<article><button onClick={()=>setPreview(undefined)}>关闭预览</button><h3>{preview.name}</h3>{/\.(png|jpe?g|svg)$/i.test(preview.name)?<img className="drawing" src={preview.url+'?inline=true'} alt={preview.name}/>:<iframe className="file-preview" sandbox="" title={preview.name} src={preview.url+'?inline=true'}/>}</article>}
 {Array.from(latest.entries()).map(([asset,r])=><article key={asset}><h3>{r.data.name}</h3><p>最新版本 v{r.data.version||1} · {r.author} · {r.created_at}</p>{uploads.filter(v=>(v.data.asset_id||v.id)===asset).slice().reverse().map(v=>{const f=files.get(v.id),reviews=rows.filter(x=>x.kind==='review'&&x.data.target_id===v.id);return <details key={v.id} open={v.id===r.id}><summary>v{v.data.version||1} · {v.data.note||'历史上传'} · {reviews.at(-1)?.data.conclusion||'待评审'}</summary>
 <p>{v.author} · {v.created_at}</p>{f&&<><a href={f.url}>下载原件</a>{v.data.preview_status==='available'?<button onClick={()=>setPreview(f)}>预览</button>:<span>暂不支持在线预览，请下载到专业工具查看</span>}</>}
 <p>方案：{plans.find(x=>x.id===v.data.proposal_id)?.data.name||'未关联'}；硬件功能：{(v.data.hardware_feature_indexes||[]).map((i:number)=>plans.find(x=>x.id===v.data.proposal_id)?.data.features[i]?.name||'待核实').join('、')||'未关联'}</p><p>需求：{(v.data.need_ids||[]).map((id:string)=>allNeeds.find(x=>x.id===id)?.data.title||'历史需求').join('、')||'未关联'}；PRD：{prds.find(x=>x.id===v.data.prd_id)?'已关联版本':'未关联'}</p>
 {v.data.preview_of_id&&<p>预览原件版本：{uploads.find(x=>x.id===v.data.preview_of_id)?.data.name||'历史原件'}</p>}{reviews.map(x=><p key={x.id}>{x.author} · {x.data.discipline} · {x.data.conclusion}：{x.data.comment}</p>)}
 {engineer(role)&&<form onSubmit={e=>{e.preventDefault();const form=e.currentTarget;run(async()=>{await request(`/projects/${pid}/reviews`,{...Object.fromEntries(new FormData(form)),target_id:v.id});form.reset()})}}><label>评审专业<input name="discipline" required defaultValue="硬件 / 结构"/></label><label>评审结论<select aria-label="评审结论" name="conclusion"><option>待评估</option><option>通过</option><option>否决</option></select></label><label>评审意见<textarea name="comment" required minLength={2}/></label><button disabled={busy}>提交该版本评审</button></form>}</details>})}</article>)}
 {rows.filter(r=>r.kind==='cad_files').length>0&&<details><summary>历史 CAD 文件归档（保留下载）</summary>{rows.filter(r=>r.kind==='cad_files').flatMap(r=>r.data.files).map((f:any)=><p key={f.id}><a href={f.url}>{f.name}</a></p>)}</details>}</>
}
