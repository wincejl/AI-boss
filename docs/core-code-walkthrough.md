# AI 招聘助手核心代码讲解指引

这份文档用于带本科生系统性理解项目代码。讲解时不要按目录从上到下扫，而是按业务链路讲：用户在系统里做了什么，前端如何发请求，后端如何调度，Python 如何控制 BOSS 网页，AI 如何生成回复。

## 0. 讲解前准备

### 现场要做什么

1. 打开项目目录：

```powershell
E:\postgraduate_project\aihr-boss\AI-CS-master\AI-CS-master
```

2. 先让学生知道项目分为三层：

```text
frontend        Next.js 前端页面
backend         Go 后端，负责业务、数据库、AI、会话
agent-service   Python 服务，负责本地浏览器控制
```

3. 画出总架构：

```text
用户操作前端页面
    ↓
Next.js 前端发 HTTP 请求
    ↓
Go 后端接收请求、保存数据、调用 AI
    ↓
Python agent-service 执行浏览器控制
    ↓
DrissionPage 控制 Chrome 中的 BOSS 直聘网页
```

### 要强调的核心观点

```text
这个项目不是单纯的聊天系统，而是“AI 客服系统 + 招聘 Agent + 本地浏览器自动化”。
前端负责交互，Go 后端负责业务调度，Python 负责控制 BOSS，Kimi 负责生成回复。
```

---

## 1. 从前端驾驶舱开始讲

### 讲到哪里

讲“用户打开系统后看到的后台页面”。

### 现场应该做什么

打开后台页面，让学生先看实际效果：

```text
http://localhost:3000/agent/dashboard?page=dashboard
```

然后告诉他们：

```text
左边是会话列表，中间是聊天记录，右边是候选人详情。
这里是招聘客服工作的主界面。
```

### 看哪个代码

```text
frontend/components/dashboard/DashboardShell.tsx
```

### 核心功能逻辑

这个文件是前端主控页面，负责把多个功能组合在一起：

```text
1. 当前选中哪个会话
2. 加载聊天记录
3. 发送消息
4. 点击“同步 BOSS 沟通”
5. 删除/关闭会话
6. 切换左侧会话列表和右侧详情
```

### 讲解方式

可以这样讲：

```text
DashboardShell.tsx 可以理解为系统驾驶舱。它本身不直接操作数据库，也不直接控制 BOSS。
它只是把用户点击按钮、输入消息这些动作，转成前端服务层的函数调用。
```

### 学生需要掌握

```text
1. 前端页面不直接控制 BOSS。
2. 前端所有核心动作都要通过 service 文件请求后端。
3. DashboardShell.tsx 是理解聊天页面的入口。
```

### 可布置任务

```text
任务：阅读 DashboardShell.tsx，标出“同步 BOSS 沟通”和“发送消息”分别调用了哪个函数。
```

---

## 2. 讲前端接口层

### 讲到哪里

讲“前端按钮点下去以后，请求是怎么发到后端的”。

### 现场应该做什么

让学生从页面按钮跳到接口调用文件，不要先看后端。

### 看哪个代码

```text
frontend/features/agent/services/recruitmentApi.ts
frontend/features/agent/services/conversationApi.ts
frontend/features/agent/services/messageApi.ts
```

### 核心功能逻辑

#### recruitmentApi.ts

负责招聘 Agent 相关请求：

```text
1. 创建招聘需求
2. 查询需求列表
3. 删除需求
4. 调用 BOSS 搜索
5. 导入 BOSS 候选人
```

重点看：

```text
createRequirement()
searchBossCandidates()
importBossCandidates()
```

#### conversationApi.ts

负责会话相关请求：

```text
1. 获取会话列表
2. 同步 BOSS 沟通联系人
3. 删除 BOSS 联系人或关闭本地会话
```

重点看：

```text
importBossChats()
deleteBossChatConversation()
```

#### messageApi.ts

负责消息发送：

```text
1. 把系统聊天框里的消息提交给后端
2. 如果该会话来源是 BOSS，后端会继续同步到 BOSS 网页
```

重点看：

```text
sendMessage()
```

### 讲解方式

可以这样讲：

```text
这些 service 文件是前端和后端之间的桥。
前端页面负责收集用户输入，service 文件负责把这些输入变成 HTTP 请求。
```

### 学生需要掌握

