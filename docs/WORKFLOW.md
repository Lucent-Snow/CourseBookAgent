# CourseBookAgent 生成工作流

## 1. 已确认的目标

CourseBookAgent 的目标是把一门课程的全部相关资料整理成一本教辅书。输入不再假设只有字幕，也不再假设“一节课对应一章”。资料可以来自智云课堂、学在浙大或用户上传，包括字幕、课件、PPTX、PDF、DOCX、Markdown 和 TXT。

工作流的阶段顺序是固定的。主 Agent 不负责发明工作流，也不输出行为决策树；它负责在固定工作流中的全局理解和内容编排。

主 Agent 的职责：

1. 查看本次所有资料的 description。
2. 理解课程整体内容、资料覆盖范围和资料之间的关系。
3. 确定整本书的章节、章节顺序、每章范围和章节写作要求。
4. 确定整本书的整体风格、读者定位和写作要求。
5. 给资料打 Tag，决定资料进入哪些子 Agent 的上下文。

Tag 的职责：

- Tag 是资料的上下文归属分类，不是流程控制器。
- 章节 Tag 表示资料进入对应章节 Agent。
- 全局 Tag 表示资料作为全书范围资料进入需要它的 Agent，例如教学大纲。
- 无 Tag 表示资料保留在资料库中，但不参与本次书籍生成。
- 一份资料可以有多个章节 Tag，也可以同时有全局 Tag 和章节 Tag。

## 2. 固定总流程

```text
选择资料集中的资源版本
    ↓
创建输入快照
    ↓
解析每份资料
    ↓
为每份资料生成 description
    ↓
主 Agent 查看全部 description
    ↓
主 Agent 确定章节、全书风格、章节写作要求和资料 Tag
    ↓
系统按 Tag 组装每个章节的上下文
    ↓
每个章节由一个章节 Agent 生成
    ↓
章节质量检查
    ↓
全书合成
    ↓
全书质量检查
    ↓
渲染 Web / Markdown 输出
```

这是固定的阶段流程。不同课程的变化发生在章节数量、章节范围、资料 Tag 和上下文内容，不发生在工作流阶段本身。

## 3. 阶段一：输入快照

产品工作台从资料集中选择本次使用的资源版本，创建不可变的输入快照。后续所有解析、description、规划和生成都只能读取快照中的资料版本。

输入：资料集中的资源版本。

输出：输入快照，包含：

- snapshot_id
- resource_revision_ids
- 资料版本的内容摘要
- 创建时间

快照是本次运行的资料边界。未进入快照的资料不参与本次运行。

## 4. 阶段二：解析资料

系统按资料类型逐份解析，不把所有原始资料直接拼成一份文本。

| 资料类型 | 解析结果 |
|---|---|
| 字幕 | 讲次、段落、时间范围、可引用文本 |
| 智云课件 | 课件页、页序、标题、页内容或页来源信息 |
| PPTX | 幻灯片顺序、文本、备注、页码 |
| PDF | 页面顺序、页面文本、页码 |
| DOCX | 标题、段落、表格和文档顺序 |
| Markdown | 标题层级和正文 |
| TXT | 原始文本和稳定的段落顺序 |
| 教学大纲 | 课程目标、教学范围、章节安排、考核要求等可识别内容 |

每份资料的解析结果必须保留与原始资料的对应关系，以便后续 Tag 和章节 Agent 使用来源信息。

输入：快照中的一个资料版本。

输出：结构化解析资料，至少包含资料版本身份、资料类型、文本内容、结构单元和来源定位。

## 5. 阶段三：生成资料 description

Description Agent 逐份阅读解析结果，生成一份给主 Agent 使用的资料说明。Description 不是最终章节摘要，也不是 Tag；它是主 Agent 了解全部资料的全局索引。

Description 至少说明：

- 资料是什么、来自哪里、属于什么类型。
- 资料覆盖哪些主题和知识点。
- 资料对应整门课、若干课次、某个主题还是局部内容。
- 资料中有哪些适合写入教辅的内容，例如定义、推导、例子、步骤、习题、教学要求。
- 资料更适合作为正文依据、全局约束还是局部补充。
- 资料的内容范围与其他资料可能存在怎样的重复或互补关系。

