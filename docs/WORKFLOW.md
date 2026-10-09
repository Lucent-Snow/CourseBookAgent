# CourseBookAgent 生成工作流

> 2026-10-09 实现现状。阶段设计与判读标准见 `DECOMPOSITION.md`；真实产物、验证和剩余任务见 `CURRENT_STATUS.md`。不要把目标检查机制当作已实现。

## 1. 固定流程

```text
上传/导入 → 资料版本 → 输入快照
                       ↓
1. 解析/加载资料 → 2. 五栏目 description → 3. 全书规划与 Tag
                       ↓
4. 按 Tag 装配 → 5. 分章生成与章节检查 → 6. 全书合成 → 7. 渲染
```

资料入库时先抽取文本，运行时 `snapshot_loader.py` 将快照中的版本加载成 ParsedResource。七个运行阶段不包含快照创建；不是七个 LLM 调用。主 Agent 规划内容，不重新发明工作流。

HTTP 入口：`POST /api/generate`，必须有 `snapshot_id`；字段为 `course_id? / regenerate / review / concurrency / chapter_indices?`。Python 唯一入口：`CourseBookPipeline.run()`，还允许直接从 course_id 读取智云资料。不要混淆 Python 和 HTTP 契约。

## 2. 阶段与契约

| 阶段 | 输入 → 输出 | 实现与边界 |
|---|---|---|
| 解析 | 资料版本 → ParsedResource/units/location | 字幕、PPTX、PDF、DOCX、MD、TXT 文本与来源定位；不调 LLM，不包含完整视觉理解/OCR |
| description | 每份 ParsedResource → ResourceDescription | 所有载体走 LLM，包括字幕；body 为五栏目 Markdown，附结构化 topic/scope 等，失败才启发式降级 |
| 全书规划 | 全部 description + 课程信息 → BookPlan | 主 Agent 输出书名、风格、主题章节、写作要求、Tag、组件规范；错误时有 JSON 修复和主题启发式降级 |
| 装配 | BookPlan + ParsedResource[] → ChapterContext[] | 纯确定性函数，根据 Tag 分配原资料；不调 LLM |
| 章节 | ChapterContext → LectureDraft | 一章一个 Agent，写导读/正文/例题/步骤/小结/备注；组件约束、例子清理及可选审校在此执行 |
| 合成 | BookPlan + 章节草稿 → CourseBook | 顺序、前言、学习路径、知识地图、术语/要点索引与前后衔接；不重写所有章节正文 |
| 渲染 | CourseBook → Markdown | `render_coursebook()` 确定性排版；产品网页读取 CourseBook，PDF 尚未接入 |

Description 五栏目：形态与性质、内容板块、独特价值、术语/关键词与可用性、章节归属建议。最后一栏是建议，最终分配由主 Agent 决定。修复了 transcript 用日期/水词生成无效说明的旧捷径。

## 3. Tag 与章节

`BookPlan.resource_tags` 以 revision_id 为键，值为章 ID 列表或 `__global__`。一份资料可进入多个章节；global 进入各章；无 Tag 本次不参与。Tag 是上下文归属，不是流程控制。

章节按知识主题组织，而非讲次 1:1：多次课可合成一章，一次课可服务多章。ChapterContext 包含写作要求、章指令、章资料、全局资料及来源。资料 Tag 仍有漏分的已知案例（B15），不假设主 Agent 永不出错。

流水线会校验每章是否有有效的章节或全局资料（缓存规划同样校验）。缺失 Tag 时先恢复模型明确给出的 `section_plan.source_revision_ids`；仍有空章则独立修复一次 Tag，保持章节结构。修复后仍无资料就阻断，不把讲次位置硬映射为章节。详见 ADR 010；该校验不保证主题归属或覆盖质量。

## 4. 并发与上下文

- description 的并发上限为 4，完成后才能规划。
- 章节按请求 concurrency 限流，默认 3（范围 1–8）；实验台也可逐章运行。
- `chapter_indices` 是规划顺序的 1-based 子集，不是 lecture_indices。
- 运行核心在生成时尝试读取上一章已有缓存作为衔接输入；并发时不保证上一章先完成，不是严格顺序依赖。实验中逐章串行可以提供前章摘要。
- 本轮真实成品来自逐阶段/逐章实验台，不把它说成网页整课并发与恢复已经重新验收。

