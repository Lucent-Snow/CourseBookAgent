# -*- coding: utf-8 -*-
"""把章节 warnings 按语义分类，用于质量报告的分层展示。"""

CATEGORY_LABELS = {
    "uncertainty": "不确定标注",
    "coverage": "覆盖缺口",
    "review": "审校意见",
    "structure": "结构问题",
    "process": "流程与降级",
    "other": "其它",
}

_ORDER = ["uncertainty", "coverage", "review", "structure", "process", "other"]


def categorize_warning(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("[不确定") or "不确定" in t[:14]:
        return "uncertainty"
    if t.startswith("可能遗漏必覆盖点"):
        return "coverage"
    if t.startswith("审校："):
        return "review"
    if t.startswith("自动审校超时") or t.startswith("LLM 不可用") or "确定性回退" in t:
        return "process"
    if any(k in t for k in ("章节无小节", "概念与正文薄弱", "缺少", "本章导读偏短", "小节", "引用")):
        return "structure"
    return "other"


def group_warnings(warnings: list[str], *, per_group: int = 8, total: int = 16) -> list[dict]:
    groups: dict[str, list[str]] = {}
    used = 0
    for w in warnings:
        if used >= total:
            break
        cat = categorize_warning(w)
        bucket = groups.setdefault(cat, [])
        if len(bucket) >= per_group:
            continue
        bucket.append(w)
        used += 1
    return [
        {"category": cat, "label": CATEGORY_LABELS[cat], "items": groups[cat]}
        for cat in _ORDER
        if cat in groups
    ]
