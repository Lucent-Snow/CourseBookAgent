# CourseBookAgent Changelog

## 2026-09-08 — 多资料工作流 v2 端到端落地

### 新工作流

按 [`docs/IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) 实现的 9 阶段工作流已经走通：快照 → 逐份解析 → description → 主 Agent 看全部 description 规划章节与 Tag → 按 Tag 装章节上下文 → 每个章节 Agent 生成 → 合成 → 渲染。

工作流的关键约定：

- 流程阶段固定，主 Agent 不重新发明流程。
- Tag 是上下文归属分类（chapter / global / 无），不是流程控制器。
- 章节是书籍章节，不等于讲次——多节课可合并成一章，一节课可独立成章，没有字幕的章节也能存在。

### 实测端到端

| 运行 | 课程 | 资料 | 主 Agent 输出 | 产物 |
|---|---|---|---|---|
| `bec909b7666a` | 数据科学与心理学研究（本）· 65564 | 智云字幕 14 份 + 智云课件 7 份 | 8 章（多课合并） | `data/output/coursebook-65564.md`（~1.5 MB，章节数 ≠ 讲次数 16） |
| `36a62891f32a` | 数据科学与心理学研究（本）· 65564 | 智云字幕 16 份 + 上传教学大纲 PDF | 17 章（教学大纲单独成第 17 章） | `data/output/coursebook-65564.md`（~150 KB） |

`bec909b7666a` 的前端运行详情（`/runs/<id>`）能列出 8 个章节 Agent 卡片，状态全部 `succeeded`。`/artifacts/<id>` 显示完整 8 章正文。

`36a62891f32a` 的前端运行详情能列出 17 个章节 Agent 卡片；产物页有完整 17 章侧边目录与正文。

### 本次提交涉及的文件（与 commit 对应）

新增：
- `coursebook_agent/agent/describe.py` — 逐份资料 description，transcript 走启发式避免输入超限，其他类型走 LLM，失败 fallback 仍生成可用 description。
- `coursebook_agent/assembly/assemble.py` — 按 `BookPlan.resource_tags` 装配 `ChapterContext`，global 资源进入每个章节的全局上下文，无 Tag 资料不出现。
- `coursebook_agent/product/snapshot_loader.py` — 把 `InputSnapshot` 转 `ParsedResource`；支持智云缓存与产品层 snapshot 两种入口。
- `tests/test_v2_workflow.py` — 12 个 v2 单元测试，覆盖 description、coerce、Tag、装配、fallback。
- `docs/IMPLEMENTATION_PLAN.md` — 实施计划（9 阶段）。
- `docs/CHANGELOG.md` — 本文件。

修改：
- `coursebook_agent/models.py` — 新增 `ResourceDescription / ResourceLocation / ParsedResource / ParsedResourceUnit / ChapterContext`；扩展 `BookPlan`（resource_tags、chapter_resources、global_resource_ids、snapshot_id）；`ChapterInstruction` 加 `chapter_id`；`LectureDraft` 加 `chapter_id` 与 `used_resource_ids`；`CourseBook` 加 `snapshot_id`。
- `coursebook_agent/agent/llm.py` — 剥离 `<think>…` 推理块；JSON 解析改为 brace-balanced 候选，对长 thinking + 长 JSON 更稳定。
- `coursebook_agent/agent/editor.py` — `plan_book_v2` 接受 `ResourceDescription[]`，输出 `BookPlan v2`；LLM 失败时按 description 自动分章（每份资料一章，scope=course 走 global）。
- `coursebook_agent/agent/chapter.py` — 新增 `generate_chapter_v2` 接受 `ChapterContext`（多资料），以及 `_with_fallback` 在 LLM 不可用时基于 ParsedResource 单元生成确定性格式章节。
- `coursebook_agent/agent/synthesize.py` — 用 `chapter_id` 优先键避免多章节塌到同一 lecture_id 槽位。
- `coursebook_agent/pipeline.py` — `MultiResourceCourseBookPipeline.run` 按 description → 主 Agent → Tag → 组装 → 并发生成 → 合成 → 渲染 固定阶段跑；按 `snapshot_id` 缓存 BookPlan。
- `coursebook_agent/product/projections.py` — 按 plan 顺序排列章节 Agent；处理 chapter_indices 字符串与数字两种形式。
- `coursebook_agent/product/service.py` — 加 `get_revision / text_path_for / blob_path_for`；显式列名的 INSERT 修复 provider 列写入错位；`provider` 字段读取带兼容回退。
- `coursebook_agent/product/api.py` — `import_xuezai_uploads` 把登录错误暴露为 warning 而非静默；统一登录支持 `via_webvpn`。
- `coursebook_agent/sources/xuezai/assist.py` — 加 `via_webvpn` 字段与 URL 重写。
- `coursebook_agent/vendor/zhiyun/client.py` — `get_ppt_timeline` 翻页硬上限 `max_pages=20`（B10）。
- `coursebook_agent/app.py` — `POST /api/generate/v2`；progress callback 同步写回 `state.chapters`。
- `frontend/src/api/product.ts` — `startRun` 指向 `/api/generate/v2`。
- `frontend/src/pages/WorkflowConfigPage.tsx` — 移除"上传资料不接入生成"的旧说明。

### 已知遗留

- 学在浙大与智云今天都触发 CAS `loginView.sendsms.error`，需要 SMS 二次验证；端到端必须由浏览器先登录保存 session cookie。详见 `docs/ISSUES.md` B11 / B12。
- `tests/test_core.py::test_warning_render` 失败是 main 上队友 `fix: 修复quality.py` 把 `⚠️` 换成 `【易错】` 文字的回归，与本工作无关。

### 如何自己跑一遍

```bash
uv sync
uv run python -m unittest discover -s tests          # 73/74 通过
uv run python scripts/check_offline.py                # 离线回归通过
cd frontend && npm run build && npm run lint          # 通过
# 启动：
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
# 在浏览器打开 http://127.0.0.1:5173/datasets
```