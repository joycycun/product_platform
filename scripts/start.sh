#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  .venv/bin/python -c 'from pathlib import Path; import secrets; p=Path(".env"); p.write_text(Path(".env.example").read_text().replace("change-this-before-use",secrets.token_urlsafe(18))); p.chmod(0o600)'
  echo '已生成本地 .env。登录名和初始密码请查看其中的 BOOTSTRAP_USER / BOOTSTRAP_PASSWORD。'
fi
exec .venv/bin/python -m uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000