输入：一份结构化解析资料。

输出：与资料版本绑定的 description，供主 Agent 汇总查看。

注意：字幕压缩不是本阶段的固定替代品。字幕可以根据需要生成知识点地图或其他整理结果，但目标工作流首先要求所有资料都有 description，让主 Agent 能看到全局资料集合。

## 6. 阶段四：主 Agent 全局规划

主 Agent 一次性接收本次快照中全部资料的 description，以及课程基本信息。它不需要逐份接收全部原始长文本；它通过 description 先建立全局认识，再生成书籍规划。

主 Agent 输出四类结果：

### 6.1 全书信息

- 书名
- 目标读者
- 教辅书定位
- 学习路径
- 全局写作风格
- 全局术语和表达要求
- 全书组件规范

### 6.2 章节定义

每个章节必须是书籍章节，不是课程讲次的别名。每个章节包含：

- 稳定的 chapter_id
- 章节序号和标题
- 所属模块
- 章节在全书中的作用
- 学习目标
- 必须覆盖的内容
- 应压缩或弱化的内容
- 小节结构
- 章节深度和写作要求
- 与前后章节的衔接要求

主 Agent 可以把多节课合并成一章。例如第 1、2 节课共同讲完“函数极限”，就只生成一个章节 Agent，并把两节课相关资料一起放入该章节上下文。

### 6.3 资料 Tag

主 Agent 为资料建立上下文归属：

- chapter tag：资料进入一个或多个指定章节 Agent。
- global tag：资料进入全局上下文，供所有需要全局信息的 Agent 使用。
- no tag：资料本次不进入生成上下文。

Tag 需要能表达资料与章节的关系，而不是只能给资料设置一个单值类别。主 Agent 认为教学大纲只作为全书约束时，就给它 global tag；主 Agent 认为某个 PPT 只服务于某一章时，就给它对应的 chapter tag；主 Agent 认为资料没有必要参与本次生成时，就不设置 Tag。

### 6.4 章节资料映射

系统从 Tag 得到每个章节的资料集合。这个映射不是独立由规则猜出来的，而是主 Agent 规划结果的执行形式。

输入：课程信息 + 全部资料 description。

输出：BookPlan，包括全书信息、章节定义、全局写作要求、资料 Tag 和章节资料映射。

## 7. 阶段五：按 Tag 组装章节上下文

系统根据 BookPlan 为每个章节建立上下文，不再按课程讲次机械地建立章节。

一个章节 Agent 的上下文包含：

1. 全局写作风格和全书约束。
2. 该章节的 ChapterInstruction。
3. 所有带该章节 Tag 的资料。
4. 所有带 global tag 的资料。
5. 资料的解析内容和来源定位。
6. 需要时的字幕整理结果、原始字幕片段、课件页或讲义片段。

例如两节字幕共同组成第 2 章，则第 2 章 Agent 同时获得这两节字幕及其相关 PPT、讲义；它不是分别生成两个章节后再拼接。

无 Tag 资料不进入章节 Agent。章节 Agent 不自行决定资料范围，系统严格按照主 Agent 的 Tag 组装上下文。

## 8. 阶段六：章节生成

每个主 Agent 定义出的章节对应一个章节 Agent。章节 Agent 的任务是把该章节上下文中的多种资料组织成一章可独立阅读的教辅内容。

输入：

- 全局写作提示词。
- 本章 ChapterInstruction。
- 本章 Tag 资料。
- global tag 资料。
- 解析后的字幕、课件和文档内容。
- 需要时的来源定位信息。

输出：

- 一个章节草稿。
- 章节标题、概览、学习目标、正文小节、例题、易错点和小结。
- 每个重要内容对应的资料来源引用。
- 可供 Web / Markdown 渲染的组件数据。

章节 Agent 不做全书章节规划，不重新给资料打 Tag，也不把一节课自动当作一章。

不同章节可以并行生成，因为每个章节的上下文已经由 Tag 独立组装完成。

## 9. 阶段七：章节质量检查