```text
1. 前端通过 apiUrl() 统一拼接接口路径。
2. 前端调用的是 Go 后端，不是 Python。
3. recruitment、conversation、message 三类接口分别对应招聘需求、会话同步、消息发送。
```

### 可布置任务

```text
任务：整理这三个文件中最重要的 10 个接口，写出接口名称、请求路径、用途。
```

---

## 3. 讲 Go 后端 BOSS 总入口

### 讲到哪里

讲“前端请求到达后端以后，谁来接收和调度”。

### 现场应该做什么

打开 controller，让学生看到前端请求进入后端的入口。

### 看哪个代码

```text
backend/controller/boss_assistant_controller.go
```

### 核心功能逻辑

这个文件是 BOSS 招聘 Agent 的总控制器。

重点函数：

```text
SearchCandidates()
接收前端搜索请求，触发 BOSS 页面搜索。

ImportCandidates()
读取 BOSS 搜索结果，并写入候选人池。

ImportChats()
同步 BOSS 沟通联系人和聊天记录。

DeleteChat()
删除 BOSS 联系人或关闭本地会话。

draftReplyBossChats()
发现候选人新消息后，触发 AI 生成回复。

sendBossChatAIReply()
把 AI 回复同步发送到 BOSS。
```

### 讲解方式

可以这样讲：

```text
controller 不直接点浏览器，也不直接操作页面。
它的职责是接收请求、校验参数、调用 service，并把结果返回给前端。
```

### 学生需要掌握

```text
1. controller 是后端接口入口。
2. BOSS 相关能力基本都从这个文件进入。
3. AI 自动回复也是在同步 BOSS 消息后触发的。
```

### 可布置任务

```text
任务：阅读 boss_assistant_controller.go，整理每个公开接口的功能说明。
```

---

## 4. 讲 Go 后端服务层如何调用 Python

### 讲到哪里

讲“Go 后端如何把请求转给 Python agent-service”。

### 现场应该做什么

先让学生知道：

```text
Go 后端不直接操作 Chrome。
真正操作 Chrome 的是 Python agent-service。
Go 后端通过 HTTP 调 Python。
```

### 看哪个代码

```text
backend/service/boss_assistant_service.go
```

### 核心功能逻辑

重点函数：

```text
SearchCandidates()
调用 Python 的 /v1/boss/search。

ReadCandidates()
调用 Python 读取 BOSS 搜索结果候选人。

ReadChats()
调用 Python 读取 BOSS 沟通联系人。

SendChatMessage()
调用 Python 在 BOSS 聊天框发消息。

DeleteChat()
调用 Python 删除 BOSS 联系人。
```

### 讲解方式

可以这样讲：

```text
这个 service 文件相当于 Go 和 Python 的适配层。
Go 后端说“我要搜索候选人”，它就把这个请求封装成 HTTP，发给 agent-service。
```

### 学生需要掌握

```text
1. Go 后端通过 BOSS_AGENT_SERVICE_URL 找到 Python 服务。
2. Go 负责业务，Python 负责浏览器动作。
3. 这里是排查 BOSS 同步失败的重要位置。
```

### 可布置任务

```text
任务：画出 boss_assistant_service.go 调用了 agent-service 哪些接口。
```

---

## 5. 讲 Python agent-service 接口

### 讲到哪里

讲“Python 这边对外暴露了哪些本地浏览器控制接口”。

### 现场应该做什么

打开 Python API 入口文件。

### 看哪个代码

```text
agent-service/app/main.py
```

### 核心功能逻辑

这个文件提供 FastAPI 接口：

```text
/v1/boss/search
执行 BOSS 搜索。

/v1/boss/candidates
读取 BOSS 搜索结果候选人。

/v1/boss/chats
读取 BOSS 沟通联系人和聊天记录。

/v1/boss/send-message
给 BOSS 候选人发消息。

/v1/boss/delete-chat
删除 BOSS 联系人。
```

### 讲解方式

可以这样讲：

```text
main.py 本身不是最复杂的，它主要是 HTTP 接口入口。
真正复杂的页面控制逻辑在 boss_browser.py。
```

### 学生需要掌握

```text
1. agent-service 是本地服务。
2. 它跑在 8090。
3. Go 后端通过 HTTP 调它。
4. 它再调用 boss_browser.py 控制浏览器。
```

### 可布置任务

```text
任务：整理 main.py 中每个接口对应 boss_browser.py 的哪个函数。
```

---

## 6. 讲最核心的 BOSS 浏览器控制

