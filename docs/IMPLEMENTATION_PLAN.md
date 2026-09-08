# 新一代多资料课程成书工作流实施计划

## 1. 交付目标

将当前“按讲次处理字幕”的生成核心升级为“按主 Agent 规划出的章节处理多资料”的固定工作流：

```text
快照资料
→ 逐份解析
→ 逐份生成 description
→ 主 Agent 基于全部 description 规划章节、风格和 Tag
→ 按 Tag 组装章节上下文
→ 一个章节一个章节 Agent 生成
→ 章节检查
→ 全书合成
→ 全书检查与渲染
```

完成后必须满足：

1. 智云字幕、智云课件、学在浙大课件、上传 PPTX/PDF/DOCX/MD/TXT 可以在同一次运行中共同参与。
2. 主 Agent 能看到本次快照中每份资料的 description。
3. 主 Agent 可以把多节课规划为一个章节。
4. Tag 决定资料进入哪些章节 Agent 的上下文。
5. global tag 资料进入全局上下文；无 Tag 资料不进入本次生成上下文。
6. 章节 Agent 的数量和章节规划一致，不再默认等于课程讲次数。
7. 现有旧 `/api/generate` 与不使用 snapshot 的旧调用保持兼容，除非实现阶段明确更新其适配路径。

## 2. 执行原则

- 先读 `AGENTS.md`、`docs/PRODUCT_HANDOFF.md`、`docs/ARCHITECTURE.md`、`docs/WORKFLOW.md` 和 ADR 008。
- 本计划是实现计划，不要求新增 ADR；如实现过程中改变持久化结构或公开 API，先在对应文档补充契约，再改代码。
- 每完成一个独立功能点，运行相关测试并提交一个小 commit，commit message 使用英文。
- 不做无关重构，不改变质量门禁规则，不把主 Agent 变成流程编排器。
- 不增加人工审核、主 Agent 失败恢复、上下文超限策略等本次未要求的边界设计。

## 3. 当前代码基线

### 已存在

- `coursebook_agent/product/parsers.py` 已能解析 PDF、DOCX、PPTX、Markdown、TXT。
- `coursebook_agent/product/service.py` 已保存资源、资源版本、解析文本和输入快照。
- 产品层已有 `coursebook` preset、运行投影和产物接口。
- 旧生成核心已有字幕清洗分块、字幕 digest、BookPlan、章节生成、质量检查、全书合成和 Markdown 渲染。

### 必须改造

- `coursebook_agent/models.py` 没有资料 description、Tag、按章节的资料映射和通用资料单元模型。
- `agent/editor.py` 只接收 LectureDigest，并强制章节数等于 digest 数。
- `agent/chapter.py` 只接收单讲字幕 chunks。
- `pipeline.py` 通过 ZhiyunSource 读取课程和字幕，未从 InputSnapshot 读取产品资料。
- `product/service.py` 生成的解析文本未传入 pipeline。
- 章节缓存、全书缓存和运行投影仍以 lecture index / lecture_id 为主。
- 当前工作流文档和产品交接文档的旧描述已更新为目标方向，但代码仍未实现目标方向。

## 4. 实施阶段

### 阶段 0：建立契约和最小样例

目标：在写生成逻辑前固定数据契约，避免后续各模块各自发明字段。

任务：

1. 在 `coursebook_agent/models.py` 增加资料通用模型：资料版本引用、解析单元、资料 description、资料 Tag。
2. 增加稳定的章节模型标识，章节标识不能依赖 lecture_id；保留旧字段兼容旧缓存时要明确兼容方式。
3. 扩展 `BookPlan`，至少能表达：章节列表、每章覆盖的资料 Tag、全局资料 Tag、无 Tag 资料、全局写作提示词。
4. 定义章节 Agent 的统一输入模型：章节规划 + 全局资料 + 章节资料 + 来源定位。
5. 给每个字段写中文含义和最小 JSON 示例，放在 `docs/WORKFLOW.md` 或单独的 API/模型说明中。
6. 准备一个离线样例：两份字幕资料共同组成一章，一份 PPT 属于该章，一份教学大纲为 global，一份无 Tag 资料不进入章节。

完成标准：

