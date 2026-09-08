# 不董就问：离线验收与联调交接

## 一键验证

```sh
uv sync --frozen
uv run python scripts/check_offline.py
cd frontend
npm ci
npm run build
```

已安装 Python 依赖时可直接使用 python scripts/check_offline.py。
脚本使用临时数据目录，主动禁止外部 socket 网络连接（允许事件循环的本机通信），不读取账号会话、
不消耗模型额度、不清理你的课程数据。

## 已实现

- 来源指标写入 LectureDraft.quality_metrics / quality_report，随章节和成书保存，
  通过成书、任务和质量报告接口返回；有效覆盖率要求该小节全部引用属于当前讲次。
- 来源时间由真实字幕计算；按引用顺序颠倒时仍取最早开始与最晚结束。
- 没有课程 Profile 时仍计算和检查来源；修复内置 Profile 加载路径。
- 未运行语义审校的结果不标 accepted；人工确认单独记录与回读。
- 任务状态、阶段事件、蓝图、讲次清单、成功章节和字幕证据保存为任务快照。
- 重启标记 interrupted；手动 retry 复用快照，仅补失败/未完成章节。
- only_indices=[] 只合成，None 为全课；缓存缺失不再静默输出空章节。
- 运行中可 cancel，60 分钟上限防止任务无限占用；成功章节保留。
- OpenAI 兼容模型的请求次数、成功/失败、重试、耗时和 provider usage Token
  会随 JobState 持久化，并在产品运行详情展示；未返回 usage 时不猜测 Token。
- 可在设置页填写输入/输出单价，运行统计按每百万 Token 估算成本；留空只展示用量。
- 限流、服务错误、超时等模型级失败会写入运行轨迹，区分“准备重试”和最终失败。
- 产物投影带有 dataset_id、dataset_name、snapshot_id；已结束运行删除时同步清理任务检查点。
- 关键生成产物原子写入；清缓存保留 jobs/runs，运行中拒绝清理。
- 模型鉴权/请求错误快速失败；限流、服务错误和超时有界重试；
  JSON 修复有上限；不将 reasoning 字段当作最终答案。
- 工作台保存最近任务标识并支持恢复/停止；质量报告显示有效来源指标。

## 接口交接（暮成雪）

- POST /api/jobs/{job_id}/retry：恢复失败、部分完成、中断任务。复用原 job_id。
- POST /api/jobs/{job_id}/cancel：停止排队/运行任务，保留快照。
- GET /api/jobs/{job_id}：包含 course_id、chapters、events。
- GET /api/runs：合并旧 V2 报告与有成书结果的新任务。
- GET /api/runs/{job_id}/report：包含 course_id、results[].deterministic.metrics.traceability，
  semantic、confirmation。未审校不等于通过。
- GET /api/jobs/{job_id}/chapters/{index}/sources/{chunk_id}：读取任务保存的字幕证据。

source_coverage 是 0–1 的小节有效引用覆盖率，不能标成“准确率”。
引用数量按去重的字幕块 ID 计算。旧产物可能没有指标，应显示“未校验”。

## 配置真实 API 后再验收（就云协作）

1. 在设置页自行登录智云、配置模型并测试连接。
2. 选一门已授权课程，先运行一章，再全课。
3. 对照字幕人工核对公式、数值、例题和章节衔接；记录模型、耗时与实际成本。
4. 验证真实限流/网络中断及重启后的恢复行为。
5. 与前端同伴联调智云播放器的时间戳跳转。

### 本轮最小真实联调记录

已用一份短 Markdown、一个输入快照和一个选中章节完成一次真实模型端到端运行：
资料解析、description、主 Agent 规划、章节生成、全书合成和 Markdown 产物均完成；
4 次请求全部成功，返回 15,953 Token，累计模型耗时约 119 秒。临时资料集、快照和运行产物
已在验收后删除。完整课程仍需使用正式资料集按“先单讲、后全课”执行。

## 明确边界

当前是单进程本地应用，不支持多 worker 或多用户隔离；不自动继续付费调用。
恢复保证复用成功章节和蓝图；失败章节会重新生成，不是 token 级续写。
旧任务若没有 course_id 无法自动恢复；快照缺失会补生成，课程讲次变化会阻止混用。
报告保留未通过的草稿以供人工检查，不能宣称所有导出内容均通过语义质检。
浏览器展示和真实课程质量需在联网联调时进一步验收。
