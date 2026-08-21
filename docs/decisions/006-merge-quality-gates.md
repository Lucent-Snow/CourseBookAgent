# ADR-006: 合并质量门禁进主流程，移除 V2 试点

## Status

Accepted — `v2.py` 试点已删除，门禁核心抽到 `agent/quality.py`，`pipeline.py` 集成组件清理。

## Context

项目曾存在两套生成流程并存：

- `pipeline.py` 的 `CourseBookPipeline`：生产流程，app.py 的 `/api/generate` 使用，但生成产物有机器残留（Python dict 例子、steps 数组被 `str()` 化）。
- `v2.py` 的 `V2Pipeline`：质量门禁试点，只有 `generate_pilot`（跑 4 讲），独立于生产，造成"V1/V2"命名分裂和代码冗余。

两套并存让新功能的落地位置含糊，也让"更好的结果"缺少单一迭代基线。

## Decision

1. **门禁核心抽到 `agent/quality.py`**：`CourseProfile`、`normalize_chunks`、`enforce_component_contract`、`sanitize_examples`、`deterministic_quality_gate`、`llm_quality_gate` 等，作为可复用库。
2. **删除 `v2.py`**：试点类 `V2Pipeline` 不再保留；其修订循环逻辑后续在 `pipeline.generate_lecture` 内以 `review` 参数重新落地。
3. **`pipeline.py` 集成基础清理**：`generate_lecture` 在写盘前统一执行 `sanitize_examples(enforce_component_contract(draft))`。
4. **前端兜底清理**：`frontend/src/lib/sanitize.ts` 清理历史缓存里的机器残留，保证展示层干净。
5. **数据保留作反面案例**：`data/` 里的旧产物（V1 成书、V2 runs）不删除，用于对照旧 prompt 与生成结果迭代。

## Consequences

- 生产流程唯一，质量门禁成为"更好的结果"的单一迭代点。
- 删除试点后，`--v2-profile`/`--v2-pilot` CLI 参数移除；`/api/runs` 仍读旧 run 数据用于质量报告页展示。
- 全量质量门禁（确定性 + LLM 审校 + 修订循环）尚未接回 `pipeline`，是下一迭代目标（对应 ISSUES B5）。
