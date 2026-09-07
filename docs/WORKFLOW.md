# CourseBookAgent Workflow 设计

## 总流程

```text
资料集（长期容器，可包含智云 / 学在浙大 / 上传）
    → 选取资源版本
    → 输入快照（SHA-256 锁定）
    → 提交运行（coursebook preset）
        ├─ fetch_transcripts     # 按 provider 拉取原始字幕 / 课件
        ├─ clean_and_chunk       # 清洗 + 分块
        ├─ compress_lectures     # 每讲压缩为知识点地图
        ├─ plan_book             # 主编统筹全书
        ├─ generate_chapters     # 分章撰写（并发，信号量限流）
        ├─ quality_gate          # 质量门禁（组件契约 / 例子清理）
        ├─ synthesize_book       # 全书合成
        └─ render_outputs        # 渲染为 Web / Markdown
    → ArtifactSummary（按 job_id 区分）
```

---

## 资料工作台触发的运行

产品工作台通过 `/api/product/datasets/{id}/configure` 让用户选择本次生成所用的资料版本和讲次，再用 `/api/product/datasets/{id}/snapshots` 创建 SHA-256 锁定的快照，最后提交 `/api/generate` 触发实际运行。

`/api/generate` 的请求体扩展（向后兼容）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `course_id` | str | 必填，保留旧行为 |
| `snapshot_id` | str \| null | 输入快照 ID；产品工作台运行时会携带 |
| `preset_id` | str | 工作流预设，默认 `coursebook`，可扩展多 profile |
| `lecture_indices` | int[] \| null | 只生成指定讲次；透传给 `pipeline.generate_course(only_indices=...)` |
| `concurrency` | int | 章节 Agent 并发数，1–8；透传给 `asyncio.Semaphore` |
| `refresh_source` | bool | 刷新智云课程/讲次缓存 |
| `regenerate` | bool | 强制重新生成（忽略缓存） |
| `review` | bool | 是否进入 LLM 审校循环 |

当 `snapshot_id` 与 `lecture_indices` 同时存在时，运行按快照内容引用资源版本，按指定讲次工作。生成核心不感知资料集，所有上下文通过 `pipeline.generate_course(...)` 的现有参数透传。

---

## 字幕压缩

**输入**：一讲的 TimedChunk[]（完整字幕）

**输出**：LectureDigest（知识点地图）

主编是聪明人，知道假设检验是什么。压缩器只需要回答：

> "这堂课老师怎么讲的？先讲了什么、后讲了什么？有哪些知识点？关键例子在哪？ASR 质量怎么样？"

压缩原则：

- 知识点宁多勿少，描述要密度高。
- 记录老师流向（A→B→C），不是知识点罗列。
- 每个知识点标 `chunk_ref` 和 `time_ref`。
- ASR 问题单独记录。
- 不写散文，写清单。

产物：`data/intermediate/digest-{lecture_id}.json`

---

## 全书规划（主编统筹）

**输入**：14 份 LectureDigest

**输出**：BookPlan

主编做三件事：

### 2a. 定结构

- 按主线分模块（假设检验主线、方差分析主线、回归主线、专题）
- 每章定角色（core / guest / review / mixed）
- 写承上启下
- 定学习路径

### 2b. 定组件规范

主编定义书里有哪些可复用组件：

```json
{
  "name": "worked_example",
  "description": "课堂例题的标准化展示：题干 → 解题步骤 → 结论",
  "fields": ["title", "problem", "steps", "conclusion", "source_ref"],
  "usage_instruction": "每章至少 1 个例题；步骤必须来自字幕，不编造数字",
  "example": "【例题】某校 40 名学生平均分 52.5..."
}
```

其他组件：`tip_box`（小贴士）、`warning`（易错警告）、`side_note`（旁注）、`procedure`（步骤流程）

### 2c. 写指令

主编为每章写一份独立的 `ChapterInstruction`：

- 覆盖什么、压缩什么。
- 用哪个组件、怎么用。
- 深度指导（"这章需要逐步计算" vs "概述即可"）。

主编还写一份共享的 `writer_system_prompt`，约束所有写作者的风格和禁忌。

产物：`data/plans/bookplan-{course_id}.json`

---

## 分章撰写

