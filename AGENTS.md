# AGENTS.md

CourseBookAgent — 把高校课堂资料（智云课堂字幕、学在浙大课件、上传讲义）整理成课程教辅书的教学智能体（启真问智比赛项目）。

本文件是地图，不是百科。细节在 `docs/` 中。

## 每次任务开始前读

- `docs/CURRENT_STATUS.md`：当前实现、验证结果、已知缺口与下一步；不要用旧报告覆盖这里的状态
- `docs/PRODUCT_HANDOFF.md`：产品交接总文档，理解目标、输入输出、比赛策略
- `docs/ARCHITECTURE.md`：系统架构与模块划分
- `docs/WORKFLOW.md`：生成工作流的具体设计
- `docs/decisions/008-product-workbench-application-layer.md`：资料工作台应用层边界（必读，涉及产品层与生成核心的分工）

## 需要时读

- `docs/DECOMPOSITION.md`：拆解设计——每一步解决什么问题、契约、判断标准、置信度（🟢策略级/🟡参数级）
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
uv run python scripts/check_offline.py                   # 离线确定性回归
cd frontend && npm run build && npm run lint             # 前端构建与 lint
```

## 模块边界

- `pipeline.py`：唯一入口 `CourseBookPipeline.run()`；输入快照之后按 7 阶段（parse → describe → plan + Tag → assemble → generate + 章节检查 → synthesize → render）执行；旧 per-lecture 入口已删除。
- `sources/zhiyun.py`、`sources/xuezai/assist.py`：分别从智云课堂和学在浙大获取资料；不碰生成逻辑；不依赖外部 skill。实时刷新依赖会话文件或环境变量。
- `agent/`：生成核心——`describe.py`（逐份资料 description）、`editor.py`（主 Agent 全书规划、Tag 装配）、`chapter.py`（分章撰写）、`synthesize.py`（全书合成）、`quality.py`（质量门禁）、`llm.py`（LLM 客户端）。**这是队友的工作线，不要轻易改动**。
- `assembly/`：按 Tag 装 `ChapterContext`；纯函数。
- `renderer/`：只负责渲染 Markdown / Web 阅读器，不做生成。
- `preprocess/`：字幕清洗分块，纯确定性逻辑，不调 LLM。
- `product/`：产品工作台应用层。资料集、资源版本、输入快照、工作流预设、结构化运行投影与按 Job 阅读的产物（导出文件的版本隔离仍待统一）。包含 `api.py`（`/api/product/*`）、`service.py`（SQLite 落盘 + 内容寻址 blob）、`projections.py`（Job → 结构化投影）、`parsers.py`（多格式文档解析）、`snapshot_loader.py`（snapshot → ParsedResource）。
- `frontend/`：React 前端，包含 8 页产品工作台（资料库、资料集详情、工作流配置、运行中心、运行详情、产物列表、产物阅读、系统设置）；资料与投影使用 `/api/product/*`，生成、恢复、导出和设置使用共享 `/api/*`。
- 生成结果与资料集缓存在 `data/`。原始 `data/cache/zhiyun/`（字幕）、`data/cache/xuezai/`（我的课程、课件列表）、`data/product/`（资料集 SQLite + blob + 文本）均受 Git 忽略。

## 工作规则

- 核心目标：让输出像一本可复习的教辅书，不是讲次摘要拼接。
- 对外叙述面向所有学生：上传自己的课程资料是主路径；智云课堂/学在浙大接入是浙大学生的便捷选项，不是核心卖点。
- 产品层与生成核心的分工：
 - 产品层（`product/` + 前端）：资料管理、快照、运行投影、产物身份、用户可见的工作流配置。
 - 生成核心（`agent/` + `pipeline.py`）：接收快照上下文，产出 `CourseBook`。
 - HTTP 生成请求必须提供 `snapshot_id`；可选 `course_id` 仅作元信息。实际字段为 `regenerate` / `review` / `concurrency` / `chapter_indices`；`preset_id` 目前是产品预设/投影概念，不是可切换的生成参数。Python 入口仍可单独接收 `course_id`，不等于 HTTP 兼容旧入口。
- 资料层扩展：除智云课堂字幕外，已支持 PPTX、PDF、DOCX、Markdown、TXT 上传，以及学在浙大课件下载。新加 provider 必须有独立适配器与独立会话。
- 前端只是展示和任务可见性；核心发力点是生成工作流与成品质量。
- 新增功能必须回答：它是否让"课程 → 教辅书"的输出更稳、更像成稿，或显著改善现场演示？
- 遇到生成卡住、失败或进度异常，先建立可复现测试并分别验证任务、LLM、并发、锁和前端轮询，不把现象直接写成根因。
- 代码与文档同步更新；涉及数据结构、持久化、工作流方向或比赛口径的复杂改动先写 ADR 到 `docs/decisions/`。
- 当前 Git 基线是 `main` / `origin/main`；任务应从独立分支开始；完成后跑检查、提交小步 commit，并先检查再合并。
- 任何改动都要跑后端测试；前端改动还必须构建并 lint：`uv run python -m unittest discover -s tests -v`、`cd frontend && npm run build && npm run lint`。
- 当前 `data/` 被 Git 忽略，只能作为本机实验数据；不要把凭据、原始字幕或生成产物提交到仓库。
- 所有资料（包括字幕）均经 LLM 生成五栏目 description；启发式仅为失败降级，不能恢复旧的 transcript fast-path。
- 长 LLM 调用使用流式响应，不传 `max_tokens`；保留 usage 统计与分层超时。
- 当前已有真实 12 章全书与单独排版的 PDF 确认稿；系统 PDF 导出、在线部署、失败章节精准续跑与全书自动审稿仍待补齐。实验产物不能自动视为工作台已有产物。
- 下一阶段围绕比赛 demo：产品展示、恢复/保存/预览/导出、访问网页、文档与 PPT。逐步验收，不擅自重跑全书或把实验台接进前端。

## 实验台（逐阶段 prompt 迭代）

`scripts/lab.py` 把 `CourseBookPipeline.run()` 拆成 5 个独立可调用的阶段，每个阶段自带缓存：

```bash
uv run python scripts/lab.py status    --snapshot snap-1
uv run python scripts/lab.py describe  --snapshot snap-1 [--force] [--revision rev-abc]
uv run python scripts/lab.py plan      --snapshot snap-1 [--force]
uv run python scripts/lab.py assemble  --snapshot snap-1
uv run python scripts/lab.py generate  --snapshot snap-1 --chapter c1 [--force]
uv run python scripts/lab.py synthesize --snapshot snap-1 [--force]
uv run python scripts/lab.py show descriptions|plan|chapters|chapter --snapshot snap-1 [--revision|--chapter]
```

工作循环：跑一个阶段 → `show` 看产物 → 不满意就改 `agent/*.py` 里的 prompt → 加 `--force` 重跑那一个阶段 → 通过后再跑下一个。

JSON 到 stdout（方便 `jq` / `grep` / `diff`），人读摘要到 stderr。

同样的能力通过 API 也开放了，方便前端和远端调用：

```
GET    /api/product/snapshots/{id}/lab/status
POST   /api/product/snapshots/{id}/lab/describe         body: {force?, revision_id?}
POST   /api/product/snapshots/{id}/lab/plan             body: {force?}
POST   /api/product/snapshots/{id}/lab/assemble
POST   /api/product/snapshots/{id}/lab/chapters/{chapter_id}/generate   body: {force?, review?}
POST   /api/product/snapshots/{id}/lab/synthesize        body: {force?}
GET    /api/product/snapshots/{id}/lab/descriptions
GET    /api/product/snapshots/{id}/lab/descriptions/{revision_id}
GET    /api/product/snapshots/{id}/lab/plan
GET    /api/product/snapshots/{id}/lab/chapters
GET    /api/product/snapshots/{id}/lab/chapters/{chapter_id}
DELETE /api/product/snapshots/{id}/lab/descriptions[/{revision_id}]
DELETE /api/product/snapshots/{id}/lab/plan
DELETE /api/product/snapshots/{id}/lab/chapters[/{chapter_id}]
```
