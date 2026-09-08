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
├── models.py               # 生成核心数据模型（资料描述 / Tag / BookPlan / ChapterDraft / CourseBook 等）
├── pipeline.py             # 固定阶段编排；按主 Agent 章节规划与 Tag 组装上下文
├── sources/
│   ├── zhiyun.py           # 智云课堂适配器：课程列表、讲次、字幕、PPT 时间轴
│   └── xuezai/
│       └── assist.py       # 学在浙大适配器：CAS 登录、我的课程、课件列表、文件下载
├── preprocess/
│   ├── transcript.py       # 字幕清洗 + 分块
│   └── teaching_signals.py # 教学信号预处理
├── agent/
│   ├── describe.py         # 逐份资料 description
│   ├── digest.py           # 需要时整理字幕内容
│   ├── editor.py           # 主 Agent 全书规划、章节划分与 Tag
│   ├── chapter.py          # 按章节上下文撰写
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

生成核心的关键模型（`coursebook_agent/models.py`）。**生成链路按"资料 → description → 章节 → 产物"四层；不再按讲次 1:1 切章节**。

| 模型 | 层 | 用途 |
|---|---|---|
| `ParsedResource` / `ParsedResourceUnit` / `ResourceLocation` | 0 | 解析后的资料：智云字幕、智云课件页、上传 PDF/PPTX/DOCX/MD/TXT。`ResourceLocation.kind` 区分 `transcript_segment / slide / page / section`。 |
| `ResourceDescription` | 1 | 主 Agent 用的资料说明：topic / knowledge_topics / scope / suggested_role / summary。transcript 走启发式，其他资料走 LLM，失败 fallback。 |
| `ComponentSpec` | 2 | 可复用的 UI 组件规范 |
| `ChapterInstruction` | 2 | 主编（主 Agent 规划时输出）给某一章的写作指令，**chapter_id 稳定、与讲次解耦** |
| `BookPlan` | 2 | 主编的完整蓝图，包含 `chapter_resources / resource_tags / global_resource_ids / snapshot_id`。**章数由主题决定，不等于资料数**。 |
| `ChapterContext` | 2.5 | 章节 Agent 的完整输入：chapter + chapter resources + global resources + 写作 prompt + 组件规范。**由 `assemble_chapter_contexts` 按 Tag 装配**。 |
| `ChapterSection` / `ChapterComponent` | 3 | 章节中的小节（含组件实例） |
| `LectureDraft` | 3 | 一章的完整产物；新增 `chapter_id / used_resource_ids` |
| `CourseBook` | 4 | 全书产物；`course.name` 现在取自资料集名（可选 `course_id` 是 metadata） |

Tag 语义（`BookPlan.resource_tags: dict[revision_id, list[str]]`）：

- `chapter_id` 列表：资料进入这些章节 Agent 的上下文（一份资料可进多个章节）。
- `"__global__"`：资料作为全局上下文进入每个章节 Agent。
- 未列入：资料本次不参与生成。

产品工作台的关键模型（`coursebook_agent/product/models.py`）：

| 模型 | 用途 |
|---|---|
| `Dataset` | 资料集，长期容器。**生成绑定到 dataset，不再绑定到 course**。 |
| `Resource` | 单份资料；可来自上传 / 智云 / 学在浙大 |
| `ResourceRevision` | 资料的某个版本（SHA-256 内容寻址） |
| `InputSnapshot` | 一次运行所引用的资料版本快照（哈希锁定） |
| `WorkflowPreset` | 工作流预设（`coursebook` 是当前唯一内置） |
| `AgentProjection` | 一个章节 Agent 的结构化状态 |
| `RunProjection` | 一次 Job 的结构化视图；含 `dataset_id / dataset_name` |
| `ArtifactSummary` | 一个产物（按 job_id 区分） |
| `ResourceProjection` | 前端用的资料行：含 description 文本 + Tag（chapter/global/none + chapter_id 列表） |
| `StageProjection` | 前端用的 7 阶段进度计数器 |
| `QualityReport` | 前端用的每章质量扫描 |

