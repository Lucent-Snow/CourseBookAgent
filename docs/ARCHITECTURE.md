# CourseBookAgent 技术架构

## 1. 技术定位

CourseBookAgent 的核心是**课堂资料 → 教辅书的生成工作流**，由"产品工作台"和"生成核心"两层组成。

| 层 | 技术 | 说明 |
|---|---|---|
| 数据获取 | 项目内置 Zhiyun / Xue Zai ZJU adapter | 智云课堂字幕 + 课件页，学在浙大原始课件，不依赖外部 skill |
| 后端 | Python + FastAPI + SQLite | 编排长任务、产品工作台应用层、本地元数据 |
| AI | 通用大模型 API（OpenAI 兼容） | 生成工作流的核心 |
| 存储 | 本地文件 + SQLite | 中间产物全缓存，资料集元数据 + 内容寻址 blob |
| 前端 | React + TypeScript + Vite + Tailwind + shadcn | 9 页产品工作台 + 旧兼容页 |
| 输出 | Markdown / Web 阅读器 | 组件化渲染；PDF 尚未实现 |

---

## 2. 模块划分

```text
coursebook_agent/
├── app.py                  # FastAPI 入口；同时挂载 /api/courses、/api/jobs 等旧路由与 /api/product/*
├── config.py               # 配置（LLM / 智云 / 路径）
├── models.py               # 生成核心数据模型（Course / Lecture / TimedChunk / LectureDigest / BookPlan / LectureDraft / CourseBook）
├── pipeline.py             # 生成工作流编排（并发章节 Agent）
├── sources/
│   ├── zhiyun.py           # 智云课堂适配器：课程列表、讲次、字幕、PPT 时间轴
│   └── xuezai/
│       └── assist.py       # 学在浙大适配器：CAS 登录、我的课程、课件列表、文件下载
├── preprocess/
│   ├── transcript.py       # 字幕清洗 + 分块
│   └── teaching_signals.py # 教学信号预处理
├── agent/
│   ├── digest.py           # 字幕压缩
│   ├── editor.py           # 全书规划（主编）
│   ├── chapter.py          # 分章撰写
│   ├── synthesize.py       # 全书合成（终审）
│   ├── quality.py          # 质量门禁（组件契约 / 例子清理 / 确定性门禁 / LLM 审校）
│   ├── style_rules.py      # 写作风格规则
│   └── llm.py              # LLM 客户端（重试 / JSON 修复）
├── renderer/
│   └── markdown.py         # Markdown 渲染（含组件）
├── product/                # 产品工作台应用层
│   ├── api.py              # /api/product/* 路由
│   ├── service.py          # SQLite + 内容寻址 blob 持久化
│   ├── models.py           # Dataset / Resource / ResourceRevision / InputSnapshot / WorkflowPreset / AgentProjection / RunProjection / ArtifactSummary
│   ├── parsers.py          # 多格式文档解析（PDF/DOCX/PPTX/Markdown/TXT）
│   ├── projections.py      # JobState → RunProjection / ArtifactSummary
│   └── __init__.py         # 导出 ProductService
├── frontend/               # React 前端（9 页产品工作台 + 旧兼容页）
├── profiles/               # 课程 Profile（术语表/章节模板）
└── scripts/
    ├── overnight_book_quality.py  # 全量批处理
    └── check_offline.py            # 离线确定性回归
```

---

## 3. 产品工作台应用层（与生成核心的边界）

产品工作台是独立的"应用层"，不修改生成核心，只扩展它的请求契约。详见 `docs/decisions/008-product-workbench-application-layer.md`。

```text
用户上传 / 导入
    ↓
Dataset (SQLite)
    ↓ 选取资源版本
InputSnapshot (SHA-256 锁定)
    ↓ 创建 Run
GenerateRequest { snapshot_id, preset_id, lecture_indices, concurrency, ... }
    ↓
CourseBookPipeline（既有逻辑，新增参数透传）
    ↓
JobState (in-memory + 落盘)
    ↓
projections.project_run / project_artifact
    ↓
RunProjection / ArtifactSummary
    ↓
独立 ArtifactSummary（按 job_id 区分，同课程多次生成互不覆盖）
```

