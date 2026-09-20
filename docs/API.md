# CourseBookAgent API 接口文档

新增可靠性与来源接口、字段及离线验证命令见 [OFFLINE_ACCEPTANCE.md](OFFLINE_ACCEPTANCE.md)。

> 前端（React）与后端（FastAPI）的对接契约。产品工作台使用 `/api/product/*`；触发生成、运行生命周期和共享设置由 `app.py` 提供。下面表格里的端点与代码完全对应；真实外部链路与浏览器流程仍按 `docs/DEVELOPMENT.md` 验证。

## 全部接口

| 方法 | 路径 | 用途 | 对应页面 |
|---|---|---|---|
| GET | `/api/health` | 健康 + 配置状态 | 设置 |
| GET | `/api/zhiyun/auth` | 智云登录状态 | 设置 |
| POST | `/api/zhiyun/login` | 智云登录 | 设置 |
| POST | `/api/generate` | 触发多资料工作流；body 必须含 `snapshot_id` | 工作台 |
| GET | `/api/runs` | run 列表 | 质量报告 |
| GET | `/api/runs/{run_id}` | run 状态（事件、阶段、章节摘要、Usage） | 运行详情 |
| POST | `/api/runs/{run_id}/retry` | 失败 / 中断 / 部分完成任务恢复（复用 job_id） | 运行详情 |
| POST | `/api/runs/{run_id}/cancel` | 停止排队 / 运行任务，保留快照 | 运行详情 |
| GET | `/api/runs/{run_id}/report` | 质量报告 | 质量报告 |
| GET | `/api/runs/{run_id}/chapters/{lecture_index}` | 章节产物 | 质量报告 |
| POST | `/api/runs/{run_id}/chapters/{lecture_index}/confirm` | 标记人工确认 | 质量报告 |
| GET | `/api/runs/{run_id}/download.md` | 下载 Markdown | 产物详情 |
| GET | `/api/settings` | 配置状态（LLM 脱敏 + 智云 + 数据统计） | 设置 |
| PUT | `/api/settings/llm` | 保存 LLM 配置（写 `.env`） | 设置 |
| POST | `/api/settings/llm/test` | 测试 LLM 连接 | 设置 |
| DELETE | `/api/cache` | 清派生产物（保留原始字幕与蓝图） | 设置 |

## 契约

### 触发生成

```json
// POST /api/generate
{
  "snapshot_id": "snap-1",
  "course_id": "75061",        // 可选；只作为 metadata
  "regenerate": false,
  "review": true,
  "concurrency": 3,
  "chapter_indices": [1, 2, 3]  // 可选；缺省生成全部
}
→ JobState
```

### 设置

```json
// GET /api/settings
{
  "llm": { "base_url": "https://api.example.com/v1", "model": "qwen-plus",
           "api_key_set": true, "configured": true,
           "input_price_per_million": null, "output_price_per_million": null },
  "zhiyun": { "authenticated": true, "username": "3240100242", "webvpn": false },
  "data": { "cache_bytes": 9017753, "course_count": 1 }
}

// PUT /api/settings/llm
{ "base_url": "...", "model": "...", "api_key": "...", "input_price_per_million": null, "output_price_per_million": null }
→ { "ok": true, "configured": true }

// POST /api/settings/llm/test
{ }  → { "ok": true, "model": "qwen-plus", "latency_ms": 812, "usage": { "total_tokens": 12 } }
```

### 质量报告

```json
// GET /api/runs
{ "data": [ { "run_id": "abc12345", "accepted": 12, "rejected": 2, "course_id": "75061" } ] }

// POST /api/runs/{run_id}/chapters/{lecture_index}/confirm
{ "note": "已人工对照原音频确认" }  → { "ok": true }
```

## 产品工作台接口

产品工作台所有数据读写都走 `/api/product/*`。前端默认使用这些接口，不直接访问 `/api/generate` 之外的旧路径。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET / POST | `/api/product/datasets` | 资料集列表 / 新建空白资料集 |
| GET / DELETE | `/api/product/datasets/{dataset_id}` | 资料集详情 / 删除 |
| POST | `/api/product/datasets/{dataset_id}/resources` | 上传 PPTX、PDF、DOCX、MD、TXT |
| GET | `/api/product/imports/zhiyun/courses` | 智云课堂“我的课程” |
| GET | `/api/product/imports/zhiyun/courses/{course_id}` | 智云课堂讲次列表 |
| POST | `/api/product/datasets/{dataset_id}/imports/zhiyun` | 智云课堂讲次 + 课件导入 |
| GET | `/api/product/imports/xuezai/courses` | 学在浙大“我的课程” |
| GET | `/api/product/imports/xuezai/courses/{course_id}` | 学在浙大课件列表 |
| POST | `/api/product/datasets/{dataset_id}/imports/xuezai` | 学在浙大课件下载导入 |
| GET | `/api/product/auth/providers` | 两个 provider 的连接状态 |
| POST | `/api/product/auth/login` | 统一身份认证登录，同步获取智云和学在浙大会话 |
| GET | `/api/product/resource-revisions/{revision_id}/preview` | 查看解析文本 |
| GET / POST | `/api/product/datasets/{dataset_id}/snapshots` | 输入快照列表 / 创建不可变快照 |
| GET | `/api/product/snapshots/{snapshot_id}` | 单个快照 |
| GET | `/api/product/workflow-presets` | 工作流预设列表 |
| GET / DELETE | `/api/product/runs[/{run_id}]` | 结构化运行和章节 Agent 投影 |
| GET | `/api/product/datasets/{dataset_id}/runs` | 资料集下所有运行 |
| GET | `/api/product/artifacts[/{artifact_id}]` | 按 Job ID 区分的独立产物 |

资料集、资源版本和输入快照的架构边界见 `docs/decisions/008-product-workbench-application-layer.md`。

## 遗留问题（记录，之后迭代）

1. 目前只有 4 讲 pilot run，`GET /api/runs` 需能容忍无全量 run 的情况。
2. 单讲重生成后重新 synthesize 全书，与全课生成共用 `generation_lock`，耗时会阻塞（见 ISSUES B3）。
3. `PUT /api/settings/llm` 写 `.env` 无鉴权，本地应用可接受，多用户部署待议（见 ISSUES B2）。