---

## 5. 缓存策略

每一层的产物都缓存在 `data/` 下，支持断点续跑：

```text
data/
├── cache/
│   ├── zhiyun/             # 原始字幕 + 课程/讲次缓存
│   └── xuezai/             # 我的课程 + 课件列表缓存
├── intermediate/
│   ├── chunks-*.json       # 清洗分块
│   ├── descriptions/
│   │   └── description-<rev_id>.json  # 资料 description 缓存
│   ├── chapter-{snapshot_id}-{chapter_id}.json   # 章节产物（按 snapshot 分桶）
│   └── coursebook-<course_id>.json                # 全书产物
├── plans/
│   └── bookplan-{snapshot_id}.json  # 全书蓝图（按 snapshot 分桶）
├── output/
│   └── coursebook-<course_id>.md     # 最终 Markdown
└── product/                # 产品工作台持久化
    ├── product.sqlite3     # 资料集 / 资源 / 快照元数据
    ├── blobs/              # 内容寻址 blob（SHA-256 文件名）
    └── text/               # 解析后的文本（按 revision_id）
```

`chapter-{cid}.json` 在 v2 之前用 lecture_id 做后缀，会跨 snapshot 串台（详见 `docs/ISSUES.md`）。v2 用 `{snapshot_id}-{chapter_id}` 命名，按 snapshot 分桶。

---

## 6. API

完整契约见 `docs/API.md`。

| 路由族 | 路径前缀 | 说明 |
|---|---|---|
| 健康 | `/api/health` | 健康 + 配置状态 |
| 智云（旧） | `/api/zhiyun/*`、`/api/courses`、`/api/books` | 兼容路径，仍可用 |
| 任务（旧） | `/api/generate`、`/api/jobs/*`、`/api/runs/*` | Job 调度 + 报告（**v2 推荐用 `/api/generate/v2`**） |
| 设置 | `/api/settings`、`/api/settings/llm` | LLM 配置保存 |
| 缓存清理 | `/api/cache` | 清派生产物 |
| **产品工作台** | `/api/product/*` | 资料集、上传、快照、导入、运行投影、产物 |
| 静态 | `/static/*` | 内置旧 SPA |

