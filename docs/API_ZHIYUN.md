# 智云课堂 API 接口文档

> CourseBookAgent 的智云集成现已内置于 `coursebook_agent/vendor/zhiyun/`，不依赖 pi skill、`zju-scholar` 安装目录或外部可执行脚本。
> 本文其余部分保留平台端点与数据字段的调研记录；CLI 用法已由项目内的 `ZhiyunSource` 替代。
> 测试课程：实验设计与心理统计Ⅱ（course_id=82493）。

---

## 0. 前置条件

### 运行环境

```bash
uv sync

# 推荐：在 .env 中设置；不把 JWT 提交进仓库
ZHIYUN_JWT=<智云课堂 JWT>

# 可选：只导入已有会话数据；项目不会执行该位置的任何外部脚本
ZHIYUN_SESSION_FILE=/absolute/path/to/session.json
```

运行时通过项目内的 `coursebook_agent.sources.zhiyun.ZhiyunSource` 调用 API。首次获取后，课程、讲次和字幕缓存在 `data/cache/zhiyun/`，离线读取缓存不需要 JWT。

### 统一 JSON 输出格式

```json
{
  "ok": true/false,
  "platform": "zhiyun",
  "feature": "<接口名>",
  "source": "live",
  "generated_at": "ISO8601",
  "meta": {},
  "data": {},
  "error": {"message": "..."}   // 仅 ok=false 时
}
```

---

## 1. login — 登录

**用途**：用浙大统一认证凭证登录，同时开通 ZDBK、学在浙大、智云课堂三个服务的 session。
**这是 CourseBookAgent 的第一步——用户必须先登录才能获取课程数据。**

### 命令

```bash
# 首次登录（保存凭证 + 登录全部服务）
$PYTHON zju_login.py -u 学号 -p 密码

# 校外强制 WebVPN
$PYTHON zju_login.py -u 学号 -p 密码 --webvpn

# 使用已保存凭证重新登录
$PYTHON zju_login.py

# 查看登录状态（不执行登录）
$PYTHON zju_login.py --status
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `-u, --username` | string | 首次必填 | 学号 |
| `-p, --password` | string | 首次必填 | 密码 |
| `--webvpn` | flag | 否 | 强制通过 WebVPN（校外网络） |
| `--status` | flag | 否 | 只查看状态，不执行登录 |
| `--save-only` | flag | 否 | 只保存凭证，不登录 |
| `--zhiyun-token` | string | 否 | 手动设置智云 JWT（自动获取失败时） |

### 登录流程

```text
zju_login.py -u 学号 -p 密码
    │
    ├─ 1. CAS 统一认证登录 → TGT/ST
    ├─ 2. ST → 教务网 (ZDBK)
    ├─ 3. ST → 学在浙大 (Courses)
    ├─ 4. 获取智云课堂 JWT
    │
    └─ 5. session 保存到 data/session.json
         凭证保存到 data/credentials.json（可选复用）
```

### 输出

```
正在登录统一认证 (学号: 3240100242)...
  统一认证登录成功
正在登录教务网(ZDBK)...
  教务网登录成功
正在登录学在浙大(Courses)...
  学在浙大登录成功
正在登录智云课堂...
  智云课堂登录成功

登录完成，session 已保存。
```

### --status 输出

```
=== 凭证 ===
  学号: 3240100242
  密码: ***************
  智云 JWT: 未设置

=== Session ===
  学号: 3240100242
  模式: WebVPN (校外)
  智云 JWT: 已设置
```

### CourseBookAgent 对接

```text
前端：用户输入 学号 + 密码
    │
    ▼
后端：subprocess.run([python, zju_login.py, -u, username, -p, password])
    │
    ├─ returncode=0 → session 就绪
    └─ returncode≠0 → 返回错误给前端
