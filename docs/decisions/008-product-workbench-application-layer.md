# ADR 008：产品工作台应用层

## 状态

已接受，2026-09-06。

## 背景

现有系统以 `course_id -> JobState -> CourseBook` 为主线，能够完成智云课程字幕到教辅书的生成，但无法表达以下已确认的产品能力：

- 一个资料集长期保存智云课程、字幕、PPT、PDF、DOCX、Markdown 和文本资料。
- 每次运行从资料集中选择不同材料，并冻结可复现的输入快照。
- 工作流预设可以扩展，但首个预设仍是“课程教辅书”。
- 同一资料集可以产生多次运行和多个独立产物。
- 前端需要观察阶段、章节 Agent、失败、重试和中间结果。

团队现有分工将生成稳定性和输出质量作为独立工作线。产品工作台不能重写 `agent/`、质量门禁或章节生成算法。

## 决策

新增独立 `coursebook_agent/product/` 应用层，并通过 `/api/product/*` 暴露接口。应用层负责：

1. `Dataset`：资料集元数据。
2. `Resource` 与 `ResourceRevision`：逻辑资料、原文件版本和解析结果。
3. `InputSnapshot`：运行实际使用的资料版本，不可变。
4. `WorkflowPreset`：可选择的工作流定义；首版内置课程教辅书。
5. `RunProjection`：把现有 Job 与章节进度投影成前端可观察结构。
6. `ArtifactRecord`：按运行记录独立产物身份，不改变现有 CourseBook 内容模型。

元数据使用 Python 标准库 SQLite，原文件按 SHA-256 存储在 `data/product/blobs/`。解析文本作为资源版本的一部分保存。PPTX、PDF、DOCX 使用成熟解析库；Markdown 和 TXT 直接解析。

运行创建时必须保存所选 `resource_revision_ids` 和配置。后续资料集更新不得改变历史快照。应用层通过薄适配调用现有 pipeline；不在本 ADR 中改变生成算法、质量规则、模型重试或检查点恢复语义。

## API 演进

- 现有 `/api/courses`、`/api/jobs`、`/api/books`、`/api/runs` 保留，保证队友分支和旧前端兼容。
- 新前端优先使用 `/api/product/*`。
- 运行适配初期允许内部复用现有 Job ID，但对外使用结构化字段，不解析中文 `message` 推断状态。
- 后续若需要 SSE，可在不改变 Run/Projection 数据结构的前提下增加事件流端点。

## 边界

产品工作台工作线可以修改：

- `coursebook_agent/product/`
- 新产品 API 路由及其挂载
- 文件解析依赖
- 前端页面、类型和 API client
- 产品 API 测试及相关文档

除非经过共同确认，不修改：

- `coursebook_agent/agent/` 中的 prompt 与生成策略
- 质量门禁规则
- pipeline 的章节生成与合成算法
- 现有任务恢复和模型重试语义

## 后果

优点：产品能力不再受单课程模型限制；上传和快照是真实能力；新旧前端可以渐进迁移；与队友的生成核心冲突较少。

成本：需要维护 SQLite schema、文件生命周期和解析失败状态；解析后的非字幕材料接入生成上下文仍需要后续与生成工作线共同确认适配契约。
