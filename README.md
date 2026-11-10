# Zycoo · 公司内部产品设计平台

本地 V1 垂直切片；需求依据见 docs/AI产品经理工作平台_设计大纲.md。客户与商机主数据属于既有销售平台，本平台仅接收匹配摘要。

## Docker Compose 启动（推荐）

当前目录已有 `.env`，直接运行：

```sh
docker compose up --build -d
```

访问 http://127.0.0.1:8000 ，账号与初始密码见 `.env`。也可使用兼容命令 `docker-compose up --build -d`。新机器先复制 `.env.example` 为 `.env` 并设置初始密码。前端、Python 与 CAD 依赖均在镜像中构建，无需宿主安装。为兼容 CadQuery 2.6.1 的 Linux 安装包，服务固定使用 linux/amd64；Apple Silicon 由 Docker Desktop 模拟运行，CAD 性能可能低于本地原生环境。

`./data` 持久挂载，复用本地已创建的演示项目；不要同时运行本地服务和容器服务。修改 `.env` 后运行 `docker compose up -d` 重建容器。若端口冲突，在 `.env` 设置 `PLATFORM_PORT=8001`。

```sh
docker compose logs -f platform
docker compose exec platform python -m pytest -q
docker compose exec platform python scripts/seed_demo.py
docker compose down
```

`down` 不删除宿主 `data`；备份时先停服务，再复制完整 `data` 目录（数据库及文件）。容器访问宿主模型服务时，MODEL_BASE_URL 使用 `http://host.docker.internal:端口/...`（Docker Desktop）。

## 本地 Python 启动（备选）

需要 Python 3.12、Node.js 20+。首次安装：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
cp .env.example .env
```

当前机器已安装项目依赖，可直接运行 `./scripts/start.sh`。首次运行会生成随机初始密码并保存在权限为 600 的 `.env` 中，查看 BOOTSTRAP_USER / BOOTSTRAP_PASSWORD 登录。

如按上面的手动流程创建 `.env`，请修改初始账号密码；不要提交密钥。然后：

```sh
.venv/bin/python -m uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000
```

访问 http://127.0.0.1:8000 。接口说明 http://127.0.0.1:8000/docs 。开发前端运行 `cd frontend && npm run dev`，代理后端 8000。

## 演示路径

已准备名为“【演示】学校走廊带屏 SIP 终端”的演示项目。也可在服务运行后执行 `.venv/bin/python scripts/seed_demo.py` 初始化；所有文字/客户均为显式演示，CAD 为真实几何。


1. 登录并创建项目，发布画像。右上角主动选择“显式演示 / 模板”。
2. 搜索演示竞品，展开卡片，填写选择理由，建立 premier；资料未知保持待核实。
3. 匹配客户页接收“模拟上游”，手工录入明确标记为演示的反馈。
4. 提取需求与软件、硬件、接口、联合验收；修改后将 status 设为 confirmed 保存。
5. 生成两个功能方案、提交评审、选择方案。
6. 生成 PRD 候选，在左右对照中编辑并保存；下载 DOCX，再上传候选，不会自动覆盖人工稿。
7. CAD 页面核对概念尺寸，把 confirmed 改为 true，生成真实模型。
8. 图纸旁输入“扬声器区域加宽 20 mm，屏幕有效显示区不变”，预览再应用；切换历史版本或恢复。
9. 下载 model.py、parameters.json、model.step、drawing.svg。用同一依赖环境执行 `python model.py parameters.json output` 可重新生成。

演示文字不是模型输出；模板 PRD 直接取项目数据。CAD 即使处于演示模式仍运行真正的 CadQuery/OpenCascade，而对话使用有限规则解析。真实模式调用配置的搜索及模型，不回退伪造结果。

## 验证

```sh
.venv/bin/python -m pytest -q
cd frontend && npm run build
```

测试使用临时数据库和文件目录，不写入真实项目。覆盖业务链、STEP 重开与尺寸变更、版本引用、权限和缺配置错误。

## 已知边界

- 真实搜索/模型/销售需凭据与双方联调；目前不能宣称真实端到端业务验收通过。
- 首类 CAD 是矩形终端概念模型；屏幕和扬声器仅包络体，未做声学、电气、散热、公差与制造设计。
- JSON 编辑器为 V1 精确编辑入口，后续替换为专业表单；上传 STEP 当前归档下载，尚无上传几何预览或参数恢复。
- 单实例 SQLite + 本地文件 + 进程任务池；重启标记未完成任务失败。生产需独立任务队列、企业身份、数据库/存储备份和出站网络限制。
- PRD 导入保留文本和表格内容，不承诺还原复杂 Word 排版；页面支持并排对照与候选逐行差异，非 Word 逐字红线。
- 模型数据权限当前是服务器级显式开关，尚未实现按资料分类策略。

## admin 账户配置

admin 登录后进入左侧“账户配置”，填写登录名、初始密码（至少 8 位）、销售/市场角色并勾选可访问项目，即可创建账户。已有销售/市场账户可修改角色、项目授权、启用状态或重置密码；保存配置会撤销该账户旧会话，需重新登录。未分配项目的账户不能读取任何项目，销售/市场不能自行创建项目或访问管理员接口。已有管理员凭据及项目数据保留。


`.env` 中的 BOOTSTRAP_PASSWORD 只用于首次创建管理员，不会在重启时覆盖已保存密码。若忘记原密码，可在项目目录执行以下命令，按提示输入并确认新的至少 8 位密码（不会回显）：

```sh
docker compose exec platform python scripts/reset_admin_password.py
```

此工具只有实际执行并输入新密码才会修改管理员密码，并撤销旧会话。账户配置页面仅管理销售/市场账户。