```

登录成功后，后续所有 `zju_zhiyun.py` 命令自动读取 `data/session.json`，不再需要传凭证。

### ⚠️ 注意

- 凭证和 session 存在 **skill 目录**的 `data/` 下，不在 CourseBookAgent 项目目录。
- MVP 假设单用户；多用户场景需 session 隔离。
- Session 会过期（几小时到一天），过期需重新登录。
- 校外网络自动走 WebVPN，也可 `--webvpn` 强制。
- 密码明文存在 `credentials.json`——MVP 可接受，产品化需加密或内存态。

### 映射到 CourseBookAgent API

| CourseBookAgent 接口 | 底层调用 |
|---|---|
| `POST /api/login` | `zju_login.py -u -p` |
| `GET /api/login/status` | `zju_login.py --status` |
| `GET /api/courses` | `zju_zhiyun.py my-courses` |
| `POST /api/generate` | `zju_zhiyun.py videos` → `transcript` → `ppt` |

---

## 2. my-courses — 课程列表

**用途**：获取当前账号的智云课堂课程列表。CourseBookAgent 的选课入口。

### 命令

```bash
$PYTHON zju_zhiyun.py my-courses [--keyword KEYWORD] [--teacher TEACHER]
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `--keyword` | string | 否 | 课程名称关键词 |
| `--teacher` | string | 否 | 教师姓名 |

### 输出字段

`data[]`，每个元素：

| 字段 | 类型 | 说明 |
|---|---|---|
| `course_id` | int | **智云课程 ID，后续所有接口的核心输入** |
| `title` | string | 课程名称 |
| `term` | string | 学期，如 `2025-20262` |
| `teacher` | string | 教师姓名 |
| `college` | string | 学院 |
| `course_code` | string | 课程代码 |
| `course_key` | string | 课程唯一键 |
| `prev_sub_id` | int | 最近讲次的 sub_id |
| `progress` | object | 学习进度 |

### 测试结果

```json
{
  "course_id": 82493,
  "title": "实验设计与心理统计Ⅱ",
  "term": "2025-20262",
  "teacher": "沈模卫,董一胜",
  "college": "心理与行为科学系",
  "course_code": "PSY2006M"
}
```

返回约 6 门课程（当前账号）。

---

## 3. videos — 讲次视频列表

**用途**：获取某门课程所有讲次。每个讲次对应一个 `sub_id`，是字幕和 PPT 的输入。

### 命令

```bash
$PYTHON zju_zhiyun.py videos --course-id COURSE_ID
$PYTHON zju_zhiyun.py videos --course "课程名称"
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `--course-id` | int | 二选一 | 智云课程 ID |
| `--course` | string | 二选一 | 课程名称（模糊匹配） |
| `--teacher` | string | 否 | 教师姓名 |
| `--with-all-status` | flag | 否 | 包含未转字幕视频 |

### 输出字段

`data[]`，每个元素：

| 字段 | 类型 | 说明 |
|---|---|---|
| `sub_id` | string | **讲次 ID，字幕/PPT 的核心输入** |
| `title` | string | 讲次标题，如 `2026-06-16第1-2节` |
| `duration` | int | 时长（秒），实测为 0 |
| `has_transcript` | bool | 是否有字幕，实测为 null |
| `has_ppt` | bool | 是否有 PPT，实测为 null |

### 测试结果

```json
// course_id=82493, 共 14 个讲次，按时间倒序
[
  {"sub_id": "1941530", "title": "2026-06-16第1-2节"},
  {"sub_id": "1937894", "title": "2026-06-09第1-2节"},
  {"sub_id": "1931756", "title": "2026-05-26第1-2节"}
  // ... 共 14 个
]
```

### ⚠️ 注意

- `duration` / `has_transcript` / `has_ppt` 实测均为 0/null，**不可依赖**。
- 讲次按时间倒序（最新在前），需要正序时自行 reverse。

---

## 4. transcript — 字幕原始分段

**用途**：获取某讲次带时间戳的字幕分段数组。**CourseBookAgent 的核心数据源之一。**

### 命令

```bash
$PYTHON zju_zhiyun.py transcript --sub-id SUB_ID
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `--sub-id` | string | **是** | 讲次 ID |
| `--include-translation` | flag | 否 | 附带翻译文本 |
| `--raw` | flag | 否 | 附带原始接口 JSON |

### 输出字段

`data` 是 dict：

| 字段 | 类型 | 说明 |
|---|---|---|
| `sub_id` | string | 讲次 ID |
| `segments` | array | 字幕分段数组 |

每个 segment：

| 字段 | 类型 | 说明 |
|---|---|---|
| `start_sec` | int | 开始时间（秒） |
| `end_sec` | int | 结束时间（秒） |
| `text` | string | 字幕文本 |

### 测试结果

```json
// sub_id=1941530
{
  "sub_id": "1941530",
  "segments": [
    {"start_sec": 8, "end_sec": 22, "text": "是。"},
    {"start_sec": 22, "end_sec": 68, "text": "就是。"},
    {"start_sec": 73, "end_sec": 83, "text": "嗯，好的。"},
    // ... 共 767 段
    {"start_sec": 6291, "end_sec": 6404, "text": "嗯。"}
  ]
}
```