- 资源 `source_type` 区分 `upload` / `zhiyun` / `xuezai`；`provider` 区分 `zhiyun` / `xue_zai_zju`。
- 同一资源多次上传会生成新的 `revision_id`；旧版本仍可在快照中引用。
- 快照 `SHA-256` 锁定资源版本集合，避免"运行引用资料但资料被改"的隐蔽问题。
- `lecture_indices` 透传给 `pipeline.generate_course(only_indices=...)`，并发参数 `concurrency` 透传给 `asyncio.Semaphore` 限流。
- `preset_id` 默认 `coursebook`，作为未来多 profile 工作流的扩展点。

---

## 4. 核心数据模型

生成核心的关键模型（`coursebook_agent/models.py`）：

| 模型 | 层 | 用途 |
|---|---|---|
| `TimedChunk` | 0 | 分块后的字幕单元，带时间戳 |
| `KnowledgePoint` | 1 | 单个知识点（名/描述/类别/来源引用） |
| `LectureDigest` | 1 | 一讲的压缩知识点地图 |
| `ComponentSpec` | 2 | 可复用的 UI 组件规范 |
| `ChapterInstruction` | 2 | 主编给某一章的写作指令 |
| `BookPlan` | 2 | 主编的完整蓝图 |
| `ChapterSection` | 3 | 章节中的小节（含组件实例和时间链接） |
| `LectureDraft` | 3 | 一章的完整产物 |
| `CourseBook` | 4 | 全书产物 |

产品工作台的关键模型（`coursebook_agent/product/models.py`）：

| 模型 | 用途 |
|---|---|
| `Dataset` | 资料集，长期容器 |
| `Resource` | 单份资料；可来自上传 / 智云 / 学在浙大 |
| `ResourceRevision` | 资料的某个版本（SHA-256 内容寻址） |
| `InputSnapshot` | 一次运行所引用的资料版本快照（哈希锁定） |
| `WorkflowPreset` | 工作流预设（`coursebook` 是当前唯一内置） |
| `AgentProjection` | 一个章节 Agent 的结构化状态 |
| `RunProjection` | 一次 Job 的结构化视图 |
| `ArtifactSummary` | 一个产物（按 job_id 区分） |

---

## 5. 缓存策略

每一层的产物都缓存在 `data/` 下，支持断点续跑：

```text
data/
├── cache/
│   ├── zhiyun/             # 原始字幕 + 课程/讲次缓存
│   └── xuezai/             # 我的课程 + 课件列表缓存
├── intermediate/
│   ├── digest-*.json       # 字幕压缩产物
│   ├── chunks-*.json       # 清洗分块
│   ├── chapter-*.json      # 分章产物
│   └── coursebook-*.json   # 全书产物
├── plans/
│   └── bookplan-*.json     # 全书蓝图
├── output/
│   ├── coursebook-*.md     # 最终 Markdown
│   └── lecture-*.md        # 单章 Markdown
└── product/                # 产品工作台持久化
    ├── product.sqlite3     # 资料集 / 资源 / 快照元数据
    ├── blobs/              # 内容寻址 blob（SHA-256 文件名）
    └── text/               # 解析后的文本（按 revision_id）
```

---

## 6. API

完整契约见 `docs/API.md`。

| 路由族 | 路径前缀 | 说明 |
|---|---|---|
| 健康 | `/api/health` | 健康 + 配置状态 |
| 智云（旧） | `/api/zhiyun/*`、`/api/courses`、`/api/books` | 兼容路径，仍可用 |
| 任务（旧） | `/api/generate`、`/api/jobs/*`、`/api/runs/*` | Job 调度 + 报告 |
| 设置 | `/api/settings`、`/api/settings/llm` | LLM 配置保存 |
| 缓存清理 | `/api/cache` | 清派生产物 |
| **产品工作台（新）** | `/api/product/*` | 资料集、上传、快照、导入、运行投影、产物 |
| 静态 | `/static/*` | 内置旧 SPA |