### 讲到哪里

讲“系统到底是怎么操作 BOSS 网页的”。

### 现场应该做什么

打开核心文件，并提醒学生：

```text
这个文件是项目里最接近真实业务动作的地方。
它负责打开 BOSS、点击页面、输入内容、读取页面文字。
```

### 看哪个代码

```text
agent-service/app/boss_browser.py
```

### 核心功能逻辑

#### 浏览器连接

重点函数：

```text
get_page()
启动或连接 DrissionPage 控制的 Chrome。

get_connected_page()
只复用已连接的浏览器，不主动拉起新 Chrome。
```

讲解：

```text
系统不能每次后台同步都启动一个 Chrome，否则用户关掉浏览器后它还会自动弹出。
所以后台增量同步只复用已打开的浏览器。
```

#### BOSS 搜索候选人

重点函数：

```text
search_candidates()
执行完整搜索流程。

select_city()
选择城市/区县。

select_category()
选择职位类型。

fill_keyword()
输入搜索关键词。

select_education()
选择学历。

click_search()
点击搜索或回车搜索。
```

讲解：

```text
招聘 Agent 里填的字段，会被转换成 BOSS 网页上的真实操作。
例如城市、区县、职位、关键词、学历、年龄等。
```

#### 读取候选人卡片

重点函数：

```text
read_candidates()
读取搜索结果。

collect_candidate_cards()
收集页面候选人卡片文本。

parse_boss_candidate()
把页面文本解析成结构化候选人数据。
```

讲解：

```text
BOSS 没有给我们官方接口，所以我们只能从页面上读取卡片内容，再解析成姓名、年龄、学历、经验等字段。
```

#### 读取 BOSS 沟通联系人

重点函数：

```text
read_chats()
同步 BOSS 沟通联系人入口。

collect_boss_chat_items()
读取联系人列表。

parse_boss_chat()
解析联系人姓名、岗位、最近消息。

collect_boss_chat_history()
读取当前联系人的聊天历史。
```

讲解：

```text
这一步是把 BOSS 沟通页里的联系人和消息搬到我们系统里。
如果联系人匹配不准，就会出现消息串人的问题。
```

#### 发送消息到 BOSS

重点函数：

```text
send_chat_message()
发送消息总入口。

click_boss_chat_item()
在 BOSS 联系人列表里找到目标候选人。

boss_chat_detail_matches()
确认详情页是不是目标候选人。

fill_boss_chat_input()
把消息填入 BOSS 输入框。

press_boss_chat_enter()
回车发送。
```

讲解：

```text
系统发消息时，必须先找到正确候选人，再输入和发送。
不能只依赖当前页面，否则可能回复错人。
```

#### 删除联系人

重点函数：

```text
delete_chat()
open_boss_chat_item_menu()
```

讲解：

```text
删除联系人属于高风险动作，因为它会影响 BOSS 真实联系人。
目前这个能力还不稳定，要重点记录失败原因。
```

### 学生需要掌握

```text
1. boss_browser.py 是项目自动化核心。
2. 页面结构变化会影响解析和点击。
3. 最重要的是目标确认，不能回复错人。
```

### 可布置任务

```text
任务 1：整理 search_candidates() 的完整调用链。
任务 2：整理 read_chats() 的完整调用链。
任务 3：整理 send_chat_message() 的完整调用链。
任务 4：找出哪些函数与“防止消息串人”有关。
```

---

## 7. 讲 BOSS 联系人如何变成本地会话

### 讲到哪里

讲“BOSS 同步进来的联系人，为什么能出现在我们系统左侧对话列表”。

### 现场应该做什么

先展示 BOSS 沟通页，再展示系统左侧会话列表。

告诉学生：

```text
BOSS 联系人不是天然属于我们系统。
后端要把它转换成本地 conversation 和 message。
```

### 看哪个代码

```text
backend/service/conversation_service.go
```

### 核心功能逻辑

重点关注：

```text
1. 根据 BOSS 候选人姓名、岗位、来源信息匹配或创建会话。
2. 把 BOSS 历史消息保存成本地 messages。
3. 判断 sender_is_agent，区分招聘者消息和候选人消息。
4. 对历史消息去重。
5. 更新会话最近消息和最后活跃时间。
```

### 讲解方式

可以这样讲：

```text
这个文件是 BOSS 联系人和我们系统会话之间的翻译层。
如果这里映射错了，就会出现 A 候选人的消息进到 B 候选人的会话里。
```

