# AGENTS.md

CourseBookAgent — 把智云课堂字幕整理成课程教辅的教学智能体（启真问智比赛项目）。

本文件是地图，不是百科全书。细节在 `docs/` 中。

## 每次任务开始前读

- `docs/PRODUCT_HANDOFF.md`：产品交接总文档，理解目标、输入输出、比赛策略
- `docs/ARCHITECTURE.md`：系统架构与模块划分
- `docs/WORKFLOW.md`：生成工作流的具体设计

## 需要时读

- `docs/PRD.md`：产品需求文档
- `docs/COMPETITION.md`：比赛定位与申报话术
- `docs/examples/OUTPUT_SPEC.md`：教辅书输出格式示例
- `docs/API_ZHIYUN.md`：智云课堂数据获取接口
- `docs/decisions/`：架构决策记录

## 开发命令

```bash
uv sync                          # 安装依赖
uv run python -m unittest discover -s tests -v   # 跑测试
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000  # 起服务
uv run python -m coursebook_agent.cli --course-id 82493 --plan-only  # 生成全书蓝图
uv run python -m coursebook_agent.cli --course-id 82493 --only 2,3,4 --regenerate --review  # 重生成指定讲次
uv run python scripts/overnight_book_quality.py --course-id 82493 --review  # 全量重跑
```

## 模块边界

- `sources/`：从智云课堂拉取课程、讲次、字幕，不碰生成逻辑
- `agent/`：生成核心——`digest.py`（字幕压缩）、`editor.py`（全书规划）、`chapter.py`（分章撰写）、`synthesize.py`（全书合成）
- `renderer/`：只负责渲染 Markdown / 前端数据，不做生成
- `preprocess/`：字幕清洗分块，纯确定性逻辑，不调 LLM
- 生成结果缓存在 `data/`。不要删 `data/cache/`（原始字幕）和 `data/plans/`（蓝图）

## 工作规则

- 核心目标：让输出像一本可复习的教辅书，不是讲次摘要拼接
- 前端只是展示；核心发力点是生成工作流
- 新增功能必须回答：它是否让"课程 → 教辅书"的输出更稳、更像成稿？
- 文档和代码同步更新；复杂改动先写 ADR 到 `docs/decisions/`
- 任何改动都要跑测试：`uv run python -m unittest discover -s tests -v`
