# ADR-005: 智云课堂适配器必须随项目交付

## Status

Accepted

## Context

CourseBookAgent 曾通过 `ZJU_SKILL_DIR` 执行 `~/.cielagent/skills/zju-scholar/scripts/zju_zhiyun.py`。这使得项目运行依赖某台开发机器的 AI skill 安装路径、脚本版本和 session 数据，无法由仓库自身复现、部署或评审。

## Decision

- 将 CourseBookAgent 实际使用的智云 API 客户端、统一认证和 WebVPN helper vendor 到 `coursebook_agent/vendor/zhiyun/`。
- `coursebook_agent.sources.zhiyun.ZhiyunSource` 直接调用项目内 Python API，不再创建外部脚本子进程。
- 依赖通过 `pyproject.toml` / `uv.lock` 管理；WebVPN 所需的 `pycryptodome` 是正式依赖。
- 登录信息不进仓库：优先从 `ZHIYUN_JWT` 读取；可选的 `ZHIYUN_SESSION_FILE` 只读取 session JSON，不执行其所在目录的代码。
- `data/cache/zhiyun/` 仍是缓存优先的数据入口，因此离线演示和已缓存课程不需要登录凭证。
- 旧版 CLI 信封格式缓存继续兼容读取，避免使已有课程数据失效。

## Consequences

- 项目克隆后执行 `uv sync` 即拥有智云集成代码，不再需要安装 pi skill。
- 实时刷新课程需要使用者自行提供合法、授权的智云 JWT 或 session。
- 历史文档中的 `zju-scholar` CLI 命令只作为接口考古记录，不能视为当前运行依赖。