章节生成后执行固定的章节质量检查，确认输出符合主 Agent 的章节要求：

- 章节覆盖规定内容。
- 章节结构完整。
- 多节课内容已按章节主题组织，而不是简单拼接。
- 使用了正确的章节资料和全局资料。
- 内容具有来源对应关系。
- 组件、公式、例子、易错点和小结格式正确。
- 与全书风格一致。

检查通过后进入全书合成。检查不通过时，使用检查结果重新生成该章节。

## 10. 阶段八：全书合成

全书合成 Agent 接收 BookPlan 和所有章节草稿，负责形成完整书稿：

- 按主 Agent 确定的章节顺序排列章节。
- 统一全书标题、术语、组件和表达。
- 生成前言、使用说明、知识地图、学习路径、术语表和要点索引。
- 修补章节之间的衔接。
- 检查重复和全书层面的不一致。

全书合成不改变主 Agent 的章节划分和资料 Tag。

## 11. 阶段九：全书检查与渲染

对合成书稿做全书级检查，然后渲染为 Web 和 Markdown。最终运行需要保存本次生成的快照、解析结果、description、BookPlan、Tag、章节草稿和最终 CourseBook，使生成结果可追溯。

## 12. 当前实现与目标的差距

**v2 多资料工作流已落地**（`MultiResourceCourseBookPipeline.run`，详见 §1–§11）。已实现：

- `product/parsers.py` 支持 PPTX、PDF、DOCX、Markdown、TXT 的文本解析。
- `product/service.py` 已保存资料、资料版本、输入快照；`MultiResourceCourseBookPipeline` 通过 `snapshot_id` 读取 `ParsedResource` 列表。
- `agent/describe.py` 走 transcript 启发式、其他 LLM 失败 fallback，缓存到 `data/intermediate/descriptions/`。
- `agent/editor.py::plan_book_v2` 接受 `ResourceDescription[]`，输出 `BookPlan v2`：章节由主题决定、`resource_tags / chapter_resources / global_resource_ids` 显式标记。
- `agent/chapter.py::generate_chapter_v2` 接收 `ChapterContext`（chapter + global + chapter resources + 写作 prompt）。
- `coursebook_agent/assembly/assemble.py` 按 Tag 装 `ChapterContext`。
- `pipeline.py::MultiResourceCourseBookPipeline.run` 按 7 阶段跑：`description → 主 Agent 规划 → Tag 装配 → 章节生成 → 合成 → 渲染`，按 `snapshot_id` 缓存 BookPlan，章节缓存按 `chapter-{snapshot_id}-{chapter_id}.json` 分桶。
- `agent/editor.py::heuristic_book_plan_v2` fallback **按主题关键词贪心合并**，不再 1 章 = 1 资料。
- 前端：DatasetDetailPage 列出"第 N 次生成"，可点击进入 / 删除；RunProjection 暴露 dataset_id/dataset_name 给前端做资料集名主标题；per-resource / stage / quality 透明化。

**已知遗留**（详见 `docs/ISSUES.md`）：

- B10：`get_ppt_timeline` 翻页硬上限已加 20 页。
- B11：智云 / 学在浙大今天触发 CAS `loginView.sendsms.error`，SMS 二次验证是 ZJU 服务端策略，不在我们可控范围；端到端必须由浏览器手动登录一次保存 session cookie。
- B12：webvpn 路径已留好入口（`via_webvpn=True`），但 webvpn 自己也要求登录，session cookie 复用是当下唯一可行路径。
- 旧的 `generate_course()`（4 层流水线）和 `pipeline.compress_lecture` 仍保留向后兼容，但不再被新代码调用；保留用于 `tests/test_core.py` 等。

## 13. 不属于本次目标的内容

本次不改变以下前提：

- 工作流阶段保持固定。
- 完全相信主 Agent 的章节规划和 Tag 结果。
- 不设计主 Agent 出错后的人工兜底流程。
- 不把 Tag 设计成行为决策树。
- 不把主 Agent 变成流程编排器。
- 不要求先对所有字幕按讲次压缩后才能规划全书。
- 不新增聊天机器人、个性化学习画像或全校平台能力。