**输入**：

- `writer_system_prompt`（主编写的共享 prompt）
- `ChapterInstruction`（主编写的该章指令）
- 完整字幕材料（从资料集/智云/学在浙大/上传混合）

**输出**：LectureDraft

写作者拿到的是三样东西的拼接：

```text
[系统 prompt] + [主编对这一章的具体要求] + [完整材料]
```

写作者产出的每一段都要：

- 有 `source_chunk_ids`（引用了哪些字幕块）
- 有时间链接（Web 版可点击跳转）
- 按主编规定的组件格式展示例题 / Tips / 警告
- 只用材料里的内容，不编造

产物：`data/intermediate/chapter-{lecture_id}.json`

---

## 全书合成（终审）

**输入**：所有 LectureDraft + BookPlan

**输出**：CourseBook

终审做的事：

- 写前言（基于 `book_positioning`）
- 生成知识地图（基于 `modules`）
- 统一术语（基于 `canonical_glossary`）
- 生成要点速记索引
- 检查章际连贯性
- 标注残余问题

终审**不重写章节正文**，只修补书级字段。

产物：`data/intermediate/coursebook-{course_id}.json`

---

## 渲染

同一个 CourseBook，根据目标格式不同渲染：

| 格式 | 时间戳 | 组件 | 用途 |
|---|---|---|---|
| Markdown | 文本引用 | 文本标记 | 通用、可编辑 |
| Web | 可点击链接跳转字幕 | HTML 组件（折叠、侧边栏） | 在线学习 |
| PDF | 尚未实现 | 后置能力 | 打印/提交 |

---

## 工作流预设（profile）扩展点

`coursebook_agent/product/service.py` 的 `workflow_presets()` 当前只返回内置 `coursebook` 一个 preset。`preset_id` 是 Job request 里的字段，未来可扩展：

- `coursebook-by-lecture`（保留默认，按讲次 + 字幕 + 课件）
- `coursebook-by-resource`（按主题片段切分）
- `coursebook-global`（全局大纲驱动）

每个 preset 仍复用生成核心，不重写算法。详细取舍见 ADR 009 草案。

---

## 缓存与断点续跑

每层产物独立缓存。命令行支持：

- `--plan-only`：只跑全书规划
- `--lecture N --regenerate`：只重跑某一章
- `--only 2,3,4`：只重跑指定章节
- `--force`：忽略缓存，强制重跑
- 通宵脚本：`scripts/overnight_book_quality.py`

输入快照不重置这些缓存；快照只控制"这次运行引用哪些资源版本"。

---

## 当前状态

生成工作流已集成到 `pipeline.py`。章节撰写并发执行（`asyncio.Semaphore` 限流），写盘前统一经过组件契约与例子清理；确定性门禁始终执行，LLM 审校只在 `review=True` 时执行。当前 Web `/api/generate` 明确传入 `review=False`，因此默认 Web 生成不会进入 LLM 审校与修订循环；通宵脚本默认开启 review。

| 层 | 状态 | 验证方式 |
|---|---|---|
| 字幕压缩 | 已实现，接入 pipeline | 单讲压缩 e2e 通过 |
| 全书规划 | 已实现（含启发式回退） | 蓝图生成通过 |
| 分章撰写 | 已实现，**并发执行** | 单章生成 + 组件渲染 e2e 通过 |
| 质量门禁 | 已实现（`agent/quality.py`，组件契约 + 例子清理） | 机器残留测试通过 |
| 全书合成 | 已实现（LLM + 确定性回退） | 全书合成通过 |
| 渲染 | Markdown 完整，前端 React 9 页已实现；PDF 未实现 | 组件渲染测试 + 前端构建通过 |
| 资料工作台 | 已实现（资料集 / 快照 / 智云 / 学在浙大 / 上传） | 62 项后端测试中 61 项通过；唯一失败为 `test_warning_render`，与本工作无关 |

测试：`uv run python -m unittest discover -s tests -v`（当前 62 个用例，61 通过）

前端 9 页：资料库 / 资料集详情 / 工作流配置 / 运行中心 / 运行详情 / 产物列表 / 产物阅读 / 系统设置 / 从平台导入对话框，全部连接 `/api/product/*`。