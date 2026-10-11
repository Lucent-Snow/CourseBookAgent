# 完整工作台的 Vercel 部署

当前适配方案见 ADR 012。线上使用完整 React App 和 FastAPI，默认游客独立空间，不使用个人 VPS，不要求注册，不自动启用付费套餐。

## 资源与配置

- Vercel Hobby 项目，私有 Blob Store 连接该项目。
- `COURSEBOOK_CLOUD=1`、`BLOB_READ_WRITE_TOKEN`、至少 32 字符随机 `COURSEBOOK_SESSION_SECRET`。
- Python 3.12 或更新版本，使用锁文件依赖。Workflow 注册于 `coursebook_agent.hosting.workflows:wf`。
- 凭据只写 Vercel 环境变量。公开访客不会继承本机 `.env` 的模型 Key 或校内会话。每个访客可以在正常设置页配置自己的模型。
- 正式域名需允许公开访问；预览域名可以保留 Vercel 认证保护。这与产品游客身份是两回事。

## 数据与任务

签名 Cookie 确定空间，API 按空间恢复私有文件和 SQLite；不是靠前端隐藏条目。上传文件、快照、模型配置、平台会话和所有产物均属于当前空间。Cookie 有效期 90 天，删除 Cookie 无法找回游客数据；不提供跨设备同步。

工作空间清单使用 ETag 条件写入。只合并不冲突的文件修改，同一文件冲突返回 409；前端提示刷新重试。清单读取绕开 CDN 缓存，内容寻址文件可使用验证过的临时缓存。临时磁盘和进程里的 Job 字典不是持久存储。资料版本路径相对产品根目录保存。

Workflow 重放相同流水线，每步最多新增一批模型响应，批内并发遵循用户配置；Job 的私有日志保留已成功的模型响应，避免正常重放再次计费。没有改变生成提示词或使用实验台入口。单次调用限制 235 秒，为存档留出时间；更慢的模型可能需要换模型或续跑。模型服务已接受但响应未完成时仍可能计费，不能承诺网络失败下的恰好一次计费。

停止任务先持久化中断状态，再终止 Workflow；正在执行的外部调用可能继续，但旧步骤不能覆盖停止状态。失败、部分完成和中断均沿用正常续跑入口。

大于 3 MB 的资料自动分片上传（每片 2 MB），避免平台 4.5 MB 请求限制；单文件目前限制 64 MB。文件上传完成后仍走同一个文档解析器。

## 预设与发布

`export_workbench_preset.py --job <完成任务>` 只导出该任务、输入快照及选中的资料版本。输出在被忽略的 `data/deployment-preset/`，不能提交原始资料、成品或凭据。首次访问复制预设进入游客空间；删除后不反复恢复。已有书稿明确标记为完成预设，查看不调用模型。

`deploy_workbench.py` 上传应用源码和显式导出的预设；默认预览部署。`--production` 才更新正式版本。它不上传整个工作目录、`.env`、会话、实验数据或静态 demo 内容。发布脚本先构建完整前端，再将输出作为 `public/` 文件上传，确保静态资源被平台 CDN 收录。

## 免费边界

核实日期 2026-10-11：Hobby 的单步骤上限为 300 秒；Workflow 每月包含 50,000 事件、1 GB 写入，完成后平台日志仅保留 1 天；私有 Blob 包含约 1 GB 存储、10 GB 传输、10,000 简单操作、2,000 高级操作。多次存档及文件旧版本会消耗空间与操作数，游客体验需要关注额度；当前尚无自动回收闲置游客和孤立对象的任务。

超额可能暂停云端功能，不能自动升级。模型 API 费用独立于托管，不保证所有模型调用免费。公开预设浏览不产生模型费用。

官方参考：[Hobby](https://vercel.com/docs/plans/hobby)、[Blob 额度](https://vercel.com/docs/vercel-blob/usage-and-pricing)、[Workflow 额度](https://vercel.com/docs/workflows/pricing)、[Python Workflow](https://workflow-sdk.dev/docs/getting-started/python)。
