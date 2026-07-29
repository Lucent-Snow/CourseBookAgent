# CourseBookAgent

CourseBookAgent 将智云课堂带时间戳字幕整理为结构化教辅书。采用四层生成工作流：字幕压缩 → 主编统筹 → 分章撰写 → 终审合成。

## 运行

```bash
uv sync
cp .env.example .env
# 在 .env 中配置 LLM_API_KEY 等参数
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000`。

## CLI

```bash
# 生成全书
uv run python -m coursebook_agent.cli --course-id 82493

# 只生成书蓝图
uv run python -m coursebook_agent.cli --course-id 82493 --plan-only

# 重生成单章
uv run python -m coursebook_agent.cli --course-id 82493 --lecture 2 --regenerate --review

# 通宵批处理
uv run python scripts/overnight_book_quality.py --course-id 82493 --review
```

## 测试

```bash
uv run python -m unittest discover -s tests -v
```

## 四层工作流

| 层 | 模块 | 说明 |
|---|---|---|
| 1. 字幕压缩 | `agent/digest.py` | 每讲压缩为知识点地图，面向聪明主编 |
| 2. 主编统筹 | `agent/editor.py` | 定结构 + 组件规范 + 每章指令 + 系统 prompt |
| 3. 分章撰写 | `agent/chapter.py` | 系统 prompt + 主编指令 + 完整字幕 → 教辅章节 |
| 4. 终审合成 | `agent/synthesize.py` | 前言 + 知识地图 + 术语表 + 要点索引 |