### 学生需要掌握

```text
1. conversation 是本地系统概念。
2. BOSS 联系人要经过映射才能变成本地 conversation。
3. 消息串人问题主要和映射规则有关。
```

### 可布置任务

```text
任务：画出 BOSS 联系人同步到本地会话的数据结构变化。
```

---

## 8. 讲消息发送链路

### 讲到哪里

讲“我们系统里发送一条消息，BOSS 候选人为什么能收到”。

### 现场应该做什么

在系统聊天框里发一条测试消息，然后观察 BOSS 页面输入框/消息区。

### 看哪个代码

```text
frontend/features/agent/services/messageApi.ts
backend/controller/message_controller.go
backend/service/boss_assistant_service.go
agent-service/app/boss_browser.py
```

### 核心链路

```text
MessageInput 输入消息
    ↓
messageApi.ts / sendMessage()
    ↓
message_controller.go 保存本地消息
    ↓
判断会话来源是否是 BOSS
    ↓
boss_assistant_service.go / SendChatMessage()
    ↓
agent-service /v1/boss/send-message
    ↓
boss_browser.py / send_chat_message()
    ↓
BOSS 网页发出消息
```

### 讲解方式

可以这样讲：

```text
系统消息发送分两步：先保存到自己系统，再同步到 BOSS。
如果 BOSS 同步失败，本地可能已经有消息，但 BOSS 没有真正发出去。
```

### 学生需要掌握

```text
1. 本地消息保存和 BOSS 发送是两个动作。
2. BOSS 发送失败要有错误提示。
3. 发送前必须确认目标联系人。
```

### 可布置任务

```text
任务：整理发送消息失败的可能原因，例如联系人不可见、页面不在沟通页、输入框未找到、BOSS 风控。
```

---

## 9. 讲 AI/Kimi 自动回复

### 讲到哪里

讲“候选人发消息后，Kimi 如何生成招聘回复”。

### 现场应该做什么

打开一条 BOSS 候选人会话，演示候选人问题和系统回复。

### 看哪个代码

```text
backend/controller/boss_assistant_controller.go
backend/service/ai_provider.go
backend/service/ai_service.go
backend/service/document_service.go
backend/service/faq_service.go
backend/service/rag/
```

### 核心功能逻辑

重点函数：

```text
draftReplyBossChats()
遍历新同步进来的候选人消息。

createBossChatAIDraft()
调用 AI 生成回复内容。

sendBossChatAIReply()
自动把 AI 回复发到 BOSS。
```

AI 调用逻辑：

```text
候选人问题
    ↓
读取聊天历史和岗位信息
    ↓
检索知识库话术
    ↓
调用 Kimi
    ↓
生成回复
    ↓
人工审核或自动发送
```

### 讲解方式

可以这样讲：

```text
Kimi 不是永久学习我们的业务。
我们是把岗位信息、聊天历史、知识库话术作为上下文，每次生成回复时一起发给 Kimi。
```

### 学生需要掌握

```text
1. AI 只负责生成文本，不直接控制 BOSS。
2. 自动发送仍然要走 send_chat_message()。
3. 知识库是 RAG 检索，不是模型永久记忆。
```

### 可布置任务

```text
任务 1：整理 30 条招聘话术，并按场景分类。
任务 2：测试 10 个候选人问题，记录 Kimi 回复是否合适。
任务 3：设计哪些场景必须人工审核，哪些场景可以自动回复。
```

---

## 10. 讲招聘 Agent 新建需求链路

### 讲到哪里

讲“用户新建需求后，系统如何自动在 BOSS 搜索候选人”。

### 现场应该做什么

在招聘 Agent 页面创建一个需求，例如：

```text
城市：莆田市
区县：城厢区
职位类型：不限职位
关键词：服务员
学历：不限
年龄：不限
同步候选人：10 个
```

观察 BOSS 搜索页是否变化。

### 看哪个代码

```text
frontend/features/agent/services/recruitmentApi.ts
backend/controller/boss_assistant_controller.go
backend/service/boss_assistant_service.go
agent-service/app/boss_browser.py
```

### 核心链路

```text
招聘 Agent 表单
    ↓
recruitmentApi.ts 提交需求
    ↓
Go 后端保存需求
    ↓
SearchCandidates()
    ↓
boss_assistant_service.go 调 /v1/boss/search
    ↓
boss_browser.py 控制 BOSS 页面
    ↓
选择城市、区县、职位、关键词、学历、年龄
    ↓
点击搜索
    ↓
读取候选人卡片
    ↓
写入候选人池
```