### ⚠️ 关键发现

- 一节课 **767 段**，总时长 **6404 秒（≈107 分钟）**。
- 大量短句（"是。""嗯。""就是。"），是口头语/低信息碎片，需要清洗。
- 时间戳以秒为单位，可用于和 PPT 的 `created_sec` 对齐。

---

## 5. subtitle — 字幕纯文本

**用途**：获取某讲次字幕的纯文本版本（已过滤口头语）。比 `transcript` 更适合直接送给 LLM。

### 命令

```bash
$PYTHON zju_zhiyun.py subtitle --sub-id SUB_ID
$PYTHON zju_zhiyun.py subtitle --sub-id SUB_ID --timestamps
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `--sub-id` | string | **是** | 讲次 ID |
| `--timestamps` | flag | 否 | 保留时间戳 |
| `--no-filter-fillers` | flag | 否 | 不过滤口头语 |

### 输出

- 文本 ≤ 800 字：直接在 `data.text` 返回。
- 文本 > 800 字：存文件，返回 `data.file`（路径）、`data.char_count`、`data.preview`。

---

## 6. lecture — 讲座纯文本（一键）

**用途**：一键获取某讲次的纯文本，比 `transcript` 更干净。**适合快速原型和 LLM 输入。**

### 命令

```bash
$PYTHON zju_zhiyun.py lecture --course "课程名称" [--index INDEX]
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `--course` | string | **是** | 课程名称 |
| `--teacher` | string | 否 | 教师姓名 |
| `--index` | int | 否 | 讲座索引，0=最新（默认 0） |
| `--timestamps` | flag | 否 | 保留时间戳 |
| `--no-filter-fillers` | flag | 否 | 不过滤口头语 |

### 输出字段

`data` 是 dict：

| 字段 | 类型 | 说明 |
|---|---|---|
| `course` | object | `{course_id, title, term}` |
| `video` | object | `{sub_id, sub_title, lecturer_name}` |
| `file` | string | 本地文件路径（长文本自动落盘） |
| `filename` | string | 文件名 |
| `char_count` | int | 文本字数 |
| `preview` | string | 前 300 字预览 |
| `text` | string/null | 短文本直接返回，长文本为 null |

### 测试结果

```json
{
  "course": {"course_id": 82493, "title": "实验设计与心理统计Ⅱ", "term": "2025-20262"},
  "video": {"sub_id": "1941530", "sub_title": "2026-06-16第1-2节", "lecturer_name": "沈模卫,董一胜"},
  "file": "~/.cielagent/skills/zju-scholar/output/lecture_1941530.txt",
  "filename": "lecture_1941530.txt",
  "char_count": 11279,
  "preview": "就是。好的。我也是。是假设检验的是一个加速..."
}
```

### ⚠️ 注意

- `lecture` 用 `--course` 名称 + `--index`，内部自动查 videos 获取 sub_id。
- 过滤后仍有口语痕迹，但比原始 transcript 干净很多。
- **CourseBookAgent 推荐用 `transcript`（保留时间戳用于对齐），再自己清洗；`lecture` 作为快速原型方案。**

---

## 7. ppt — PPT 时间轴

**用途**：获取某讲次的 PPT 幻灯片时间轴，含截图 URL。**CourseBookAgent 的另一个核心数据源。**

### 命令

