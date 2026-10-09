# CourseBookAgent 技术架构

> 2026-10-09。最新验证和待办见 `CURRENT_STATUS.md`；阶段契约见 `WORKFLOW.md`；实际 HTTP 字段见 `API.md`。

## 1. 分层

| 层 | 实现 | 职责 |
|---|---|---|
| 资料源 | 内置智云/学在浙大 adapter；文件上传 | 获取课程资料，各 provider 独立会话，不依赖外部 skill |
| 产品应用层 | Python/FastAPI/SQLite，`product/` | 资料集、原文件/版本、文本、快照、预设、结构化运行与产物投影 |
| 生成核心 | `agent/`、`assembly/`、`pipeline.py` | description、主题章节规划、Tag、原资料装配、写作、检查、合成 |
| 生命周期 | `app.py` | Job 调度、落盘、停止/恢复、错误与 usage、共享设置 |
| 渲染 | `renderer/markdown.py` + React BookReader | 确定性 Markdown 与网页阅读，不做生成 |
| 迭代工具 | `lab.py` / `scripts/lab.py` | 独立阶段运行、缓存与查看，复用生成核心 |

前端为 React/TypeScript/Vite/Tailwind/shadcn，8 页工作台；旧兼容页、旧 CLI、旧静态 SPA 已删除。系统输出为 Markdown/网页，完整 PDF 确认稿是另行排版，未接系统。

## 2. 模块入口

```text
coursebook_agent/
├── app.py                     # HTTP、Job 生命周期、设置
├── config.py / models.py      # 环境配置、生成数据模型
├── pipeline.py                # CourseBookPipeline.run 唯一总入口
├── lab.py                     # 各阶段操作与缓存
├── sources/zhiyun.py           # 智云资料
├── sources/xuezai/assist.py    # 学在浙大 + CAS/SMS
├── preprocess/                # 字幕清洗/分块、教学信号
├── agent/                     # describe/editor/chapter/synthesize/quality/llm
├── assembly/assemble.py       # Tag → ChapterContext 纯函数
├── renderer/markdown.py       # CourseBook → Markdown
├── product/                   # API/service/models/parsers/projections/snapshot_loader
└── profiles/                  # 课程模板与术语约束
frontend/src/                  # 8 页产品工作台与 BookReader
scripts/lab.py                 # 分阶段实验 CLI
scripts/check_offline.py       # 外网禁止的离线回归
```

ADR 008 的应用层边界仍有效，旧“保留全部 legacy API”的迁移条款已经被当前代码取代。生成核心是队友工作线，不随意重写。

## 3. 数据与请求

```text
Dataset → Resource/ResourceRevision → InputSnapshot
       → POST /api/generate → JobState → CourseBookPipeline.run
       → CourseBook → project_run/project_artifact → 前端
```

资料集是长期容器；资源版本存 SHA-256 与解析文本；快照锁定本次 revision 集合。快照保证输入版本固定，不保证模型重跑输出完全相同。

`GenerateRequest`：必须有 snapshot_id，可选 course_id，regenerate/review/concurrency/chapter_indices。默认 review=True、concurrency=3。preset_id 目前存在于预设和投影，未驱动多预设核心；lecture_indices 是旧契约，不替代 chapter_indices。

Python `run()` 还允许 course_id-only 来源加载，但 HTTP 不允许。dataset_name 从产品层传入核心，生成核心的 CourseBook 保留课程基本元信息。

## 4. 模型与资料分配

| 模型 | 用途 |
|---|---|
| ParsedResource / units / location | 每份资料的文本、结构单元与来源位置 |
| ResourceDescription | LLM 五栏目 body + topic/knowledge_topics/scope/suggested_role 等索引字段 |
| BookPlan / ChapterInstruction / ComponentSpec | 全书主题结构、章节要求、风格、Tag 和组件规范 |
| ChapterContext | 章指令、原始章资料、global 资料及写作约束 |
| LectureDraft / ChapterSection / ChapterComponent | 章节草稿、小节和组件；LectureDraft 名称保留，但语义为知识章节 |
| CourseBook | 章节 + 前言/使用说明/知识地图/学习路径/术语/索引/核验备注 |
| RunProjection / ArtifactSummary | Job 的前端视图，不是另一份独立书稿数据库 |

`resource_tags[revision_id]` 可以含多个 chapter_id，`__global__` 进入各章，无 Tag 排除。原文分配由纯函数装配，主 Agent 不控制运行流程。

所有资料经 LLM description，失败才启发式降级。description 并发 4，章节按请求限流。上一章摘要只在已有缓存时可用，并发并不保证顺序依赖。

## 5. 存储与身份边界

```text
data/
├── product/product.sqlite3   # Dataset/Resource/Revision/Snapshot
├── product/blobs/            # SHA-256 原文件
├── product/text/             # revision 解析文本
├── cache/zhiyun/、xuezai/      # 平台数据缓存
├── intermediate/descriptions/description-{revision_id}.json
├── plans/bookplan-{snapshot_id}.json
├── intermediate/chapter-{snapshot_id}-{chapter_id}.json
├── intermediate/coursebook-{course_id或snapshot_id}.json
├── output/coursebook-{course_id或snapshot_id}.md
└── jobs/{job_id}.json         # Job 请求/状态/事件/完整 CourseBook
```

- 章节按快照隔离，description 按 revision 跨快照复用。
- 产品按 Job ID 阅读存于 Job 的书稿；全书 JSON/Markdown 仍按 course/snapshot 命名，同键重跑可覆盖文件。下载端点按 course_id 或 run_id 查找文件，与产物身份并未完全统一，需验证旧版本下载不会串书。
- Lab 阶段缓存不自动成为产品 Job/Artifact；真实示例的工作台接入是待办。
- data、会话、原字幕和输出受 Git 忽略。公网部署/演示交接需单独安排数据与持久磁盘，不依赖临时容器目录。

## 6. 长任务与可靠性

Job 在内存调度、原子写文件；启动时重新载入并把 running 标为 interrupted。支持 cancel/retry，复用同一 Job 和原请求；不代表失败缓存一定会重算。运行核心会复用身份匹配的缓存，失败/降级草稿可能阻碍精准恢复。

LLMClient 流式接收、请求重试、JSON 修复、usage 统计；不传 max_tokens。默认600秒，description/审校300秒，规划/章节/合成900秒；网页任务5400秒。usage 为上游提供值，没有返回就不伪造。

确定性组件/例子检查及可选章节审校已实现，全书自动审稿/回炉未实现。来源字段、警告与模型自审不等于教师事实确认。

## 7. 页面与接口

前端路由：`/datasets`、`/datasets/:id`、`/datasets/:id/configure`、`/runs`、`/runs/:id`、`/artifacts`、`/artifacts/:id`、`/settings`。导入为对话框。

- `/api/product/*`：资料、快照、provider、预设、运行/产物投影、实验台。
- `POST /api/generate`、`/api/runs/*`：生成、状态、停止/恢复、报告与下载。
- `/api/settings*`、`/api/health`、`/api/cache`：共享基础设施。
- 旧 `/api/courses`、`/api/jobs`、`/api/books` 返回404，有迁移回归测试。

设置和删除接口当前按本机应用设计，发布前需要访问边界；公开展示不必开放无限生成。播放器跳转、系统 PDF 与公网部署尚待实现/验收。