产品工作台关键路由：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/product/datasets` | 资料集列表 / 新建 |
| GET/DELETE | `/api/product/datasets/{id}` | 资料集详情 / 删除 |
| POST | `/api/product/datasets/{id}/resources` | 上传 PDF/DOCX/PPTX/MD/TXT |
| GET | `/api/product/imports/zhiyun/courses` | 智云课堂"我的课程" |
| GET | `/api/product/imports/zhiyun/courses/{id}` | 智云课堂讲次列表 |
| POST | `/api/product/datasets/{id}/imports/zhiyun` | 智云课堂讲次 + 课件导入 |
| GET | `/api/product/imports/xuezai/courses` | 学在浙大"我的课程" |
| GET | `/api/product/imports/xuezai/courses/{id}` | 学在浙大课件列表 |
| POST | `/api/product/datasets/{id}/imports/xuezai` | 学在浙大课件下载导入 |
| POST | `/api/product/auth/login` | 统一身份认证登录（智云 + 学在浙大） |
| GET | `/api/product/auth/providers` | 两个 provider 的连接状态 |
| GET/POST | `/api/product/datasets/{id}/snapshots` | 输入快照列表 / 创建 |
| GET | `/api/product/resource-revisions/{id}/preview` | 解析文本预览 |
| GET | `/api/product/workflow-presets` | 工作流预设列表 |
| GET | `/api/product/runs[/{id}]` | 结构化运行投影 |
| GET | `/api/product/artifacts[/{id}]` | 独立产物（含 CourseBook） |

`POST /api/generate` 新增可选字段：`snapshot_id`、`preset_id`、`lecture_indices`、`concurrency`。旧请求仍兼容。

---

## 7. 关键设计决策

### 7.1 压缩 vs 完整的分层

主编只看压缩摘要（~2 万字），不看完整字幕（~30 万字）。写作者看完整字幕。这解决了上下文限制问题，同时保留了主编的全局视角。

### 7.2 组件化输出

主编定义"书长什么样"：Tips 框、例题格式、侧边栏、重点标记。写作者按规范使用组件。渲染器根据目标格式（Web/PDF）适配。

### 7.3 时间戳链接

Web 版当前保留时间链接字段，但尚未真正接入智云播放器跳转。PDF 输出尚未实现。

### 7.4 并行章节生成

分章撰写是全书生成的主要耗时环节。`pipeline.generate_course` 用 `asyncio.Semaphore` 限流并发执行各章，默认并发 3；承上启下依赖 `ChapterInstruction` 的桥接字段兜底，不依赖上一章的生成结果。`concurrency` 参数可在产品工作台运行时由用户覆盖。

### 7.5 质量门禁

`agent/quality.py` 提供统一的写盘前清理：组件契约（未知组件归并、steps 数组展开）、例子清理（Python dict 残留转文本）、确定性门禁、LLM 审校。主流程默认应用前两者，全量门禁循环是下一迭代目标。

### 7.6 多 provider 数据源

`product/` 不内嵌具体数据源实现，而是按 `provider` 字段区分来源。智云课堂与学在浙大各自有独立适配器和独立会话，互不干扰。新 provider 必须遵循这一边界。

### 7.7 资料集与输入快照

- 资料集是长期容器，可能同时包含字幕、PPT、PDF、Word。
- 输入快照是某次运行所引用的资源版本集合，按 SHA-256 锁定，避免"资料被改但运行引用了旧版本"的隐性 bug。
- 同一课程多次运行产生不同 job_id，从而不同 `ArtifactSummary`，互不覆盖。

### 7.8 生成核心零侵入

`product/` 不修改 `pipeline.py`、`agent/quality.py`、`renderer/markdown.py`。两者通过 `preset_id` / `snapshot_id` / `lecture_indices` / `concurrency` 四个扩展参数对接。`pipeline.py` 已接受 `only_indices` 和 `concurrency`，其余透传。