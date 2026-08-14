# 问题清单（迭代中记录）

> 前后端全链路实现过程中发现的问题，按优先级排列，之后逐个迭代优化。

## 后端

| # | 问题 | 影响 | 状态 |
|---|---|---|---|
| B1 | `enforce_component_contract` 把 `steps` 数组 `str()` 成 Python list 字符串 | 步骤组件渲染出 Python 语法残留 | ✅ 已修（quality.py 对 list 用 extend） |
| B2 | `PUT /api/settings/llm` 直接写 `.env` 无鉴权 | 本地应用可接受，但多用户部署不安全 | 记录待议 |
| B3 | 单讲重生成后重新 synthesize 全书，且与全课生成共用 `generation_lock` | 重生成一章也要等全书合成，耗时且阻塞 | 待优化（增量合成） |
| B4 | `DELETE /api/cache` 会删 `data/runs`（质量报告记录） | 清除缓存后质量报告页为空 | 待议删除范围 |
| B5 | V2 只有 4 讲 pilot run，无全量 14 讲 run | 质量报告页只有试点数据 | 需跑全量 V2 |
| B6 | LLM 配置从 `.env` 读，`save_llm_settings` 后内存 config 已刷新但 `LLM_TIMEOUT` 等未联动 | 设置页改动不完整 | 待完善 |
| B7 | `synthesize_book` 单次大调用（14 章摘要喂给 LLM），JSON 返回不稳触发 repair 重试 | 合成阶段慢（约 2-3 分钟） | 待拆分或确定性回退 |

## 前端

| # | 问题 | 影响 | 状态 |
|---|---|---|---|
| F1 | 书架 53 个课程卡片全量渲染，无搜索/筛选/分页 | 课程多时首屏卡顿、难找课 | 待加搜索 |
| F2 | `ReviewPage` 重生成用 `run_id.split('-')[0]` 推断 course_id | 脆弱，run_id 格式变化即错 | 后端应在 report 里返回 course_id |
| F3 | `WorkspacePage` 的 courseId 从 query 读，课程不在下拉列表时无对应 option | 选课状态可能错配 | 待校验 |
| F4 | 设置页保存 LLM 后 `api_key_set` 未刷新 | 显示状态不准确 | 待修 |
| F5 | 阅读器时间戳仍是纯文本，未接播放器跳转 | 「来源可追溯」卖点未完全落地 | 需接智云播放器 |
| F6 | V1 产物 `examples` 含 Python dict 残留（`{'example': ...}`） | 前端直接展示会暴露机器残留 | ✅ 已修（前端 sanitize + 后端 sanitize_examples） |

## 产品 / 体验

| # | 问题 | 说明 |
|---|---|---|
| P1 | 首次使用引导缺失 | 未配置 LLM / 未登录智云时，应引导到设置页，而非静默失败 |
| P2 | 书架无课程封面元信息 | 目前用渐变色块代替，真实封面/教师头像可增强辨识度 |
| P3 | 质量报告无「已确认」状态回读 | 确认写入 `review/confirm-*.json`，前端未回显已确认状态 |

## 完成标准回顾

- [x] 后端 7 个新接口（settings/runs/confirm/regenerate/cache/books 列表/llm test）
- [x] 前端 5 页路由 + 全部连接后端
- [x] 后端 24 测试通过
- [x] 浏览器端到端验证 5 页 + 深度检查通过
- [ ] B1/F6 机器残留修复（P0，影响成品质量）
- [ ] F5 时间戳跳转（P0，卖点落地）
- [ ] B5 全量 V2 run（P0，质量报告有数据）
