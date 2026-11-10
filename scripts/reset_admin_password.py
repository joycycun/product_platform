"""Explicit terminal-only recovery for an existing administrator account."""
import getpass
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
from backend import db
from backend.main import password_hash

def reset(password):
    if not 8 <= len(password) <= 200 or password != password.strip():
        raise ValueError('新密码需要 8–200 位，且首尾不能有空格')
    name=os.getenv('BOOTSTRAP_USER','admin')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        target=c.execute("SELECT u.id FROM users u JOIN account_settings a ON a.user_id=u.id WHERE u.name=? AND a.role='admin'",(name,)).fetchone()
        if not target:raise ValueError('未找到已有管理员，请先启动平台完成初始化')
        c.execute('UPDATE users SET password=? WHERE id=?',(password_hash(password),target['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(target['id'],))
        c.execute('INSERT INTO admin_audit VALUES(?,?,?,?,?)',(db.uid(),'local-console','管理员密码恢复',target['id'],db.now()))

if __name__=='__main__':
    try:
        password=getpass.getpass('输入管理员新密码（至少 8 位）：')
        if password!=getpass.getpass('再次输入新密码：'):raise ValueError('两次密码不一致，未修改')
        reset(password)
        print('管理员密码已更新，请使用新密码重新登录。')
    except (ValueError,EOFError,KeyboardInterrupt) as exc:
        print(str(exc) or '已取消，未修改',file=sys.stderr);sys.exit(1)
