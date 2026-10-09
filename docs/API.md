# CourseBookAgent API 接口文档

> 2026-10-09：HTTP 生成必须提供 snapshot_id，旧课程入口已删除。接口存在与行为可靠性分别验证，最新状态见 CURRENT_STATUS.md。

新增可靠性与来源接口、字段及离线验证命令见 [OFFLINE_ACCEPTANCE.md](OFFLINE_ACCEPTANCE.md)。

> 前端（React）与后端（FastAPI）的对接契约。产品工作台使用 `/api/product/*`；触发生成、运行生命周期和共享设置由 `app.py` 提供。下面表格里的端点与代码完全对应；真实外部链路与浏览器流程仍按 `docs/DEVELOPMENT.md` 验证。

## 共享基础接口

| 方法 | 路径 | 用途 | 对应页面 |
|---|---|---|---|
| GET | `/api/health` | 健康 + 配置状态 | 设置 |
| GET | `/api/zhiyun/auth` | 智云登录状态 | 设置 |
| POST | `/api/zhiyun/login` | 智云登录 | 设置 |
| POST | `/api/generate` | 触发多资料工作流；body 必须含 `snapshot_id` | 工作台 |
| GET | `/api/runs` | 带成书的 Job 与历史报告列表 | 报告接口（当前列表页使用产品投影） |
| GET | `/api/runs/{run_id}` | run 状态（事件、阶段、章节摘要、Usage） | 运行详情 |
| POST | `/api/runs/{run_id}/retry` | 失败 / 中断 / 部分完成任务恢复（复用 job_id） | 运行详情 |
| POST | `/api/runs/{run_id}/cancel` | 停止排队 / 运行任务，保留快照 | 运行详情 |
| GET | `/api/runs/{run_id}/report` | Job 章节质量报告，兼容历史报告文件 | 报告接口（当前运行页使用产品投影） |
| POST | `/api/runs/{run_id}/chapters/{lecture_index}/confirm` | 标记人工确认 | API 已有，当前前端无确认按钮 |
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
  "zhiyun": { "authenticated": true, "username": "student-id", "webvpn": false },
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

资料、快照和运行/产物投影使用 `/api/product/*`；生成、停止/恢复、下载和设置使用共享 `/api/*`。这些共享路径仍有效，不能按“旧接口”删除。

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

## 登录与实验台

统一登录请求：`{username, password, webvpn?: false, authcode?: null}`。首次遇到短信校验可以返回 HTTP 202 与 `sms_required`；第二次请求携带 `authcode`。真实登录仍取决于校内网络、会话与短信，不保证新环境一次成功。

实验台复用生成阶段函数，用于逐阶段迭代，不是普通用户前端：

| 方法 | `/api/product/snapshots/{id}/lab` 后缀 | 用途 |
|---|---|---|
| GET | `/status` | 阶段缓存状态 |
| POST | `/describe` | `{force?, revision_id?}` |
| POST | `/plan` | `{force?}` |
| POST | `/assemble` | 按 Tag 装配 |
| POST | `/chapters/{chapter_id}/generate` | `{force?, review?}` |
| POST | `/synthesize` | `{force?}` |
| GET | `/descriptions[/{revision_id}]`、`/plan`、`/chapters[/{chapter_id}]` | 查看中间产物 |
| DELETE | `/descriptions[/{revision_id}]`、`/plan`、`/chapters[/{chapter_id}]` | 清理指定缓存 |

Lab 合成只保存 CourseBook 缓存，不自动注册 Job/Artifact 或输出 Markdown；没有 PDF 导出端点。

## 已知契约边界

1. 已有 12 章实验成品，但没有对应产品 Job；不能因文件存在就假定 `/artifacts` 可读。
2. retry 使用同一 Job 与原请求，章节缓存可复用失败/降级内容；精准恢复须单独验收。
3. `/download.md` 按 course_id 或 run_id 取文件，核心输出按 course_id 或 snapshot_id 命名；历史版本与文件定位尚未完全统一。
4. `PUT /api/settings/llm` 写 `.env`，当前无鉴权；公开发布前需设置访问边界。
5. 当前网页的质量检测来自产品运行投影；人工确认用共享接口。旧章节 GET 路由已移除，不按旧文档调用。
