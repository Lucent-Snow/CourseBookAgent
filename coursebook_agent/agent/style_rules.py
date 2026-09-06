"""Anti-AI-flavor style rules for Chinese teaching material writing.

Provides:
- inject_prompt_rules(): appends style constraints to a SYSTEM prompt
- check_content(): scans generated text for banned patterns
"""

from __future__ import annotations

import re


# ── Banned AI cliches (中文 AI 套话黑名单) ──────────────────────────────────

BANNED_TRANSITIONS = [
    r"首先让我们来了解", r"接下来我们将探讨", r"让我们先来了解",
    r"首先我们来了解一下", r"接下来让我们来看", r"下面我们来讨论",
    r"首先.*?了解", r"接下来.*?探讨",
    r"总而言之", r"综上所述", r"由此可见", r"不难发现",
    r"值得注意的是", r"需要强调的是", r"值得一提的是",
    r"通过以上分析", r"基于以上讨论",
]

BANNED_EMPTY = [
    r"本节将介绍", r"本部分将探讨", r"本节主要讲述",
    r"通过本文的学习", r"帮助读者理解", r"帮助同学们理解",
    r"本节内容.*?以下", r"本节主要.*?内容",
]

BANNED_FAKE_INTERACTION = [
    r"你是否想过", r"你有没有想过", r"让我们一起来看看",
    r"大家想一想", r"同学们可以思考一下.*?[？?]",
]

BANNED_MECHANICAL = [
    r"不仅.*?更是.*?的",
]

ALL_BANNED = BANNED_TRANSITIONS + BANNED_EMPTY + BANNED_FAKE_INTERACTION + BANNED_MECHANICAL


# ── Positive style rules ────────────────────────────────────────────────────

POSITIVE_RULES = """【文风要求（必须遵守）】
1. 直接进入主题，不要用"首先让我们来了解""接下来我们将探讨"等过渡句开头。
2. 用具体的知识内容、计算步骤、判定规则填充每个小节，禁止只写空洞的概述句（如"本节将介绍…""本节主要讨论…"）。
3. 方法步骤必须精确到"一个没上过这堂课的同学照着做能完成计算"的程度。
4. 术语首次出现时简要解释其含义，之后直接使用术语。
5. 像一本好的大学教辅那样写作：平实、精确、不啰嗦。让读者能照着步骤操作和理解。
6. 段落之间要有逻辑递进（为什么需要 → 原理 → 步骤 → 例子 → 注意什么），不能是孤立的知识点罗列。
7. 例题要展示完整解题过程，不能只说"老师用XX例子说明了YY"。"""


def inject_prompt_rules(system_prompt: str) -> str:
    """Append style rules to a SYSTEM prompt string."""
    if POSITIVE_RULES in system_prompt:
        return system_prompt
    return system_prompt + "\n\n" + POSITIVE_RULES


def check_content(text: str) -> list[str]:
    """Scan text for banned AI-cliche patterns. Returns list of issues found."""
    issues: list[str] = []
    for pattern in ALL_BANNED:
        matches = re.finditer(pattern, text)
        for m in matches:
            issues.append(f'AI套话：「{m.group()}」')
    return issues
