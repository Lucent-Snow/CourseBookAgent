# CourseBookAgent Workflow 设计

## 总流程

```text
course_id
  → fetch_transcripts          # 获取原始字幕
  → clean_and_chunk            # 清洗 + 分块
  → compress_lectures          # 每讲压缩为知识点地图
  → plan_book                  # 主编统筹全书
  → generate_chapters          # 带上下文的分章撰写
  → synthesize_book            # 全书合成
  → render_outputs             # 渲染为 Markdown / Web / PDF
```

---

## 字幕压缩

**输入**：一讲的 TimedChunk[]（完整字幕）
**输出**：LectureDigest（知识点地图）

主编是聪明人，知道假设检验是什么。压缩器只需要回答：

> "这堂课老师怎么讲的？先讲了什么、后讲了什么？有哪些知识点？关键例子在哪？ASR 质量怎么样？"

压缩原则：
- 知识点宁多勿少，描述要密度高
- 记录老师流向（A→B→C），不是知识点罗列
- 每个知识点标 chunk_ref 和 time_ref
- ASR 问题单独记录
- 不写散文，写清单

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

主编为每章写一份独立的 ChapterInstruction：
- 覆盖什么、压缩什么
- 用哪个组件、怎么用
- 深度指导（"这章需要逐步计算" vs "概述即可"）

主编还写一份共享的 writer_system_prompt，约束所有写作者的风格和禁忌。

产物：`data/plans/bookplan-{course_id}.json`

---

## 分章撰写

**输入**：
- writer_system_prompt（主编写的共享 prompt）
- ChapterInstruction（主编写的该章指令）
- TimedChunk[]（该讲完整字幕）

**输出**：LectureDraft

写作者拿到的是三样东西的拼接：
```
[系统 prompt] + [主编对这一章的具体要求] + [完整字幕材料]
```

写作者产出的每一段都要：
- 有 source_chunk_ids（引用了哪些字幕块）
- 有时间链接（Web 版可点击跳转）
- 按主编规定的组件格式展示例题/Tips/警告
- 只用字幕里的内容，不编造

产物：`data/intermediate/chapter-{lecture_id}.json`

---

## 全书合成（终审）

**输入**：14 章 LectureDraft + BookPlan
**输出**：CourseBook

终审做的事：
- 写前言（基于 book_positioning）
- 生成知识地图（基于 modules）
- 统一术语（基于 canonical_glossary）
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
| PDF | 省略链接 | 静态排版 | 打印/提交 |

---

## 缓存与断点续跑

每层产物独立缓存。命令行支持：
- `--plan-only`：只跑全书规划
- `--lecture N --regenerate`：只重跑某一章
- `--only 2,3,4`：只重跑指定章节
- `--force`：忽略缓存，强制重跑
- 通宵脚本：`scripts/overnight_book_quality.py`

---

## 当前状态

生成工作流已完整实现并集成到 `pipeline.py`。

| 层 | 状态 | 验证方式 |
|---|---|---|
| 字幕压缩 | 已实现，接入 pipeline | 单讲压缩 e2e 通过 |
| 全书规划 | 已实现（含启发式回退） | 蓝图生成通过 |
| 分章撰写 | 已实现 | 单章生成 + 组件渲染 e2e 通过 |
| 全书合成 | 已实现（LLM + 确定性回退） | 全书合成通过 |
| 渲染 | Markdown 完整，Web 组件化已实现 | 组件渲染测试通过 |

测试：`uv run python -m unittest discover -s tests -v`（当前 14 个用例全通过）
