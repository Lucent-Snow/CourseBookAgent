# CourseBookAgent · 智课成书

将高校课程的字幕、课件、讲义与笔记整理成按知识主题组织的课程教辅书。学生上传自己的资料是主路径；智云课堂和学在浙大是浙大学生的便捷接入。

## 当前状态

核心多资料流程已用真实课程完成 12 章全书：解析 → 五栏目资料说明 → 全书规划与 Tag → 上下文装配 → 分章生成/检查 → 全书合成 → Markdown。已有完整 PDF 审阅稿，但 PDF 排版未接入系统。下一阶段围绕比赛产品展示、恢复与保存验收、预览/导出、网页部署与提交材料。

代码迁移和生成优化在 `chore/v2-cleanup-and-rebrand`，当前文档交接在 `docs/current-state-and-team-handoff`，尚未合 main。最新事实从 [CURRENT_STATUS](docs/CURRENT_STATUS.md) 阅读；简版 [PRD](docs/PRD.md) 解释为什么做和如何成书。

## 架构

- Python/FastAPI/SQLite：资料集、文件版本、快照、Job 生命周期和运行投影。
- 生成核心：description、主题式规划、Tag、章写作和合成；独立实验台支持逐阶段迭代。
- React/TypeScript/Vite：8 页产品工作台与成品阅读。旧兼容页和旧 CLI 已删除。
- 当前系统输出：结构化 CourseBook、Markdown 与 Web 阅读内容。实验缓存不自动成为产品 Job。

## 运行

```bash
uv sync
cp .env.example .env
# 自行配置 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000
```

另一个终端：

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`；先建立资料集并上传/导入，创建快照后生成。`POST /api/generate` 必须有 snapshot_id；旧课程单入口和旧 `/api/courses`、`/api/jobs`、`/api/books` 不再提供。

## 验证

```bash
uv run python -m unittest discover -s tests -v
uv run python scripts/check_offline.py
cd frontend && npm run build && npm run lint
```

2026-10-09：后端及离线检查96/96通过，build通过，lint无错误、4条既有警告。真实校内登录、浏览器恢复和公网部署未在本轮重验。

## 文档与数据

- [AGENTS.md](AGENTS.md)：AI地图与边界；[DEVELOPMENT](docs/DEVELOPMENT.md)：协作/验证。
- [ARCHITECTURE](docs/ARCHITECTURE.md)、[WORKFLOW](docs/WORKFLOW.md)、[API](docs/API.md)：真实实现和接口。
- [DECOMPOSITION](docs/DECOMPOSITION.md)：逐阶段设计；[ISSUES](docs/ISSUES.md)：缺口；[COMPETITION](docs/COMPETITION.md)：比赛表达。

`data/` 保存本机资料库、会话、中间结果、Job和产物，受 Git 忽略。拉代码不包含示范课程或凭据；不要把原始资料、密钥或生成书稿提交公开仓库。不同资料和产物的当前完整性/恢复边界见 CURRENT_STATUS。