## 5. 章节质量与异常

已有组件契约、例子清理、确定性检查、可选 LLM 审校与警告记录。提示词强调全量覆盖、原始课堂价值、待核标记和“据口述重写”的示意代码。审校输入截断从 8000 扩到 40000 字符，仍不是无限输入。

当前 `generate_chapter_from_context_with_fallback` 异常时仍可能产出降级正文并落盘；空章节异常也会保存失败草稿。章节 Agent 接收全部资料单元，不截取前 24 段。流水线复用章节缓存须有正文、资料 ID 与当前上下文一致、context_fingerprint 匹配，且警告中没有确定性回退标记；旧缓存没有指纹，须重算。确定性回退或空正文在流水线进度与缓存投影中计为失败，整书状态为部分完成，可保留有效缓存重试。语义有效性与完整失效传播仍待处理；恢复入口不等于精准续跑已全面验收，见 B14 与 CURRENT_STATUS。

自动按审校意见回炉、全书独立 LLM 审稿与事实正确性认证没有完整闭环。合成时的 quality_notes 是模型整理备注，不是独立审核证明。

## 6. 保存与重跑

- description：`data/intermediate/descriptions/description-{revision_id}.json`，跨快照复用。
- 规划：`data/plans/bookplan-{snapshot_id}.json`。
- 章节：`data/intermediate/chapter-{snapshot_id}-{chapter_id}.json`。
- 成书/Markdown：按 course_id（若存在）或 snapshot_id 命名，见 ARCHITECTURE；并非每个 Job 独立文件。
- Job：`data/jobs/{job_id}.json`，包含状态、请求、事件及完整 CourseBook。

HTTP retry 使用同一 Job 与原请求重新调 pipeline；默认可能复用 description、规划与章节缓存。`regenerate=True` 会重算规划与章节，不自动清 description 缓存，不能当精准续跑开关。

重启把 running 标成 interrupted，停止保留记录；重试可从 failed/partial/interrupted 发起。实际恢复与版本下载一致性是比赛前验收项。

## 7. 实验台

`LabService` / `scripts/lab.py` 将 describe、plan、assemble、generate、synthesize 独立开放，带阶段缓存和 `--force`。它复用核心阶段函数，不形成第二套写作算法。

```bash
uv run python scripts/lab.py status --snapshot <snapshot_id>
uv run python scripts/lab.py describe --snapshot <snapshot_id>
uv run python scripts/lab.py plan --snapshot <snapshot_id>
uv run python scripts/lab.py assemble --snapshot <snapshot_id>
uv run python scripts/lab.py generate --snapshot <snapshot_id> --chapter c1
uv run python scripts/lab.py synthesize --snapshot <snapshot_id>
uv run python scripts/lab.py show chapter --snapshot <snapshot_id> --chapter c1
```

逐阶段展示产物、判断后推进；不能一口气重跑全书。实验不进普通用户前端。Lab 合成写 CourseBook 缓存，但不自动注册 Job 或输出 Markdown；显式调用 renderer 才能导出，现有示例已执行该步。

接口 `/api/product/snapshots/{id}/lab/*`，清缓存与查看方法见 `AGENTS.md` / `API.md`。改变上游资料、description 或规划后，下游缓存需人工按依赖判断失效，当前没有完整自动失效传播。

## 8. LLM 运行约束

LLMClient 使用 OpenAI 兼容流式响应，`stream_options.include_usage=True`；不传 max_tokens。默认超时 600 秒，description/审校 300 秒，规划/写作/合成常用 900 秒；网页整任务上限 5400 秒。请求重试/JSON 修复已有，但不代替成功产物校验。

当前示范实验模型为本机配置的 `mimo-v2.6-flash`，不是仓库写死的服务。队友需自行配置端点/模型/密钥，不复制私人凭据。
