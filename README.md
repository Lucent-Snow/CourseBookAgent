# CourseBookAgent

把高校课堂资料（智云课堂字幕、学在浙大课件、上传讲义）整理成结构化课程教辅书的教学智能体。

## 架构

- **后端** FastAPI + Python + SQLite：
 - 生成核心（`agent/` + `pipeline.py`）：字幕压缩 → 全书规划 → 分章撰写（并发）→ 质量门禁 → 全书合成
 - 产品工作台（`product/`）：资料集、资源版本、输入快照、工作流预设、结构化运行与独立产物
 - 数据源适配（`sources/zhiyun.py` + `sources/xuezai/assist.py`）：智云课堂字幕/课件页、学在浙大原始课件下载；学在浙大会话保存在 `XUEZAI_SESSION_FILE` 指定的位置
- **前端** React 19 + TypeScript + Vite + Tailwind 4 + shadcn/ui：9 页产品工作台（资料库、资料集详情、工作流配置、运行中心、运行详情、产物列表、产物阅读、系统设置）+ 旧兼容页（书架 / 工作台 / 阅读器）
- **质量门禁** `agent/quality.py`：组件契约、例子清理、确定性门禁、可选 LLM 审校
- **开发交接** `AGENTS.md` 是文档入口，`docs/DEVELOPMENT.md` 是协作与验证协议

## 运行

### 后端

```bash
uv sync
cp .env.example .env
# 在 .env 中填入自己的 LLM 端点、模型名、API key
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173，/api 代理到 8000
```

浏览器打开 `http://localhost:5173`，默认进入 `/datasets`（产品工作台）。
旧 URL（`/workspace`、`/read/:courseId`、`/review`）仍可用。

## 测试

```bash
uv run python -m unittest discover -s tests -v   # 后端测试
uv run python scripts/check_offline.py            # 离线确定性回归
cd frontend && npm run build && npm run lint      # 前端构建与 lint
```

## API

资料集与生成走 `/api/product/*`；生成触发、运行生命周期和共享设置在 `app.py`。

- 资料集：`/api/product/datasets`、上传 `/api/product/datasets/{id}/resources`、快照 `/api/product/datasets/{id}/snapshots`
- 智云导入：`/api/product/imports/zhiyun/courses`、`/api/product/datasets/{id}/imports/zhiyun`
- 学在浙大导入：`/api/product/imports/xuezai/courses`、`/api/product/datasets/{id}/imports/xuezai`
- 统一身份认证：`/api/product/auth/login`（一次登录同时取智云 + 学在浙大会话）
- 运行投影：`/api/product/runs[/{run_id}]`、`/api/product/artifacts[/{artifact_id}]`
- 触发生成：`POST /api/generate`（body 必须带 `snapshot_id`）
- 运行生命周期：`POST /api/runs/{run_id}/retry`、`POST /api/runs/{run_id}/cancel`、`GET /api/runs/{run_id}/download.md`
- 共享：`GET /api/health`、`GET /api/settings`、`PUT /api/settings/llm`、`POST /api/settings/llm/test`、`DELETE /api/cache`

详细契约见 `docs/API.md`。

## 说明

- 生成结果缓存在 `data/`：`cache/zhiyun/`（原始字幕）、`cache/xuezai/`（我的课程/课件列表，勿删）、`intermediate/`（中间产物）、`output/`（Markdown）。
- 资料集与产物元数据在 `data/product/`（SQLite + 内容寻址 blob + 解析文本）。
- `data/` 里的旧产物作为**反面案例**保留，用于对照 prompt 与生成结果迭代。
- 详细设计见 `docs/`，问题清单见 `docs/ISSUES.md`，架构决策见 `docs/decisions/`。
