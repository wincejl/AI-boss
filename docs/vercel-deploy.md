# Vercel 部署说明

## 当前项目能部署什么

Vercel 适合部署本项目的 `frontend`，也就是 AI-CS 的 Web 页面。

本项目的 Go 后端 `backend` 和本地浏览器控制服务 `agent-service` 不能直接跑在 Vercel 上。原因是它们需要常驻进程、本地文件/数据库、WebSocket，以及 DrissionPage 控制本机浏览器。

所以推荐结构是：

```text
Vercel frontend -> 公网 Go backend -> 本地或服务器 agent-service
```

如果只是本机演示 BOSS 自动化，继续用 `scripts/start-dev.ps1` 或 `start-aihr.bat` 最稳。

## Vercel 项目设置

1. 在 Vercel 导入 GitHub 仓库。
2. Root Directory 选择：

```text
AI-CS-master/AI-CS-master/frontend
```

3. Framework Preset 选择 `Next.js`。
4. Build Command 使用：

```text
npm run build
```

5. Output Directory 保持默认。

## 环境变量

如果后端已经部署到公网，在 Vercel 项目里配置：

```text
NEXT_PUBLIC_API_BASE_URL=https://你的后端域名
BACKEND_BASE_URL=https://你的后端域名
```

注意：这里不要带最后的 `/api`，前端会自动拼接 `/api`。

示例：

```text
NEXT_PUBLIC_API_BASE_URL=https://aihr-api.example.com
BACKEND_BASE_URL=https://aihr-api.example.com
```

## 重要限制

部署到 Vercel 后，网页可以在线访问，但 BOSS 浏览器控制不会自动变成云端能力。BOSS 同步、自动发消息、招聘 Agent 控制浏览器这些功能仍然依赖运行在使用者本机或你自己服务器上的 `agent-service`。

如果要让别人下载源码后本地使用，Vercel 不是必需项；更适合的方式是提供一键启动脚本。

如果要让别人直接访问线上网站使用，则还需要继续做公网后端、用户隔离、认证、安全配置，以及每个用户本地浏览器控制端的连接方案。