```bash
$PYTHON zju_zhiyun.py ppt --course-id COURSE_ID --index 0
$PYTHON zju_zhiyun.py ppt --sub-id SUB_ID
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `--course-id` | int | 二选一 | 课程 ID |
| `--course` | string | 二选一 | 课程名称 |
| `--sub-id` | string | 或 | 指定讲次 ID |
| `--teacher` | string | 否 | 教师姓名 |
| `--index` | int | 否 | 视频索引，0=最新 |

### 输出字段

`data[]`，每个元素：

| 字段 | 类型 | 说明 |
|---|---|---|
| `course_id` | string | 课程 ID |
| `sub_id` | string | 讲次 ID |
| `slide_id` | string/null | 幻灯片 ID（实测为 null） |
| `created_sec` | int | **该页出现时间点（秒），用于和字幕对齐** |
| `image_url` | string | **PPT 截图 URL，可直接 HTTP GET 下载** |
| `title` | string | 幻灯片标题（**实测为空字符串**） |
| `raw` | object | 原始 API 返回 |

### 测试结果

```json
// course_id=82493, index=0, 共 81 页
[
  {
    "course_id": "82493",
    "sub_id": "1941530",
    "created_sec": 1,
    "image_url": "http://video.cmc.zju.edu.cn/ai3/ppt/20260616/.../1781567768000.jpg",
    "title": ""
  },
  {"created_sec": 7, "image_url": "..."},
  {"created_sec": 17, "image_url": "..."},
  // ... 共 81 页
]
```

### ⚠️ 关键发现

- 一节课 **81 张截图**，间隔约 6-10 秒。
- `title` 全是空——**不能靠 PPT 标题做章节切分，需要 OCR 或视觉识别**。
- `image_url` 可直接 HTTP GET 下载。
- `created_sec` 是对齐锚点：PPT 第 N 页在第 `created_sec` 秒出现，字幕 `start_sec` 在该时间附近的段落对应这页。

---

## 8. courseware-pdf — 课件 PDF 导出

**用途**：将 PPT 截图合并为 PDF。可导出单讲或全课。

### 命令

```bash
$PYTHON zju_zhiyun.py courseware-pdf --course-id COURSE_ID --all --output ./pdfs
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `--course-id` | int | 二选一 | 课程 ID |
| `--course` | string | 二选一 | 课程名称 |
| `--sub-id` | string | 否 | 指定讲次 |
| `--teacher` | string | 否 | 教师姓名 |
| `--index` | int | 否 | 视频索引 |
| `--all` | flag | 否 | 导出全部视频课件 |
| `--output` | string | 否 | 输出目录 |
| `--dedup` | flag | 否 | 感知哈希去重 |
| `--dedup-threshold` | int | 否 | 哈希距离阈值，默认 15 |

### 注意

- 需下载所有截图再合并，全课导出耗时较长。
- `--dedup` 可去除几乎相同的页面。

---

## 9. search — 全站搜索（旁路）

**用途**：搜索智云平台课程。旁路能力，结果可能为空。

```bash
$PYTHON zju_zhiyun.py search --keyword "人工智能" [--teacher "张三"]
```

---

## 10. CourseBookAgent 数据获取流程

```text
用户输入 学号 + 密码
    │
    ▼
POST /api/login
    → zju_login.py -u -p
    → session 就绪
    │
    ▼
GET /api/courses
    → zju_zhiyun.py my-courses
    → [{course_id, title, teacher}, ...]
    │
    ▼
用户选择 course_id
    │
    ▼
POST /api/generate  {course_id}
    │
    ├─ Step 1: zju_zhiyun.py videos --course-id {course_id}
    │   → [{sub_id, title}, ...]
    │
    ├─ Step 2: 对每个 sub_id:
    │   ├─ zju_zhiyun.py transcript --sub-id {sub_id}
    │   │   → segments[{start_sec, end_sec, text}]
    │   └─ zju_zhiyun.py ppt --sub-id {sub_id}
    │       → slides[{created_sec, image_url}]
    │
    ├─ Step 3: 对齐
    │   PPT created_sec ↔ transcript start_sec/end_sec
    │
    ├─ Step 4: 清洗字幕 + 结构化
    │
    └─ Step 5: LLM 生成讲义
```

---

## 11. 已知限制与风险

| 问题 | 详情 | 应对 |
|---|---|---|
| `/usr/bin/python3` 缺 pycryptodome | macOS 系统 Python 未安装 | 用 `/opt/homebrew/bin/python3` |
| Session 过期 | JWT / CAS token 会过期 | 调用前检查状态，过期重新登录 |
| 字幕质量 | ASR 有错字、断句乱 | 清洗后保留原文引用 |
| PPT title 为空 | 不能直接用标题做章节切分 | 需要 OCR 或视觉模型 |
| duration 为 0 | videos 接口不返回有效时长 | 用 transcript 最后 segment end_sec 推算 |
| has_transcript/has_ppt 为 null | 不能依赖 | 直接调用，失败则跳过 |
| 大文件 | lecture >800 字自动存文件 | 需读本地文件获取全文 |
| 多用户 session | data/session.json 单文件覆盖 | MVP 单用户可接受，后续隔离 |
| 密码明文存储 | credentials.json 明文 | MVP 可接受，产品化需加密 |
