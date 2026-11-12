"""Account management used by the existing Accounts page."""
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import Field
from . import db, schemas as s

class AccountConfig(s.Strict):
    role:Literal['sales','marketing']
    project_ids:list[str]=Field(default_factory=list,max_length=500)
    active:bool=True
    password:str=Field(default='',max_length=200)
class AccountCreate(AccountConfig):
    name:str=Field(min_length=2,max_length=80)

def register(app,user,password_hash):
    def admin(u=Depends(user)):
        if u.get('account_role')!='admin':raise HTTPException(403,'仅管理员可配置账户')
        return u
    def save(c,uid,b,u):
        if b.password and len(b.password)<8:raise ValueError('新密码至少 8 位')
        for pid in b.project_ids:
            if not c.execute('SELECT id FROM projects WHERE id=?',(pid,)).fetchone():raise ValueError('项目不存在')
        c.execute('INSERT INTO account_settings VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET role=excluded.role,active=excluded.active',(uid,b.role,int(b.active)))
        c.execute('DELETE FROM members WHERE user_id=?',(uid,))
        c.executemany('INSERT INTO members VALUES(?,?,?)',[(pid,uid,b.role) for pid in set(b.project_ids)])
        if b.password:c.execute('UPDATE users SET password=? WHERE id=?',(password_hash(b.password),uid))
        c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        c.execute('INSERT INTO admin_audit VALUES(?,?,?,?,?)',(db.uid(),u['name'],'配置账户',uid,db.now()))
        return {'id':uid}
    @app.get('/api/admin/accounts')
    def listing(u=Depends(admin)):
        with db.connect() as c:
            accounts=[dict(r) for r in c.execute("SELECT u.id,u.name,COALESCE(a.role,'member') role,COALESCE(a.active,1) active FROM users u LEFT JOIN account_settings a ON a.user_id=u.id")]
            for a in accounts:a['project_ids']=[r['project_id'] for r in c.execute('SELECT project_id FROM members WHERE user_id=?',(a['id'],))]
            return {'accounts':accounts,'projects':[dict(r) for r in c.execute('SELECT id,name FROM projects')]}
    @app.post('/api/admin/accounts')
    def create(b:AccountCreate,u=Depends(admin)):
        if len(b.password)<8:raise ValueError('新密码至少 8 位')
        with db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT id FROM users WHERE name=?',(b.name,)).fetchone():raise HTTPException(409,'账户已存在')
            uid=db.uid();c.execute('INSERT INTO users VALUES(?,?,?)',(uid,b.name,password_hash(b.password)))
            return save(c,uid,b,u)
    @app.post('/api/admin/accounts/{uid}')
    def update(uid:str,b:AccountConfig,u=Depends(admin)):
        with db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            a=c.execute('SELECT role FROM account_settings WHERE user_id=?',(uid,)).fetchone()
            if not a or a['role'] not in ('sales','marketing'):raise HTTPException(403,'仅可配置销售/市场账户')
            return save(c,uid,b,u)
