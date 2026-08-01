# CourseBookAgent

把智云课堂字幕整理成结构化课程教辅的教学智能体。输入一门课程，自动获取字幕并生成可阅读、可复习的教辅书（Markdown / 网页）。

## 运行

```bash
uv sync
cp .env.example .env
# 在 .env 中填入你自己的 LLM 端点、模型名、API key
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000`。

## 测试

```bash
uv run python -m unittest discover -s tests -v
```

## CLI

```bash
uv run python -m coursebook_agent.cli --course-id 82493 --plan-only   # 生成全书蓝图
uv run python -m coursebook_agent.cli --course-id 82493 --only 2,3,4 --regenerate --review  # 重生成指定讲次
uv run python -m coursebook_agent.cli --course-id 82493               # 生成全书
```

## 说明

- 生成结果缓存在 `data/`：`cache/`（原始字幕）、`plans/`（全书蓝图）、`intermediate/`（中间产物）、`output/`（最终 Markdown）
- 使用自己的 LLM 配置（OpenAI 兼容端点），项目不内置任何端点或 key
- 详细设计见 `docs/`
