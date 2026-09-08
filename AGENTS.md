# AGENTS.md

CourseBookAgent — 把高校课堂资料（智云课堂字幕、学在浙大课件、上传讲义）整理成课程教辅书的教学智能体（启真问智比赛项目）。

本文件是地图，不是百科。细节在 `docs/` 中。

## 每次任务开始前读

- `docs/PRODUCT_HANDOFF.md`：产品交接总文档，理解目标、输入输出、比赛策略
- `docs/ARCHITECTURE.md`：系统架构与模块划分
- `docs/WORKFLOW.md`：生成工作流的具体设计
- `docs/decisions/008-product-workbench-application-layer.md`：资料工作台应用层边界（必读，涉及产品层与生成核心的分工）

## 需要时读

- `docs/PRD.md`：产品需求文档
- `docs/COMPETITION.md`：比赛定位与申报话术
- `docs/examples/OUTPUT_SPEC.md`：教辅书输出格式示例
- `docs/API.md`：所有 HTTP 接口契约
- `docs/API_ZHIYUN.md`：智云课堂数据获取接口
- `docs/decisions/`：架构决策记录
- `docs/DEVELOPMENT.md`：AI 接手、协作、分支、验证与文档同步协议

## 开发命令

```bash
uv sync                                                 # 安装依赖
uv run python -m unittest discover -s tests -v          # 跑后端测试
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000  # 起后端
cd frontend && npm install && npm run dev               # 起前端 dev server（/api 代理到 8000）
uv run python -m coursebook_agent.cli --course-id 82493 --plan-only  # 生成全书蓝图
uv run python -m coursebook_agent.cli --course-id 82493 --only 2,3,4 --regenerate --review  # 重生成指定讲次
uv run python scripts/overnight_book_quality.py --course-id 82493 --review  # 全量重跑
uv run python scripts/check_offline.py                   # 离线确定性回归
cd frontend && npm run build && npm run lint             # 前端构建与 lint
```

## 模块边界

- `sources/zhiyun.py`、`sources/xuezai/assist.py`：分别从智云课堂和学在浙大获取资料；不碰生成逻辑；不依赖外部 skill。实时刷新依赖会话文件或环境变量。
- `agent/`：生成核心——`digest.py`（字幕压缩）、`editor.py`（全书规划）、`chapter.py`（分章撰写）、`synthesize.py`（全书合成）、`quality.py`（质量门禁）、`llm.py`（LLM 客户端）。**这是队友的工作线，不要轻易改动**。
- `renderer/`：只负责渲染 Markdown，不做生成。
- `preprocess/`：字幕清洗分块，纯确定性逻辑，不调 LLM。
- `product/`：产品工作台应用层。资料集、资源版本、输入快照、工作流预设、结构化运行投影与独立产物。包含 `api.py`（`/api/product/*`）、`service.py`（SQLite 落盘 + 内容寻址 blob）、`projections.py`（Job → 结构化投影）、`parsers.py`（多格式文档解析）。
- `frontend/`：React 前端，包含 9 页产品工作台（资料库、资料集详情、工作流配置、运行中心、运行详情、产物列表、产物阅读、系统设置），全部连接 `/api/product/*`。
- 生成结果与资料集缓存在 `data/`。原始 `data/cache/zhiyun/`（字幕）、`data/cache/xuezai/`（我的课程、课件列表）、`data/product/`（资料集 SQLite + blob + 文本）均受 Git 忽略。

## 工作规则

- 核心目标：让输出像一本可复习的教辅书，不是讲次摘要拼接。
- 当前对外叙述以教师使用为主：课程资产沉淀、讲义草稿和人工审核；学生复习是自然的第二场景。
- 产品层与生成核心的分工：
 - 产品层（`product/` + 前端）：资料管理、快照、运行投影、产物身份、用户可见的工作流配置。
 - 生成核心（`agent/` + `pipeline.py`）：按 `preset_id` 与 `snapshot_id` 接收上下文，产出 `CourseBook`。
 - 共享：Job request 新增 `snapshot_id` / `preset_id` / `lecture_indices` / `concurrency` 字段；旧的 `course_id` 仍可单独使用。
- 资料层扩展：除智云课堂字幕外，已支持 PPTX、PDF、DOCX、Markdown、TXT 上传，以及学在浙大课件下载。新加 provider 必须有独立适配器与独立会话。
- 前端只是展示和任务可见性；核心发力点是生成工作流与成品质量。
- 新增功能必须回答：它是否让"课程 → 教辅书"的输出更稳、更像成稿，或显著改善现场演示？
- 遇到生成卡住、失败或进度异常，先建立可复现测试并分别验证任务、LLM、并发、锁和前端轮询，不把现象直接写成根因。
- 代码与文档同步更新；涉及数据结构、持久化、工作流方向或比赛口径的复杂改动先写 ADR 到 `docs/decisions/`。
- 当前 Git 基线是 `main` / `origin/main`；任务应从独立分支开始；完成后跑检查、提交小步 commit，并先检查再合并。
- 任何改动都要跑后端测试；前端改动还必须构建并 lint：`uv run python -m unittest discover -s tests -v`、`cd frontend && npm run build && npm run lint`。
- 当前 `data/` 被 Git 忽略，只能作为本机实验数据；不要把凭据、原始字幕或生成产物提交到仓库。

## 已知遗留（与本次合并无关，需协调修复）

- `tests/test_core.py::test_warning_render` 断言 `⚠️` emoji，但 `fix: 修复quality.py` 把 warning 渲染输出改成了 `【易错】` 文字。该测试断言与渲染代码不一致，需要队友在他们的分支上同步修复测试期望。本工作台分支未触及 `renderer/` 或 `agent/quality.py`。