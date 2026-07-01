# AIHR BOSS 招聘 Agent

这是一个面向蓝领/服务业招聘场景的 AI 招聘 Agent 原型。项目基于原 AI 客服系统改造，当前重点不是官网客服，而是通过本地招聘工作台管理招聘需求，并辅助操作 BOSS 直聘完成候选人搜索、筛选和后续沟通流程。

## 当前目标

- 在系统内创建招聘需求，例如服务员、水电工、普工等岗位。
- 将城市/区县、岗位、职位关键词、学历、年龄、推荐筛选、专业要求等条件同步到 BOSS 直聘搜索页。
- 每次创建需求后自动触发 BOSS 搜索，减少人工重复输入。
- 将候选人手动加入候选人池，后续由招聘 Agent 生成沟通话术、维护跟进状态。
- 后续扩展为两个 Agent：
  - Agent1：BOSS 直聘候选人筛选、沟通、获取联系方式、拉入私域。
  - Agent2：微信群/企业微信内介绍岗位业务和承接转化。

## 项目结构

```text
AI-CS-master/
├── backend/          # Go 后端：账号、招聘需求、候选人池、BOSS 本地助手接口
├── frontend/         # Next.js 前端：招聘 Agent 页面、设置页、登录页
├── agent-service/    # Python Agent 服务：LangGraph 流程、BOSS 页面自动化辅助
├── scripts/          # 本地启动、停止、BOSS 辅助脚本
├── docs/             # BOSS 接入、招聘 Agent 架构说明
└── .env              # 本地配置，不要提交
```

## 快速启动

推荐使用后台启动脚本，不需要手动开 3 个 PowerShell。

```powershell
cd E:\postgraduate_project\aihr-boss\AI-CS-master\AI-CS-master
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

停止服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1
```

访问地址：

```text
http://localhost:3000/agent/login
```

默认登录：

```text
admin / 123456
```

如果只看页面、不需要 BOSS 自动搜索：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1 -NoAgent
```

日志目录：

```text
.dev/logs/
```

## 手动启动方式

后端：

```powershell
cd backend
& "$env:TEMP\codex-go-1.24.1\go\bin\go.exe" run .
```

前端：

```powershell
cd frontend
npm run dev
```

招聘 Agent 服务：

```powershell
cd agent-service
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

## 主要功能

### 招聘 Agent 页面

路径：

```text
http://localhost:3000/agent/dashboard?page=recruitment
```

已实现：

- 新建招聘需求。
- BOSS 搜索条件字段：
  - 省 / 市 / 区县
  - 职位类型
  - 搜索职位关键词
  - 学历要求
  - 年龄要求
  - 排序方式
  - 推荐筛选 / 更多筛选
  - 专业要求三级选择和手动输入
  - 过滤近 14 天查看
  - 近 30 天未和同事交换简历
- 创建需求后同步 BOSS 搜索。
- 需求列表搜索。
- 单条删除需求。
- 一键删除全部需求，需输入当前账号密码二次确认。
- 候选人池手动录入。
- 候选人状态推进、沟通记录、话术生成入口。

### BOSS 本地助手

当前不是直接接 BOSS 官方 API，而是本地辅助操作：

- 检测本机 BOSS 客户端或 Chrome 中的 BOSS 页面。
- 打开 BOSS 搜索 / 沟通页面。
- 根据招聘需求把搜索条件同步到 BOSS 页面。
- 自动触发普通搜索按钮，避免手动再点搜索。

注意：

- 项目不保存 BOSS 账号、密码、cookie 或登录态。
- 需要人工先登录 BOSS。
- 当前属于本地演示/原型能力，稳定性取决于 BOSS 页面结构和窗口状态。

### Agent 服务

`agent-service/` 提供 Python 服务：

- `/v1/recruitment/run`：运行招聘 Agent 流程。
- `/v1/recruitment/draft`：生成候选人沟通话术。
- `/v1/boss/search`：辅助操作 BOSS 搜索页。
- `/v1/boss/snapshot`：读取 BOSS 页面文本快照。

项目已引入 LangGraph 思路，当前用于招聘 Agent 的状态流设计：需求 -> 候选人 -> 匹配判断 -> 话术生成 -> 人工确认 -> 跟进记录。

## 可借鉴的开源方向

- LangGraph：适合表达多轮招聘沟通状态流。
- LangChain / RAG：适合把岗位介绍、公司话术、BOSS 使用技巧沉淀为知识库。
- Playwright / DrissionPage：适合做本地浏览器自动化和页面读取。

当前项目里同时保留了：

- `agent-service/`：更接近 Agent 工作流。
- `scripts/boss_job_export_fast.py`：从旧 Python 脚本整理出的 BOSS 职位导出工具，适合做岗位市场数据采集，不直接参与候选人筛选主流程。

## 重要文件

```text
frontend/app/agent/recruitment/page.tsx
backend/service/boss_assistant_service.go
agent-service/app/boss_browser.py
agent-service/app/recruitment_agent.py
scripts/start-dev.ps1
scripts/stop-dev.ps1
docs/boss-integration-requirements.md
docs/recruitment-agent-langgraph-architecture.md
```

## 当前限制

- BOSS 官方接口未接入，目前通过本地页面辅助操作实现。
- 候选人资料还需要人工复制/录入到候选人池。
- BOSS 页面结构变化会影响自动点击和字段同步。
- Agent 沟通发送前仍保留人工确认，避免自动发送不合规消息。

## 下一步

- 提升 BOSS 搜索条件同步稳定性。
- 从 BOSS 列表读取候选人卡片信息，批量加入候选人池。
- 接入岗位知识库，生成更贴近岗位的首轮沟通话术。
- 完善候选人匹配评分和多轮沟通状态流。
- 如能获得 BOSS 官方授权接口，优先替换本地页面自动化。
