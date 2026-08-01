# ADR-003: 教辅书生成工作流（字幕压缩 → 全书规划 → 分章撰写 → 全书合成）

## Status

Accepted (implementation in progress)

## Context

ADR-002 确立了"主编 + 分章写作者 + 终审"三层架构。经过通宵实验验证，该方向有效（14/14 章有承上启下、重点、易错点）。但存在以下问题：

1. 压缩摘要依赖旧版生成物，信息有损
2. 主编只定结构，不定组件规范，导致各章格式不统一
3. 分章写作者的 prompt 是硬编码的，主编无法控制写作风格
4. 时间戳没有链接，Web 版不能跳转

## Decision

升级为分层架构，各环节职责更清晰（结构可能随验证演进）：

### Layer 1: 字幕压缩（新）

- 输入：完整字幕
- 输出：LectureDigest（知识点地图，面向聪明主编）
- 原则：主编知道概念是什么，只需知道"老师怎么讲的"

### Layer 2: 主编统筹（增强）

- 输出新增：ComponentSpec（组件规范）、writer_system_prompt（共享写作 prompt）
- 每章指令 ChapterInstruction 包含组件使用说明和深度指导

### Layer 3: 分章撰写（增强）

- 输入改为：系统 prompt + 主编指令 + 完整字幕（三层拼接）
- 输出新增：ChapterComponent（组件实例）、transcript_links（时间戳链接）

### Layer 4: 终审合成（增强）

- 不重写正文，只修补书级字段
- 统一组件渲染

## Non-goals

- 不改变输入（仍然是课程 ID → 字幕）
- 不改变输出目标（Markdown / Web / PDF）

## 渲染策略

- Web 版：时间戳可点击跳转，组件用 HTML（折叠/侧边栏/高亮）
- PDF 版：时间戳保留文本引用，组件用静态排版
- Markdown 版：通用文本标记

## Consequences

- pipeline.py 需要重写编排逻辑
- 所有 agent/ 模块需要适配新数据模型
- renderer 需要支持组件渲染
- 前端需要支持组件 HTML