- Pydantic 模型可以序列化和反序列化。
- 两节课合并一章的样例可以在模型层表达。
- Tag 不被建模为单值字段或行为路由字段。
- 新增模型测试通过。

### 阶段 1：实现逐份资料 description

目标：让所有资料先有可供主 Agent 查看的 description。

任务：

1. 新增 `coursebook_agent/agent/describe.py`。
2. 为不同资料类型提供统一的 description 输入格式，包含 resource/revision 元数据、解析文本、结构单元和来源定位。
3. 实现 `describe_resource()`，输出绑定 revision_id 的 description。
4. description 至少包含：资料类型、来源、主题、知识点覆盖、关联课次或主题、可用内容类型、适合的使用方式。
5. 对字幕保留讲次和时间范围；对 PPT/PDF/DOCX 保留页码或文档位置。
6. 在 LLM 返回异常时，使用基于解析文本和元数据的简单 description，确保 pipeline 能继续读取资料说明。
7. 增加 description 缓存，缓存键必须包含 revision_id 或内容 hash，不能只用 filename。

完成标准：

- 每个快照资料都能得到一份 description。
- description 可被主 Agent 汇总读取。
- 相同资料版本不会重复生成 description。
- 不同资料类型的来源定位不会丢失。
- 新增单元测试覆盖字幕、PPTX/PDF/DOCX、Markdown/TXT 和缓存。

### 阶段 2：扩展主 Agent 规划

目标：主 Agent 基于全部 description 规划章节、风格和 Tag。

任务：

1. 修改 `agent/editor.py` 的输入，从 `list[LectureDigest]` 扩展为课程信息 + 全部资料 description。
2. 保留已有组件规范、写作提示词和质量要求，但删除“chapters 数量必须与 digests 一致”的约束。
3. 修改 prompt，明确：章节是书籍章节，不是讲次；允许多节课合并为一章；允许 PPT、讲义和字幕共同服务一章。
4. 要求主 Agent 输出：
   - 全书信息和整体风格。
   - 章节列表及稳定 chapter_id。
   - 每章章节范围、学习目标、小节计划和写作指令。
   - 资料 Tag 列表：global、一个或多个 chapter、无 Tag。
   - 每章实际使用的资料 revision_id 列表或 Tag 引用。
5. 修改 `_coerce_plan()`，做字段类型归一化，但不要把章节数量重新强制成资料或讲次数量。
6. 更新启发式回退，使其能按资料 description 生成至少一个章节，并能表达 Tag；回退只是技术兼容，不改变主 Agent 的目标语义。
7. 规划结果保存到与 snapshot 绑定的缓存路径，不能继续只使用 `bookplan-{course_id}.json` 覆盖不同输入快照的规划。

完成标准：

- 离线样例能规划“两节字幕 + 一个 PPT = 一个章节”。
- 教学大纲可以被标记为 global。
- 无 Tag 资料不会出现在任何章节资料映射中。
- 主 Agent 输入包含所有资料 description。
- 主 Agent 输出不再要求一讲一章。
- editor 相关测试覆盖合并章节、全局资料、多章节 Tag 和无 Tag。

### 阶段 3：让产品快照进入生成核心

目标：运行时真正使用产品工作台选中的资料，而不是只使用 ZhiyunSource。

任务：

1. 增加 snapshot context loader，读取 `InputSnapshot.resource_revision_ids` 对应的资源版本、解析文本、元数据和原始来源。
2. 设计生成核心到产品层的最小适配接口：pipeline 接收 `snapshot_id` 或已经加载好的快照资料，不直接依赖前端或 SQLite 表结构。
3. 保留旧调用：没有 snapshot 时仍按旧 course_id 读取智云课程。
4. 对快照资料建立统一课程资料集合：字幕资料转换为带来源定位的 TimedChunk 或通用资料单元；文档资料转换为页/段落单元；智云课件保留页和时间信息。
5. `GenerateRequest` 中已有的 snapshot_id 继续作为入口，并向 pipeline 透传。
6. 在 Job checkpoint 中保存 snapshot_id 和资料清单，恢复时使用原快照，不重新读取当前资料集。
7. 不能让未进入 snapshot 的资料意外进入本次运行。

完成标准：

