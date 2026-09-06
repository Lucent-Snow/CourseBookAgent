# CourseBookAgent API 接口文档

新增可靠性与来源接口、字段及离线验证命令见 [OFFLINE_ACCEPTANCE.md](OFFLINE_ACCEPTANCE.md)。

> 前端（React）与后端（FastAPI）的对接契约。按当前 5 页（书架 / 工作台 / 阅读器 / 设置 / 质量报告）组织。以下接口均已在代码中定义；真实外部链路和完整浏览器流程仍需按 `docs/DEVELOPMENT.md` 验证。

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

## 产品工作台接口

新产品工作台使用 `/api/product/*`，现有课程、任务和成书接口继续保留兼容。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET/POST | `/api/product/datasets` | 资料集列表 / 新建空白资料集 |
| GET/DELETE | `/api/product/datasets/{dataset_id}` | 资料集详情 / 删除 |
| POST | `/api/product/datasets/{dataset_id}/resources` | 上传 PPTX、PDF、DOCX、MD、TXT |
| POST | `/api/product/datasets/{dataset_id}/imports/zhiyun` | 按课程 ID 导入讲次字幕 |
| GET | `/api/product/resource-revisions/{revision_id}/preview` | 查看解析文本 |
| GET/POST | `/api/product/datasets/{dataset_id}/snapshots` | 输入快照列表 / 创建不可变快照 |
| GET | `/api/product/workflow-presets` | 工作流预设列表 |
| GET | `/api/product/runs[/{run_id}]` | 结构化运行和章节 Agent 投影 |
| GET | `/api/product/artifacts[/{artifact_id}]` | 按 Job ID 区分的独立产物 |

`POST /api/generate` 新增可选字段：`snapshot_id`、`preset_id`、`lecture_indices` 和 `concurrency`。旧请求仍兼容。`lecture_indices` 映射现有局部章节生成能力，`concurrency` 限制为 1–8。

资料集、资源版本和输入快照的架构边界见 `docs/decisions/008-product-workbench-application-layer.md`。上传材料已真实保存和解析；当前生成核心仍以智云讲次字幕为主要上下文，其他材料进入生成 prompt 的适配需要与生成工作线共同确认。

## 遗留问题（记录，之后迭代）

1. V2 目前只有 4 讲 pilot run，`GET /api/runs` 需能容忍无全量 run 的情况。
2. 单讲重生成后重新 synthesize 全书，与全课生成共用 `generation_lock`，耗时会阻塞（见 ISSUES B3）。
3. `PUT /api/settings/llm` 写 `.env` 无鉴权，本地应用可接受，多用户部署待议（见 ISSUES B2）。
