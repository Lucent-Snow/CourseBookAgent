# ADR 009: v2 多资料工作流

## 状态

已接受，2026-09-08；通过 PR merge 到 `main`。

## 背景

v1 模型假设"输入是智云课堂字幕"——课程有几讲就生成几章，章节是讲次的同义词，1 章 = 1 讲。用户资料集已支持上传 PPT/PDF/DOCX/MD/TXT，但 v1 pipeline 实际上不消费这些资料，只消费智云字幕 digest。

用户观察到的具体问题：
1. 16 份 transcript → 16 章，每章绑定一份讲次标题 —— 不是一本书。
2. 章节顺序按智云 API `newest first` 排序，与讲次时间顺序不一致。
3. 上传文件、智云课件页、学在浙大课件**未进入生成 prompt**——产品层通了，生成链路没接。

## 决策

按 `docs/IMPLEMENTATION_PLAN.md` 的 9 阶段落地，固定 7 阶段流水线：

```
snapshot -> parse -> describe -> main-Agent plan + Tag
          -> assemble per-chapter contexts (by Tag)
          -> parallel chapter generation (one Agent per chapter)
          -> synthesise -> render
```

关键契约：

1. **章节是书籍主题，不是讲次时间**。`heuristic_book_plan_v2` fallback 按 `knowledge_topics` 关键词贪心合并；`plan_book_v2` 的 prompt 显式说"按主题合并"。
2. **Tag 是上下文归属，不是流程控制**。`BookPlan.resource_tags: dict[revision_id, list[str]]`，value 是 chapter_id 列表或 `"__global__"`。未列入 = 本次不参与生成。
3. **章节 ID 是阅读顺序**。`chapter_id` (`c1 / c2 / …`) 按主 Agent 决定的阅读顺序编号；同一份资料可同时进多个章节。
4. **产品绑定到资料集**。生成结果 = `CourseBook` + 资料集元数据。`course_id` 是可选 metadata。
5. **不变量**：流程阶段固定，主 Agent 不重新发明流程；Tag 只在装配阶段起作用。

## 数据契约

新增类型（`coursebook_agent/models.py`）：

- `ParsedResource` / `ParsedResourceUnit` / `ResourceLocation`
- `ResourceDescription`（含 `knowledge_topics / scope / suggested_role`）
- `ChapterContext`（chapter + global + chapter resources + 写作 prompt）
- `BookPlan` 新增 `chapter_resources / resource_tags / global_resource_ids / snapshot_id`
- `LectureDraft` / `CourseBook` 新增 `chapter_id / used_resource_ids / snapshot_id`

`chapter-{cid}.json` 改为 `chapter-{snapshot_id}-{chapter_id}.json`，按 snapshot 分桶（修了串台 bug）。

## 失败模式与防御

- LLM 网络不稳：`LLMClient` 重试 + JSON 修复 + brace-balanced 候选解析。
- LLM 输出空 / 没章节：fallback `heuristic_book_plan_v2` 按主题合并，**plan.warnings 永远含"启发式"**，前端可标注。
- 章节 LLM 返回空 sections：fallback 基于 `ParsedResourceUnit` 生成确定性格式章节。
- chapter cache 跨课程串台：用 snapshot_id 分桶（见上）。
- CAS 触发 SMS 二次验证：详见 `docs/ISSUES.md` B11/B12，今天不可控；保留 session 文件复用路径。

## 后果

- 优点：端到端跑通 course_id 75061 → 17 章节（84213 → 9 章节，混合资料）；前端可显示每份资料的 description + Tag；用户可按资料集管理生成历史。
- 成本：v2 pipeline 每章节都调用 LLM，长课程耗时；fallback 仍按主题合并，**不用课程 ID 排序**。
- 不做：聊天机器人、个性化掌握度、自训模型、全校平台；不把 Tag 做成行为决策树；不为 LLM 失败设计人工兜底流程（用户已明示"完全相信主 Agent"）。

## ADR 备选

- A. 保留 v1 模型，只让产品层"显示"上传文件 —— 被否决：上传资料从未进入生成 prompt，违反"输入要尊重资料集"原则。
- B. 主 Agent 二次规划（先生成讲次摘要，再合并）—— 被否决：与"按讲次分章"的失败模式同源，且浪费一次 LLM 调用。
- C. **采用**：v2 单一链路，主 Agent 一次性看所有 description，输出 chapter_id + Tag。
