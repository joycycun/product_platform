import json, os, sqlite3, uuid
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(os.getenv('DATA_DIR', str(Path(__file__).resolve().parent.parent / 'data')))
ROOT.mkdir(parents=True, exist_ok=True)
FILES = ROOT / 'files'
FILES.mkdir(exist_ok=True)
def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex

def connect():
    c=sqlite3.connect(ROOT / 'platform.db', timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO migrations VALUES(1);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,direction TEXT NOT NULL,constraints TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS members(project_id TEXT,user_id TEXT,role TEXT NOT NULL,PRIMARY KEY(project_id,user_id));
        CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,author TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS records_project_kind ON records(project_id,kind);
        CREATE TABLE IF NOT EXISTS matches(project_id TEXT,source_system TEXT,external_id TEXT,data TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(project_id,source_system,external_id));
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,project_id TEXT,source_system TEXT,external_id TEXT,received_at TEXT);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT,kind TEXT,status TEXT,input TEXT,result TEXT,error TEXT,created_at TEXT,finished_at TEXT);
        CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,project_id TEXT,record_id TEXT,name TEXT,path TEXT,mime TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS record_archives(record_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,archived_at TEXT NOT NULL,archived_by TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS translation_cache(project_id TEXT NOT NULL,source_hash TEXT NOT NULL,english TEXT NOT NULL,PRIMARY KEY(project_id,source_hash));
        ''')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS account_settings(user_id TEXT PRIMARY KEY,role TEXT NOT NULL DEFAULT 'member',active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS admin_audit(id TEXT PRIMARY KEY,actor TEXT,action TEXT,target_id TEXT,created_at TEXT);
        INSERT OR IGNORE INTO migrations VALUES(2);
        ''')
        c.execute("UPDATE jobs SET status='failed',error='服务重启，任务中断；请重新提交',finished_at=? WHERE status IN ('queued','running')",(now(),))

def add(project,kind,data,author='system',c=None):
    row=dict(id=uid(),project_id=project,kind=kind,data=data,created_at=now(),author=author)
    def run(conn):conn.execute('INSERT INTO records VALUES(?,?,?,?,?,?)',(row['id'],project,kind,json.dumps(data,ensure_ascii=False),row['created_at'],author))
    if c is not None:run(c)
    else:
        with connect() as conn:run(conn)
    return row

def rows(project,kind=None):
    with connect() as c:
        rs=c.execute('SELECT r.* FROM records r LEFT JOIN record_archives a ON a.record_id=r.id WHERE r.project_id=? AND a.record_id IS NULL'+(' AND r.kind=?' if kind else '')+' ORDER BY r.rowid',(project,kind) if kind else (project,)).fetchall()
    return [dict(r)|{'data':json.loads(r['data'])} for r in rs]

def archive(project,rids,actor):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for rid in rids:
            row=c.execute('SELECT id FROM records WHERE id=? AND project_id=?',(rid,project)).fetchone()
            if not row:raise ValueError('对象不存在或不属于当前项目')
            c.execute('INSERT OR IGNORE INTO record_archives VALUES(?,?,?,?)',(rid,project,now(),actor))

def record(rid,project,kind=None):
    with connect() as c:r=c.execute('SELECT * FROM records WHERE id=? AND project_id=?',(rid,project)).fetchone()
    if not r or (kind and r['kind']!=kind):raise ValueError('对象不存在或不属于当前项目')
    return dict(r)|{'data':json.loads(r['data'])}

def latest(project,kind):
    rr=rows(project,kind)
    return rr[-1] if rr else None

def audit(project,actor,action,detail):return add(project,'audit',dict(action=action,detail=detail),actor)
