# CourseBookAgent 前端

React + TypeScript + Vite + Tailwind CSS + shadcn/ui 的教辅书阅读器。

## 开发

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 代理到 127.0.0.1:8000
```

后端需先在项目根目录启动：

```bash
uv run uvicorn coursebook_agent.app:app --host 127.0.0.1 --port 8000
```

## 构建

```bash
npm run build      # 产物在 dist/
npm run lint       # oxlint
```

## 结构

```text
src/
├── api/client.ts            # 后端 JSON API 封装
├── types.ts                 # 与后端 pydantic 模型对应的 TS 类型
├── components/
│   ├── book/                # 书业务组件（BookReader/ChapterView/ComponentBlock）
│   └── ui/                  # shadcn/ui 组件
├── App.tsx                  # 主页面（登录/选课/生成/阅读）
└── main.tsx
```

## 组件映射

| 后端数据 | 前端组件 |
|---|---|
| worked_example / tip_box / warning / procedure / side_note | `ComponentBlock`（左色条 + Badge 区分） |
| 目录 / 章节导航 | `BookReader`（桌面 sidebar + 移动端 `Sheet`） |
| 生成进度 | `Progress` |
