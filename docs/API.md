# CourseBookAgent API 接口文档

> 前端（React）与后端（FastAPI）的对接契约。按设计稿 5 页（书架 / 工作台 / 阅读器 / 设置 / 质量报告）组织。以下接口均已实现。

## 全部接口

| 方法 | 路径 | 用途 | 对应页面 |
|---|---|---|---|
| GET | `/api/health` | 健康 + 配置状态 | 设置 |
| GET | `/api/zhiyun/auth` | 智云登录状态 | 设置 |
| POST | `/api/zhiyun/login` | 智云登录 | 设置 |
| GET | `/api/courses` | 课程列表 | 书架 / 工作台 |
| GET | `/api/books` | 已生成成书列表 | 书架 |
| GET | `/api/books/{course_id}` | 缓存成书 | 书架→阅读器 |
| GET | `/api/books/{course_id}/download.md` | 缓存下载 | 阅读器 |
| POST | `/api/generate` | 全课生成任务 | 工作台 |
| GET | `/api/jobs/{job_id}` | 任务状态 | 工作台 |
| GET | `/api/jobs/{job_id}/book` | 生成结果 | 工作台→阅读器 |
| GET | `/api/jobs/{job_id}/download.md` | 下载 Markdown | 阅读器 |
| POST | `/api/courses/{course_id}/lectures/{index}/regenerate` | 单讲重生成 | 质量报告 |
| GET | `/api/settings` | 配置状态（LLM 脱敏 + 智云 + 数据统计） | 设置 |
| PUT | `/api/settings/llm` | 保存 LLM 配置（写 .env） | 设置 |
| POST | `/api/settings/llm/test` | 测试 LLM 连接 | 设置 |
| GET | `/api/runs` | V2 run 列表 | 质量报告 |
| GET | `/api/runs/{run_id}/report` | V2 质量报告 | 质量报告 |
| GET | `/api/runs/{run_id}/chapters/{lecture_index}` | V2 章节产物 | 质量报告 |
| POST | `/api/runs/{run_id}/chapters/{lecture_index}/confirm` | 标记人工确认 | 质量报告 |
| DELETE | `/api/cache` | 清派生产物（保留原始字幕与蓝图） | 设置 |

## 契约

### 设置

```json
// GET /api/settings
{
  "llm": { "base_url": "https://api.example.com/v1", "model": "qwen-plus",
           "api_key_set": true, "configured": true },
  "zhiyun": { "authenticated": true, "username": "3240100242", "webvpn": false },
  "data": { "cache_bytes": 9017753, "course_count": 1 }
}

// PUT /api/settings/llm
{ "base_url": "...", "model": "...", "api_key": "..." }
→ { "ok": true, "configured": true }

// POST /api/settings/llm/test
{ }  → { "ok": true, "model": "qwen-plus", "latency_ms": 812 }
```

### 质量报告

```json
// GET /api/runs
{ "data": [ { "run_id": "82493-v2-...", "accepted": 12, "rejected": 2, "course_id": "82493" } ] }

// POST /api/runs/{run_id}/chapters/{lecture_index}/confirm
{ "note": "已人工对照原音频确认" }  → { "ok": true }
```

### 单讲重生成

```json
// POST /api/courses/{course_id}/lectures/{index}/regenerate
{ }  → { "job_id": "abc123..." }
```

## 遗留问题（记录，之后迭代）

1. V2 目前只有 4 讲 pilot run，`GET /api/runs` 需能容忍无全量 run 的情况。
2. 单讲重生成后重新 synthesize 全书，与全课生成共用 `generation_lock`，耗时会阻塞（见 ISSUES B3）。
3. `PUT /api/settings/llm` 写 `.env` 无鉴权，本地应用可接受，多用户部署待议（见 ISSUES B2）。