- 使用产品工作台创建的快照运行时，章节生成实际读取快照中的上传文件和平台课件。
- 资料集后来新增或替换文件不会改变运行输入。
- 旧 course_id-only 流程测试仍通过。
- snapshot loader、来源定位和恢复测试通过。

### 阶段 4：按 Tag 组装章节上下文

目标：把主 Agent 的 Tag 转换为每个章节 Agent 的实际输入。

任务：

1. 在 pipeline 中增加 context assembler，不按 lecture index 创建上下文，而按 `BookPlan.chapters` 创建上下文。
2. 对每章收集：匹配章节 Tag 的资料、所有 global Tag 资料、章节指令和全局写作提示词。
3. 无 Tag 资料不进入任何章节上下文。
4. 支持一份资料进入多个章节；支持一份资料同时有 global 和 chapter 归属。
5. 保留每份资料和每个资料单元的来源定位。
6. 在调用章节 Agent 前持久化章节上下文清单，便于运行投影和后续复现。
7. 将上下文组装逻辑做成可单测的纯函数或小对象，不把 Tag 判断散落在 prompt 字符串中。

完成标准：

- 两节字幕可以进入同一个章节上下文。
- PPT 可以只进入指定章节。
- 教学大纲可以进入所有章节上下文。
- 无 Tag 资料不会进入章节 prompt。
- 组装结果可序列化，并能通过测试精确断言资料集合。

### 阶段 5：改造章节 Agent 和章节产物

目标：一个章节 Agent 生成一个主 Agent 定义出的完整章节。

任务：

1. 修改 `agent/chapter.py`，输入改为统一章节上下文，而不是单个 `Lecture` + 单讲 chunks。
2. Prompt 明确章节 Agent 可以同时使用多节字幕、PPT、PDF、DOCX 等资料，并按资料来源写出完整章节。
3. 保留现有组件规范、来源引用、章节质量指标和渲染字段；扩展来源引用以支持非字幕资料位置。
4. 修改 `LectureDraft` 或新增 `ChapterDraft`，使产物使用 chapter_id、标题和 source references；提供旧字段兼容映射，避免旧 API 立刻破坏。
5. 章节缓存改为 snapshot + chapter_id 维度，避免不同规划或快照互相复用错误章节。
6. 章节生成的质量门禁接收该章节实际使用的所有来源资料，而不是只对单讲 chunks 做 coverage 统计。
7. 修改章节进度投影，让前端显示真实的章节序号和章节标题，而不是把章节强制显示成讲次。

完成标准：

- 合并两节课的章节由一次章节 Agent 调用生成。
- 章节可以引用字幕时间、PPT 页码、PDF 页码、DOCX 段落等来源。
- 章节质量检查不再因为没有单一 lecture chunks 而错误失败。
- 旧单讲生成测试继续通过，或有明确兼容测试。

### 阶段 6：改造 pipeline 固定阶段编排

目标：将完整目标流程接入现有任务、缓存、并发和合成链路。

任务：

1. 在 `generate_course()` 中固定实现：加载快照资料 → 解析/读取 description → 主 Agent 规划 → 按章节组装 → 并发生成章节 → 章节检查 → 全书合成 → 全书检查 → 渲染。
2. description 和规划可以缓存；缓存键必须绑定 snapshot 内容和相关模型/提示词版本。
3. `only_indices` 旧参数需要定义兼容含义：如果新规划按 chapter_id 生成，旧讲次筛选只能转换为受影响章节，不能直接把讲次当章节。
4. `concurrency` 继续限制章节 Agent 并发数。
5. `regenerate` 只使相关 snapshot、规划或章节缓存失效，不要无条件污染其他运行的产物。
6. 合成输入使用主 Agent 规划出的章节顺序，而不是 `lectures` 列表顺序。
7. 进度消息和 checkpoint 记录新增 description、planning、context assembly、chapter generation、synthesis 等固定阶段。
8. 失败时保留已完成的 description、规划、章节和快照上下文，支持按章节继续运行。

完成标准：

- 一次真实运行走完整固定流程。
- 章节数量等于主 Agent 规划的章节数量。
- 章节顺序等于 BookPlan 顺序。
- 多资料确实进入对应章节 Agent。
- 全书合成和 Markdown/Web 输出仍然可用。
- pipeline 相关可靠性测试通过。