产品工作台关键路由：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/product/datasets` | 资料集列表 / 新建 |
| GET/DELETE | `/api/product/datasets/{id}` | 资料集详情 / 删除 |
| POST | `/api/product/datasets/{id}/resources` | 上传 PDF/DOCX/PPTX/MD/TXT |
| GET | `/api/product/datasets/{id}/runs` | 该资料集的所有生成记录，按时间倒序 |
| DELETE | `/api/product/runs/{id}` | 删除运行（含其 asyncio task 与缓存） |
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

`/api/generate/v2` 是新的 v2 端点：`{ snapshot_id, course_id?, regenerate, review, concurrency, chapter_indices? }`。**`course_id` 可选**；生成绑定到 `snapshot_id` 所属的资料集。

---

## 7. 关键设计决策

### 7.1 v2 多资料工作流（核心约定）

新的固定工作流按"资料 → description → 章节规划 → 上下文装配 → 章节生成 → 合成 → 渲染"7 阶段执行（见 `docs/WORKFLOW.md`）。要点：

- **章节是书籍主题，不是讲次时间**。一份 transcript 不能直接等于一章；多份资料按主题合并成一个章节是主 Agent 的核心任务。
- **Tag 是上下文归属，不是流程控制**。Tag 决定一份资料进哪个/哪些章节 Agent 的上下文——"global" 进入每个章节的全局上下文；缺失 Tag = 本次不使用该资料。
- **章节 ID 是阅读顺序**。`chapter_id` (`c1 / c2 / ...`) 按主 Agent 决定的阅读顺序编号；同一份资料可同时进多个章节（`resource_tags[revision_id] = ['c1', 'c3']`）。
- **产品绑定到资料集而非课程**。`RunProjection.dataset_id / dataset_name` 是前端主标题；`course_id` 可选，仅作为 metadata 保留。
- **不变量**：主流程阶段固定，主 Agent 不能重新发明流程；Tag 只在装配阶段起作用。

### 7.2 资料与描述

- `ParsedResource` 是解析后的最小资料单元：智云字幕为 `transcript_segment`，智云课件为 `slide`，上传 PDF 为 `page`，DOCX / PPTX / MD 为 `section`。
- `ResourceDescription` 由 description Agent 生成：transcript 走确定性启发式（topic = 标题、knowledge_topics = 标题分词），其他资料走 LLM，失败 fallback。**description 让主 Agent 不读原文也能看到全局**。
- 描述缓存到 `data/intermediate/descriptions/description-{rev_id}.json`，按 revision_id 寻址，跨 snapshot 复用。

### 7.3 组件化输出

主编定义"书长什么样"：Tips 框、例题格式、侧边栏、重点标记。`ComponentSpec` 在 `BookPlan.components` 中。`agent/quality.py::enforce_component_contract` 在写盘前把未知组件归并、`steps` 数组展开。

### 7.4 时间戳链接

Web 版保留时间链接字段，但尚未真正接入智云播放器跳转。`time_links` 在 PDF 输出尚未实现。

### 7.5 并行章节生成

`MultiResourceCourseBookPipeline.run` 按 7 阶段执行：
- description 与主 Agent 规划串行（依赖链）；
- chapter generation 用 `asyncio.Semaphore` 限流并发（默认 2，可在请求中覆盖）；
- chapter 之间的"承上"依赖上一章 `chapter-draft`（在前一章完成后传给下一章），不依赖上一章 LLM 输出中的语义。
- `chapter_indices` 参数可在产品工作台运行时由用户选择子集。

### 7.6 质量门禁

`agent/quality.py` 提供：
- `enforce_component_contract` / `sanitize_examples`（每章写盘前默认应用）
- `deterministic_quality_gate`（确定性检查）
- `llm_quality_gate`（LLM 审校，可选）
- `fact_verification_gate`（事实抽检，对字幕中可验证的事实做样本核对，源自 main 的合并 commit 73258cf）

### 7.7 多 provider 数据源

`product/` 不内嵌具体数据源实现，按 `provider` 字段区分。智云课堂与学在浙大各自有独立适配器和独立会话，互不干扰。智云学在 webvpn 路径已留好入口（详见 `docs/ISSUES.md` B12）。

### 7.8 资料集与输入快照

- **资料集是长期容器**，可包含字幕、PPT、PDF、DOCX、Markdown、TXT。生成结果与资料集绑定，不再与单一课程 ID 绑定。
- **输入快照是某次运行所引用的资源版本集合**，按 SHA-256 锁定，避免"资料被改但运行引用了旧版本"的隐性 bug。
- 同一资料集多次运行产生不同 `job_id`，从而不同 `ArtifactSummary`，互不覆盖。前端在 DatasetDetailPage 列出"第 N 次生成"，可点击进入运行或删除。

### 7.9 章节缓存与串台修复

v2 之前 `chapter-{cid}.json` 用 chapter_id 做后缀，但 `c1`/`c2` 跨 snapshot 会冲突——曾出现 84213 的章节被 65564 的 c1 内容污染（详见 `docs/ISSUES.md` 与 commit `77c825d`）。v2 改为 `chapter-{snapshot_id}-{chapter_id}.json`，按 snapshot 分桶；`course_id` 单独存在时降级到 `chapter-{course_id}-{chapter_id}.json`。

### 7.10 与产品工作台的当前对接

`MultiResourceCourseBookPipeline.run(snapshot_id, course_id?, dataset_name?, ...)` 直接读 snapshot 资料 → 解析 → description → 主 Agent 规划 → Tag → 按 Tag 装上下文 → 章节生成 → 合成 → 渲染。`product/` 通过 `/api/generate/v2` 端点触发，不再需要中间薄适配。`/api/product/datasets/{id}/runs` 列出该资料集的所有生成记录；`DELETE /api/product/runs/{id}` 清理运行（含 in-flight task 取消与缓存清除）。