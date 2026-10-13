# CourseBookAgent · 智课成书

把一门课的资料——字幕、课件、讲义、笔记——整理成按知识主题组织、可连续复习的课程教辅书。学生上传自己的资料是主路径；智云课堂和学在浙大是浙大学生的便捷接入。

## 在线试用

完整工作台已部署，无需注册：**https://coursebook-demo.vercel.app/datasets**

每个访客按签名 Cookie 拥有独立空间，可上传资料、创建快照、配置自己的模型并生成教辅书。站内附带一份已完成的九章预设供直接阅读，阅读不调用模型。托管细节见 [HOSTING](docs/HOSTING.md)。

## 本地运行

后端（Python 3.12+，用 [uv](https://docs.astral.sh/uv/) 管理依赖）：

```bash
uv sync
cp .env.example .env
# 编辑 .env，填入你自己的 OpenAI 兼容端点：LLM_BASE_URL、LLM_MODEL、LLM_API_KEY
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000
```

前端（另开一个终端，`/api` 代理到 8000）：

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。

## 生成一本书

1. 在资料库新建**资料集**，上传资料（PPTX / PDF / DOCX / Markdown / TXT），或从智云课堂 / 学在浙大导入。
2. 为资料集创建**快照**，锁定本次生成用到的资料版本。
3. 触发生成。HTTP 入口 `POST /api/generate` **必须**带 `snapshot_id`；可选 `regenerate` / `review` / `concurrency` / `chapter_indices`。
4. 在运行中心看七阶段进度（解析 → 资料说明 → 规划与 Tag → 装配 → 分章生成/检查 → 合成 → 渲染），完成后在产物页阅读或下载 Markdown。

流水线唯一入口是 `CourseBookPipeline.run()`；逐阶段调试用实验台 `scripts/lab.py`（见 [AGENTS.md](AGENTS.md)）。

## 验证

```bash
uv run python -m unittest discover -s tests -v          # 后端测试
uv run python scripts/check_offline.py                   # 离线确定性回归（禁外网）
cd frontend && npm run build && npm run lint             # 前端构建与 lint
```

## 架构

- **Python / FastAPI / SQLite**：资料集、文件版本、快照、Job 生命周期与运行投影（`coursebook_agent/product/`）。
- **生成核心**（`coursebook_agent/agent/` + `pipeline.py`）：资料说明、主题式全书规划与 Tag、上下文装配、分章撰写与检查、全书合成。
- **渲染**（`coursebook_agent/renderer/`）：结构化 CourseBook → Markdown / Web 阅读内容。
- **托管**（`coursebook_agent/hosting/`）：Vercel 游客空间、Private Blob、Python Workflow 存档与重放。
- **前端**（`frontend/`）：React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui，8 页产品工作台与成品阅读。

## 文档

- [CURRENT_STATUS](docs/CURRENT_STATUS.md)：当前事实、验证结果与缺口——**接手先读这个**。
- [AGENTS.md](AGENTS.md)：AI 协作地图与模块边界；[DEVELOPMENT](docs/DEVELOPMENT.md)：分支、验证与文档同步协议。
- [PRD](docs/PRD.md)：为什么做、如何成书；[PRODUCT_HANDOFF](docs/PRODUCT_HANDOFF.md)：产品边界；[COMPETITION](docs/COMPETITION.md)：比赛表达。
- [ARCHITECTURE](docs/ARCHITECTURE.md)、[WORKFLOW](docs/WORKFLOW.md)、[API](docs/API.md)、[HOSTING](docs/HOSTING.md)：实现、生成阶段、接口与托管。
- [ISSUES](docs/ISSUES.md)：已知缺口；[decisions/](docs/decisions/)：架构决策记录。

## 数据与隐私

`data/` 保存本机资料库、会话、中间结果、Job 与产物，受 Git 忽略。克隆仓库不包含示范课程或凭据。**不要把原始资料、密钥或生成的书稿提交到公开仓库。**
