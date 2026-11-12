"""Manage uploaded files and textual knowledge; never execute engineering files."""
import io
import zipfile
from docx import Document
from . import db

CAD_EXTENSIONS={'.step','.stp','.iges','.igs','.stl','.dwg','.dxf','.sldprt','.sldasm','.fcstd','.3dm','.ipt','.iam','.prt','.asm'}
PREVIEW_MIMES={'.pdf':'application/pdf','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.svg':'image/svg+xml','.txt':'text/plain','.md':'text/plain','.json':'application/json'}
UPLOAD_EXTENSIONS=CAD_EXTENSIONS|set(PREVIEW_MIMES)|{'.docx'}

def mime_for(ext):return PREVIEW_MIMES.get(ext,'application/octet-stream')

def safe_name(filename):
    name=(filename or '').replace('\\','/').rsplit('/',1)[-1]
    if name in ('','.','..') or len(name)>200 or any(ord(c)<32 for c in name):raise ValueError('无效文件名')
    return name

def extract_text(ext,blob):
    if ext in ('.txt','.md','.json'):
        try:return blob.decode('utf-8-sig').strip()[:60000] or None
        except UnicodeDecodeError:return None
    if ext=='.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                if len(z.infolist())>2000 or sum(i.file_size for i in z.infolist())>20_000_000:raise ValueError('DOCX 解压内容超出限制')
            d=Document(io.BytesIO(blob))
            lines=[p.text for p in d.paragraphs]+[' | '.join(c.text for c in r.cells) for t in d.tables for r in t.rows]
            return '\n'.join(lines).strip()[:60000] or None
        except (zipfile.BadZipFile,KeyError):raise ValueError('无效 DOCX 文件')
    return None

def validate_links(pid,meta):
    for nid in meta.need_ids:db.record(nid,pid,'need')
    plan=db.record(meta.proposal_id,pid,'proposal') if meta.proposal_id else None
    prd=db.record(meta.prd_id,pid,'prd') if meta.prd_id else None
    if meta.hardware_feature_indexes and not plan:raise ValueError('硬件功能必须指定方案版本')
    if plan:
        features=plan['data']['features']
        if any(i<0 or i>=len(features) for i in meta.hardware_feature_indexes):raise ValueError('硬件功能不存在于指定方案版本')
        if meta.hardware_feature_indexes:
            need_ids={n for i in meta.hardware_feature_indexes for n in features[i]['need_ids']}
            if not set(meta.need_ids)<=need_ids:raise ValueError('关联需求与硬件功能不一致')
    if prd:
        if plan and prd['data']['proposal_id']!=plan['id']:raise ValueError('PRD 与硬件功能不属于同一方案')
        if not set(meta.need_ids)<=set(prd['data']['need_ids']):raise ValueError('关联需求不在指定 PRD 中')
    data=(plan or prd or {}).get('data',{})
    return {'baseline_id':data.get('baseline_id'),'tone_id':data.get('tone_id')}
