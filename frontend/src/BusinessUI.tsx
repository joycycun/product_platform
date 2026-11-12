import {useState} from 'react';

export type BusinessRow={id:string;kind:string;data:any;created_at:string;author?:string};

const fieldNames:Record<string,string>={
 industry:'行业',scenario:'使用场景',region:'地区',scale:'客户规模',buyer:'采购角色',needs:'关键需求',budget:'预算范围',exclusions:'排除条件',
 reason:'选择理由',facts:'产品页事实',unknowns:'待核实事项',text:'内容',quote:'原文引句',status:'状态',
 title:'标题',description:'需求说明',allocation:'实现拆解',software:'软件',hardware:'硬件',interface:'软硬件接口',acceptance:'联合验收',
 name:'方案名称',features:'功能项',relationship:'与 Premier 的关系',premier_behavior:'Premier 做法',our_behavior:'建议做法',rationale:'设计依据',risks:'风险',
 discipline:'评审专业',conclusion:'评审结论',comment:'评审意见',pages:'页面流程',content:'内容',action:'操作',
 url:'产品页',locator:'原文位置',summary:'资料摘要',source:'来源',source_system:'来源系统',source_version:'来源版本',version:'版本',conditions:'适用条件',
 target_users:'目标用户与场景',core_value:'核心价值',positioning:'定位与价位',design_principles:'体验和外观原则',differentiation:'差异化重点',constraints:'必须满足的约束',out_of_scope:'明确不做的事项'
};
const hiddenFields=new Set(['id','competitor_id','source_id','source_record_id','source_project_id','target_id','baseline_id','tone_id','profile_id','proposal_id','prd_id','previous_id','feedback_ids','need_ids','knowledge_ids','impacted_ids','review_ids','asset_id','upload_id','model_verified','source_kind','source_title','query','provenance','confirmed_by','reviewed_by','supersedes','collected_at','status','confirmed','generation_mode']);
const labels=(key:string)=>fieldNames[key]||key.replaceAll('_',' ');
const link=(raw:string)=>{const match=raw?.match(/\((https?:\/\/[^)]+)\)/);const value=match?.[1]||raw;try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)?url.href:''}catch{return ''}};

export function readableDocument(content:string):string{
 return content.replace(/\{\n\s*"(?:industry|target_users|baseline_id)"[\s\S]*?\n\}/g,block=>{
  try{const data=JSON.parse(block);if(data.baseline_id&&data.proposal_id)return '- 详细对象关联保存在平台项目记录中。';
   const fields=Object.entries(data).filter(([key,value])=>fieldNames[key]&&value!=null&&typeof value!=='object'&&value!=='');
   return fields.map(([key,value])=>`- **${labels(key)}**：${value}`).join('\n')||block
  }catch{return block}
 });
}

export function recordTitle(row:BusinessRow):string{
 const d=row.data;
 if(row.kind==='baseline')return `Premier · ${d.competitor?.brand||''} ${d.competitor?.model||''}`;
 if(row.kind==='facts')return '竞品事实提取';
 if(row.kind==='feedback')return '客户反馈';
 if(row.kind==='review')return `${d.discipline||'专业'}评审`;
 if(row.kind==='source')return '产品资料原文';
 if(row.kind==='profile')return '目标客户画像';
 if(row.kind==='product_tone')return '已确认产品基调';
 if(row.kind==='selection')return '最终方案选择';
 if(row.kind==='prd'||row.kind==='prd_candidate')return 'PRD 文档';
 if(row.kind==='upload')return d.name||'设计文件';
 return d.title||d.name||d.model||'项目记录';
}

export function RecordContent({row,records=[]}:{row:BusinessRow;records?:BusinessRow[]}){
 const d=row.data;
 if(row.kind==='baseline')return <div className="record-content"><p><b>{d.competitor?.brand} {d.competitor?.model}</b> · {d.reason}</p>{link(d.competitor?.url||'')&&<a href={link(d.competitor.url)} target="_blank" rel="noreferrer">查看产品官网 ↗</a>}{d.competitor?.summary&&<details><summary>搜索摘要</summary><p className="source-text">{d.competitor.summary}</p></details>}{(d.facts||[]).map((f:any,i:number)=><p key={i}><b>{f.status==='verified'?'已核实':'待核实'}</b> · {f.text}<br/><small>原文：{f.quote}</small></p>)}{!!d.unknowns?.length&&<p>待核实：{d.unknowns.join('；')}</p>}</div>;
 if(row.kind==='need')return <div className="record-content"><p>{d.description}</p><span className="badge">{d.status==='confirmed'?'已确认':d.status==='rejected'?'已拒绝':'待产品经理确认'}</span>{(d.feedback_ids||[]).length?<p>客户反馈：{d.feedback_ids.map((id:string)=>records.find(x=>x.id===id)?.data.quote||'历史反馈').join('；')}</p>:<p>依据：已确认产品基调与 Premier；待客户验证。</p>}<dl className="field-list">{Object.entries(d.allocation||{}).map(([key,value])=><div key={key}><dt>{labels(key)}</dt><dd>{String(value)}</dd></div>)}</dl></div>;
 if(row.kind==='proposal')return <div className="record-content">{(d.features||[]).map((f:any,i:number)=><section className="feature-summary" key={i}><h4>{f.name} · {f.relationship}</h4><p><b>Premier 做法：</b>{f.premier_behavior}</p><p><b>建议做法：</b>{f.our_behavior}</p><p><b>依据：</b>{f.rationale}</p><p><b>风险：</b>{f.risks}</p></section>)}</div>;
 if(row.kind==='facts')return <div className="record-content">{(d.facts||[]).map((f:any,i:number)=><p key={i}>{f.text}<br/><small>原文：{f.quote}</small></p>)}</div>;
 if(row.kind==='source')return <div className="record-content">{link(d.url||'')&&<a href={link(d.url)} target="_blank" rel="noreferrer">打开来源 ↗</a>}<details><summary>查看产品页原文</summary><div className="source-text">{d.text}</div></details></div>;
 if(row.kind==='feedback')return <div className="record-content"><blockquote>{d.quote}</blockquote><p>来源：{d.source}{d.scenario?' · 场景：'+d.scenario:''}</p></div>;
 if(row.kind==='review')return <div className="record-content"><span className="badge">{d.conclusion}</span><p>{d.comment}</p></div>;
 if(row.kind==='knowledge')return <div className="record-content"><p className="source-text">{d.content}</p><small>来源：{d.source_system||'人工录入'} · 版本：{d.source_version||'1'}</small></div>;
 if(row.kind==='prd'||row.kind==='prd_candidate')return <div className="source-text">{readableDocument(d.content||'')}</div>;
 if(row.kind==='profile'||row.kind==='product_tone')return <dl className="field-list">{Object.entries(d).filter(([key,value])=>!hiddenFields.has(key)&&value!=null&&typeof value!=='object'&&value!=='').map(([key,value])=><div key={key}><dt>{labels(key)}</dt><dd>{String(value)}</dd></div>)}</dl>;
 if(row.kind==='reference')return <p>适用条件：{d.conditions||'待确认'}</p>;
 return <dl className="field-list">{Object.entries(d).filter(([key,value])=>!hiddenFields.has(key)&&value!=null&&typeof value!=='object'&&value!=='').map(([key,value])=><div key={key}><dt>{labels(key)}</dt><dd>{String(value)}</dd></div>)}</dl>;
}

