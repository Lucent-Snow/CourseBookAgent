# CourseBookAgent 技术架构

## 1. 技术定位

CourseBookAgent 的核心是**字幕 → 教辅书的生成工作流**，不是简单的字幕拼接。

| 层 | 技术 | 说明 |
|---|---|---|
| 数据获取 | 项目内置 Zhiyun adapter / 智云课堂接口 | 获取课程、讲次、带时间戳字幕，不依赖外部 skill |
| 后端 | Python + FastAPI | 编排长任务与 API |
| AI | 通用大模型 API | 生成工作流的核心 |
| 存储 | 本地文件 | 中间产物全缓存 |
| 前端 | 简单 Web | 课程选择、进度、教辅阅读 |
| 输出 | Markdown / HTML / PDF | 组件化渲染 |

---

## 2. 生成工作流

```text
字幕（原始）
    │
    ▼  字幕压缩（每讲独立，面向聪明主编）
    │  输入：完整字幕 TimedChunk[]
    │  输出：LectureDigest（知识点地图 + 教师流向 + 时间锚点）
    │  原则：主编知道假设检验是什么，只需知道"老师怎么讲的"
    │
    ▼  全书规划（主编统筹，全局）
    │  输入：14 份 LectureDigest
    │  输出：BookPlan
    │    ├─ 书的结构（模块/章节/角色/主线）
    │    ├─ 组件规范（ComponentSpec：Tips/例题/侧边栏/重点框）
    │    ├─ 共享系统 prompt（writer_system_prompt）
    │    ├─ 每章写作指令（ChapterInstruction）
    │    └─ 渲染配置（render_config）
    │
    ▼  分章撰写（每章独立）
    │  输入：writer_system_prompt + ChapterInstruction + 完整字幕
    │  输出：LectureDraft（带时间戳链接、组件实例、来源引用）
    │  原则：读者"比较蠢"，要讲详细；关键处链接到字幕时间段
    │
    ▼  全书合成（终审，全局）
    │  输入：14 章 LectureDraft + BookPlan
    │  输出：CourseBook（前言/知识地图/术语表/要点索引 + 组件统一）
    │
    ▼  渲染
     → Markdown（带时间戳文本引用）
     → Web（可点击的时间戳链接 + 组件 HTML）
     → PDF（省略时间戳链接）
```

---

## 3. 模块划分

```text
coursebook_agent/
├── app.py                  # FastAPI 入口
├── config.py               # 配置
├── models.py               # 数据模型
├── pipeline.py             # 工作流编排
├── sources/
│   └── zhiyun.py           # 智云课堂数据获取
├── preprocess/
│   └── transcript.py       # 字幕清洗 + 分块
├── agent/
│   ├── digest.py           # 字幕压缩
│   ├── editor.py           # 全书规划（主编）
│   ├── chapter.py          # 分章撰写
│   ├── synthesize.py       # 全书合成（终审）
│   ├── quality.py          # 质量门禁（组件契约/例子清理/确定性门禁/LLM 审校）
│   └── llm.py              # LLM 客户端
├── renderer/
│   └── markdown.py         # Markdown 渲染（含组件）
├── frontend/               # React 前端（书架/工作台/阅读器/设置/质量报告 5 页）
├── profiles/               # 课程 Profile（术语表/章节模板）
└── scripts/
    └── overnight_book_quality.py  # 通宵批处理脚本
```

---

## 4. 核心数据模型

详见 `coursebook_agent/models.py`。关键模型：

| 模型 | 层 | 用途 |
|---|---|---|
| `TimedChunk` | 0 | 分块后的字幕单元，带时间戳 |
| `KnowledgePoint` | 1 | 单个知识点（名/描述/类别/来源引用） |
| `LectureDigest` | 1 | 一讲的压缩知识点地图 |
| `ComponentSpec` | 2 | 可复用的 UI 组件规范（Tips/例题/侧边栏） |
| `ChapterInstruction` | 2 | 主编给某一章的写作指令 |
| `BookPlan` | 2 | 主编的完整蓝图 |
| `ChapterSection` | 3 | 章节中的小节（含组件实例和时间链接） |
| `LectureDraft` | 3 | 一章的完整产物 |
| `CourseBook` | 4 | 全书产物 |

---

## 5. 缓存策略

每一层的产物都缓存在 `data/` 下，支持断点续跑：

```text
data/
├── cache/zhiyun/           # 原始字幕缓存
├── intermediate/
│   ├── digest-*.json       # 字幕压缩产物
│   ├── chunks-*.json       # 清洗分块
│   ├── chapter-*.json      # 分章产物
│   └── coursebook-*.json   # 全书产物
├── plans/
│   └── bookplan-*.json     # 全书蓝图
└── output/
    ├── coursebook-*.md     # 最终 Markdown
    └── lecture-*.md        # 单章 Markdown
```

---

## 6. API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/courses` | 可用课程列表 |
| POST | `/api/generate` | 创建生成任务（全书） |
| GET | `/api/jobs/{job_id}` | 任务状态 |
| GET | `/api/jobs/{job_id}/book` | 获取生成后的教辅数据 |
| GET | `/api/jobs/{job_id}/download.md` | 下载 Markdown |
| GET | `/api/books/{course_id}` | 获取已缓存的教辅 |
| GET | `/api/books/{course_id}/download.md` | 下载已缓存 Markdown |

---

## 7. 关键设计决策

### 7.1 压缩 vs 完整的分层

主编只看压缩摘要（~2 万字），不看完整字幕（~30 万字）。写作者看完整字幕。这解决了上下文限制问题，同时保留了主编的全局视角。

### 7.2 组件化输出

主编定义"书长什么样"：Tips 框、例题格式、侧边栏、重点标记。写作者按规范使用组件。渲染器根据目标格式（Web/PDF）适配。

### 7.3 时间戳链接

Web 版的关键内容链接到字幕时间段，读者可跳转。PDF 版省略链接，保留文本引用。

### 7.4 当前不处理 PPT

PPT 获取、OCR 和字幕-PPT 对齐留作后续增强。