### 阶段 7：产品 API、投影和前端展示

目标：让新中间结果在产品工作台可观察，但不让前端重新实现生成逻辑。

任务：

1. 为 description、BookPlan、Tag 和章节资料映射增加运行产物或只读查询接口，优先复用已有 product API 风格。
2. 扩展 `RunProjection` / `AgentProjection`，显示真实章节数量、章节标题、固定阶段和资料使用情况。
3. 产物详情能区分本次运行的 snapshot、规划和最终 CourseBook。
4. 工作流 preset 的步骤描述改成目标固定流程；不增加让用户重新设计流程的配置项。
5. 前端只展示和选择资料、查看规划与运行状态，不自行计算 Tag。
6. 增加 API 和前端类型测试；若改前端，运行 build 与 lint。

完成标准：

- 用户可以查看本次运行使用的资料快照。
- 用户可以看到主 Agent 生成的章节结构和资料归属。
- 运行中心显示按章节而非按讲次的 Agent 状态。
- 产物仍可按 run/job 独立访问。

### 阶段 8：端到端验证和文档收尾

任务：

1. 使用离线固定样例验证：两节字幕合并一章、PPT 归属该章、教学大纲 global、无 Tag 资料被排除。
2. 使用真实或录制的产品工作台快照验证：上传文件和平台课件都进入生成链路。
3. 验证同一资料集创建两个不同快照时，description、Tag、章节和产物互不串用。
4. 验证只重生成受影响章节时，其他章节沿用同一快照和原规划。
5. 跑后端完整测试：`uv run python -m unittest discover -s tests -v`。
6. 跑离线回归：`uv run python scripts/check_offline.py`。
7. 若修改前端，运行：`cd frontend && npm run build && npm run lint`。
8. 更新 `docs/PRODUCT_HANDOFF.md`、`docs/ARCHITECTURE.md`、`docs/WORKFLOW.md` 和必要的 API 文档，使“当前已实现”和“目标缺口”准确分开。
9. 检查 git diff，只提交本次工作流改造相关文件。

完成标准：

- 自动化测试通过，已知遗留测试失败必须单独说明，不得伪装成通过。
- 端到端验证能证明 Tag 真的决定上下文归属。
- 文档、模型、API、运行投影和实现没有互相矛盾的旧“一讲一章”描述。

## 5. 推荐提交拆分

1. `feat: add multi-resource workflow models`
2. `feat: generate resource descriptions`
3. `feat: plan chapters and resource tags from descriptions`
4. `feat: load snapshot resources into generation pipeline`
5. `feat: assemble chapter contexts from resource tags`
6. `feat: generate chapters from multi-resource contexts`
7. `feat: integrate fixed multi-resource pipeline`
8. `feat: expose workflow projections and resource mapping`
9. `test: add multi-resource end-to-end coverage`
10. `docs: document multi-resource generation workflow`

如果某个阶段需要跨越多个独立提交，必须保持每个提交可运行、可测试，不能先提交大量未接通的半成品。

## 6. 最终验收清单

- [ ] 所有快照资料先解析，再生成 description。
- [ ] 主 Agent 输入包含所有资料 description。
- [ ] 主 Agent 能规划与讲次不同数量的章节。
- [ ] 主 Agent 能确定全书风格。
- [ ] Tag 只表达资料上下文归属，不承担流程控制。
- [ ] global tag 资料进入全局上下文。
- [ ] 无 Tag 资料不进入章节上下文。
- [ ] 一份资料可以服务多个章节。
- [ ] 一个章节 Agent 可以同时接收多节课和多种资料。
- [ ] 章节数量、顺序和标题来自 BookPlan。
- [ ] 产品 snapshot 是真实生成输入。
- [ ] 字幕、PPT、PDF、DOCX、MD、TXT 的来源定位被保留。
- [ ] 缓存和 checkpoint 绑定 snapshot 与 chapter_id。
- [ ] 全书合成使用规划章节，而不是课程讲次列表。
- [ ] Web/Markdown 渲染和运行投影继续工作。
- [ ] 后端测试、离线回归和前端检查按修改范围通过。
