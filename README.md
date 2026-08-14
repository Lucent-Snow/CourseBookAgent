# CourseBookAgent

把智云课堂字幕整理成结构化课程教辅的教学智能体。输入一门课程，自动获取字幕并生成可阅读、可复习、可追溯的教辅书（网页 / Markdown）。

## 架构

- **后端** FastAPI + Python：字幕获取 → 清洗分块 → 字幕压缩 → 全书规划 → 分章撰写（并发）→ 质量门禁 → 全书合成
- **前端** React + TypeScript + Vite + Tailwind + shadcn/ui：5 页（书架 / 工作台 / 阅读器 / 设置 / 质量报告）
- **质量门禁** `agent/quality.py`：组件契约、例子清理、确定性门禁、LLM 审校

## 运行

### 后端

```bash
uv sync
cp .env.example .env
# 在 .env 中填入自己的 LLM 端点、模型名、API key
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173，/api 代理到 8000
```

浏览器打开 `http://localhost:5173`。

## 测试

```bash
uv run python -m unittest discover -s tests -v   # 后端（24 用例）
cd frontend && npm run build                      # 前端构建
```

## CLI

```bash
uv run python -m coursebook_agent.cli --course-id 82493 --plan-only   # 生成全书蓝图
uv run python -m coursebook_agent.cli --course-id 82493 --only 2,3,4 --regenerate --review  # 重生成指定讲次
uv run python -m coursebook_agent.cli --course-id 82493               # 生成全书（章节并发）
```

## 说明

- 生成结果缓存在 `data/`：`cache/`（原始字幕，勿删）、`intermediate/`（中间产物）、`output/`（Markdown）
- `data/` 里的旧产物作为**反面案例**保留，用于对照 prompt 与生成结果迭代
- 使用自己的 LLM 配置（OpenAI 兼容端点），项目不内置任何端点或 key
- 详细设计见 `docs/`，问题清单见 `docs/ISSUES.md`