const editorHidden=new Set(['competitor_id','source_id','target_id','feedback_ids','need_ids']);
const longText=new Set(['description','content','text','summary','quote','reason','rationale','risks','comment','software','hardware','interface','acceptance','premier_behavior','our_behavior']);

export function StructuredEditor({value,onSave,label='保存新版本'}:{value:any;onSave:(data:any)=>void;label?:string}){
 const [data,setData]=useState<any>(()=>structuredClone(value));
 function update(path:(string|number)[],next:any){setData((old:any)=>{const copy=structuredClone(old);let target=copy;for(const part of path.slice(0,-1))target=target[part];target[path.at(-1)!]=next;return copy})}
 function field(key:string,current:any,path:(string|number)[]):any{
  if(editorHidden.has(key))return null;
  if(Array.isArray(current)){
   if(key==='unknowns'||current.length>0&&current.every(x=>typeof x==='string'))return <label key={path.join('.')}>{labels(key)}（每行一项）<textarea aria-label={labels(key)} value={current.join('\n')} onChange={e=>update(path,e.target.value.split('\n').map(x=>x.trim()).filter(Boolean))}/></label>;
   return <fieldset key={path.join('.')}><legend>{labels(key)}</legend>{current.map((item:any,index:number)=><div className="editor-group" key={index}><h4>{labels(key)} {index+1}</h4>{Object.entries(item).map(([child,val])=>field(child,val,[...path,index,child]))}{key==='pages'&&<button type="button" className="secondary" onClick={()=>update(path,current.filter((_:any,i:number)=>i!==index))}>删除页面</button>}</div>)}{key==='pages'&&<button type="button" className="secondary" onClick={()=>update(path,[...current,{title:'新页面',content:'待填写',action:'下一步'}])}>添加页面</button>}</fieldset>;
  }
  if(current&&typeof current==='object')return <fieldset key={path.join('.')}><legend>{labels(key)}</legend>{Object.entries(current).map(([child,val])=>field(child,val,[...path,child]))}</fieldset>;
  if(key==='status')return <label key={path.join('.')}>{labels(key)}<select aria-label={labels(key)} value={String(current)} onChange={e=>update(path,e.target.value)}>{(current==='verified'||current==='pending'&&path.includes('facts')?['pending','verified']:['pending','confirmed','rejected']).map(x=><option key={x} value={x}>{x==='pending'&&path.includes('facts')?'待核实':({pending:'待确认',verified:'已核实',confirmed:'已确认',rejected:'已拒绝'} as any)[x]}</option>)}</select></label>;
  if(key==='relationship')return <label key={path.join('.')}>{labels(key)}<select aria-label={labels(key)} value={String(current)} onChange={e=>update(path,e.target.value)}>{['保留','修改','删除','新增'].map(x=><option key={x}>{x}</option>)}</select></label>;
  if(key==='conclusion')return <label key={path.join('.')}>{labels(key)}<select aria-label={labels(key)} value={String(current)} onChange={e=>update(path,e.target.value)}>{['待评估','通过','否决'].map(x=><option key={x}>{x}</option>)}</select></label>;
  const labelText=labels(key),text=String(current??'');
  return <label key={path.join('.')}>{labelText}{longText.has(key)||text.length>100?<textarea aria-label={labelText} placeholder={key==='text'?'请粘贴可核对的资料原文，至少二十个字符。':undefined} value={text} onChange={e=>update(path,e.target.value)}/>:<input aria-label={labelText} value={text} onChange={e=>update(path,e.target.value)}/>}</label>;
 }
 return <form className="structured-editor" onSubmit={e=>{e.preventDefault();onSave(data)}}>{Object.entries(data).map(([key,current])=>field(key,current,[key]))}<button type="submit">{label}</button></form>;
}
