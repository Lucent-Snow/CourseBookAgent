# 公开部署

当前公开地址已更新为完整工作台（https://coursebook-demo.vercel.app/datasets），采用 ADR 012 / [HOSTING.md](HOSTING.md)，无需 Vercel 登录。以下静态流程是旧版本记录，不能用于当前完整版本发布。完整版本的真实验收和正式地址以 CURRENT_STATUS.md 为准。

2026-10-11。公开地址：https://coursebook-demo.vercel.app 。

## 展示范围

独立静态演示：三份概率论课堂资料的主题简介、既有九章教辅、章节目录与 Markdown 下载。简介为展示整理，非原始字幕预览。书稿来自 10-09 流水线结果，应用新阅读投影省略编辑性备注和无法判断的句子；没有按新提示词重新生成整书。

公开版不开放上传、实时生成、校内登录或系统设置。本地工作台仍保留完整功能。长任务和 SQLite/本机文件存储没有搬进 Vercel；后续如需公开生成，应另配持久化后端。

## 重复构建

从仓库根目录执行：

```bash
uv run python scripts/export_demo.py --book data/intermediate/coursebook-74397.json
VITE_DEMO_MODE=true npm --prefix frontend run build
uv run python scripts/deploy_demo.py --project coursebook-demo
```

产物仅在被 Git 忽略的 `frontend/public/demo-assets/` 与 `frontend/dist/`。导出选择一本书，不复制原始文件、数据库、Job、会话或 `.env`。没有样例文件时必须先通过单独的数据交接获得它，不能凭空构建假结果。

部署脚本使用 Vercel 官方 REST API 上传构建后的静态文件，优先从 `VERCEL_TOKEN` 获取授权，否则读本机 Vercel CLI 登录凭据。凭据不打印、不放入站点、不提交 Git。当前本机 CLI 网络连接失败，REST API 实测可用。

生产地址用于展示；每次部署返回不可变版本地址。脚本只创建/更新指定项目，不修改其他项目。

## 构建模式

- `VITE_DEMO_MODE=true`：公开演示入口，路由 `/demo/library`、`/demo/book`。
- 默认：完整本地工作台入口，仍使用 `/datasets` 等路由与现有后端。
- Vercel 仅重写 `/demo/*` 到静态入口；资源文件直接提供，未配置通往私人后端的代理。