### 讲解方式

可以这样讲：

```text
这一条链路是招聘 Agent 的主动招聘能力。
用户在我们系统里填条件，系统把这些条件映射成 BOSS 页面筛选项。
```

### 当前需要提醒的风险

```text
1. 城市/区县映射可能受 BOSS 页面结构影响。
2. 不限职位可能需要特殊处理，不能保留上一次职位。
3. 点击搜索必须真正触发搜索结果刷新。
4. 同步候选人数量要和页面读取数量一致。
```

### 可布置任务

```text
任务：整理“我们系统字段”和“BOSS 页面字段”的映射表。
```

---

## 11. 讲当前项目的重点难点

### 讲到哪里

讲完代码后，总结工程难点。

### 现场应该做什么

让学生说出他们认为最容易出错的地方，然后统一归纳。

### 重点难点

```text
1. BOSS 没有官方接口，页面结构变化会影响自动化。
2. 联系人没有稳定唯一 ID，容易出现消息串人。
3. 自动回复必须确认目标候选人，不能回复错人。
4. 后台同步不能频繁打断用户手动使用 BOSS。
5. 浏览器自动化可能触发风控，要减少无意义刷新。
6. 删除联系人属于高风险动作，需要谨慎。
```

### 可布置任务

```text
任务：写一份风险清单，列出每个风险的触发场景、影响、可能解决方案。
```

---

## 12. 推荐讲课节奏

### 第一节：项目整体和前端

```text
1. 讲项目目标
2. 讲三层架构
3. 讲 DashboardShell.tsx
4. 讲前端 service 文件
```

课后任务：

```text
整理前端按钮和接口调用关系。
```

### 第二节：Go 后端和业务调度

```text
1. 讲 boss_assistant_controller.go
2. 讲 boss_assistant_service.go
3. 讲 conversation_service.go
```

课后任务：

```text
画 BOSS 联系人同步到本地会话的数据流图。
```

### 第三节：Python 自动化

```text
1. 讲 main.py
2. 讲 boss_browser.py
3. 讲搜索、同步、发送三条函数调用链
```

课后任务：

```text
整理 boss_browser.py 中 15 个核心函数的作用。
```

### 第四节：AI 回复和知识库

```text
1. 讲 Kimi 调用
2. 讲知识库/RAG
3. 讲自动回复和人工审核
4. 讲安全边界
```

课后任务：

```text
生成并分类 30 条招聘话术，导入知识库测试。
```

---

## 13. 最终给学生的代码阅读清单

### 必读

```text
frontend/components/dashboard/DashboardShell.tsx
frontend/features/agent/services/recruitmentApi.ts
frontend/features/agent/services/conversationApi.ts
frontend/features/agent/services/messageApi.ts
backend/controller/boss_assistant_controller.go
backend/service/boss_assistant_service.go
backend/service/conversation_service.go
agent-service/app/main.py
agent-service/app/boss_browser.py
```

### 进阶

```text
backend/controller/message_controller.go
backend/service/ai_provider.go
backend/service/ai_service.go
backend/service/document_service.go
backend/service/faq_service.go
backend/service/rag/
agent-service/app/schemas.py
agent-service/app/test_boss_browser_parser.py
```

---

## 14. 最终考核任务

学生完成学习后，可以分组交付：

```text
1. 一张完整系统架构图。
2. 一张“新建需求到 BOSS 搜索”的时序图。
3. 一张“BOSS 消息同步到系统”的时序图。
4. 一张“AI 自动回复到 BOSS”的时序图。
5. 一份 BOSS 字段映射表。
6. 一份候选人消息串人风险分析。
7. 一份招聘话术知识库文档。
8. 一个小的代码改动或测试用例。
```

---

## 15. 讲解时的总收束

最后可以这样总结：

```text
这个项目的核心不是单一的 AI 聊天，而是把招聘业务流程拆成三件事：

第一，招聘需求如何驱动 BOSS 搜索候选人；
第二，BOSS 沟通消息如何同步成本地系统会话；
第三，Kimi 如何基于岗位、聊天记录和话术知识库生成回复，并通过浏览器自动化发回 BOSS。

所以读代码时，要始终围绕三条链路：
新建需求链路、消息同步链路、AI 回复链路。
```

