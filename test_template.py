#!/usr/bin/env python3
"""快速测试：不依赖智云，用模拟字幕验证模板注入和质量门禁。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

# 确保能找到项目
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from coursebook_agent.models import (
    Lecture, TimedChunk, BookPlan, ChapterInstruction, ComponentSpec,
    ChapterSection, LectureDraft, Course
)
from coursebook_agent.agent.chapter import generate_chapter
from coursebook_agent.agent.llm import LLMClient
from coursebook_agent.agent.quality import (
    load_profile,
    enforce_component_contract,
    sanitize_examples,
    deterministic_quality_gate,
    llm_quality_gate,
)


# ── 模拟数据 ────────────────────────────────────────────────────────────────

def make_chunks() -> list[TimedChunk]:
    """生成模拟字幕 chunks（假设检验入门内容）。"""
    texts = [
        "大家好，今天我们开始学习假设检验。假设检验是统计推断的核心方法之一。",
        "我们先来看一个例子。某学校说学生平均智商是100，我们抽了30个学生，测出来平均是105。能不能说这个学校的说法是对的？",
        "假设检验的基本思想是反证法。我们先假设学校的说法是对的，也就是总体均值等于100，这叫虚无假设H0。",
        "然后我们看在H0为真的条件下，得到105这个样本平均数的概率有多大。如果概率很小，比如小于0.05，我们就有理由拒绝H0。",
        "拒绝H0之后我们得到什么结论？我们说数据为研究假设提供了支持。注意，不是证明研究假设成立，而是提供支持。",
        "这里有两个重要的错误类型。第一类错误是H0为真但我们拒绝了它，叫α错误。第二类错误是H1为真但我们没有拒绝H0，叫β错误。",
        "α错误和β错误不是简单的相加关系，它们是基于两个不同分布的。当你把判定标准往一个方向移动，一个增大另一个就会减小。",
        "统计检验力等于1减β，就是当H1为真时我们能正确拒绝H0的概率。",
        "现在我们来做一道题。已知总体正态，标准差是15，样本量40，样本均值105，总体均值100。请做双侧检验，显著性水平0.05。",
        "第一步，建立假设。H0：μ等于100，H1：μ不等于100。第二步，计算标准误，SE等于15除以根号40，约等于2.37。",
        "第三步，计算z统计量，z等于105减100除以2.37，约等于2.11。第四步，查临界值，双侧0.05的临界值是正负1.96。",
        "因为2.11大于1.96，落在拒绝域，所以我们拒绝H0。结论是：该样本平均数与总体均值100存在显著差异。",
        "最后提醒大家，统计结论只能说差异显著或不显著，写科学结论时要结合实际情况说明含义。",
    ]
    chunks = []
    current_sec = 0
    for i, text in enumerate(texts):
        chunks.append(TimedChunk(
            chunk_id=f"c{i+1:03d}",
            lecture_id="test-lecture",
            start_sec=current_sec,
            end_sec=current_sec + 60 + i * 10,
            text=text,
            source_segment_indices=[i],
        ))
        current_sec += 90
    return chunks


def make_instruction() -> ChapterInstruction:
    return ChapterInstruction(
        lecture_id="test-lecture",
        index=1,
        book_title="第 1 讲：假设检验原理",
        module_name="假设检验主线",
        chapter_role="core",
        narrative_purpose="引入假设检验的基本思想和操作步骤",
        learning_goals=["能复述反证法逻辑", "能区分α和β错误", "能完成平均数显著性检验"],
        must_cover=["反证法与H0/H1", "两类错误", "z检验步骤", "统计结论与科学结论的区分"],
        prerequisite_concepts=["正态分布", "标准误"],
        bridge_from_prev="",
        bridge_to_next="下一章进入平均数差异的检验",
        canonical_terms=["虚无假设", "研究假设", "α错误", "β错误"],
        common_mistakes=["把未拒绝H0说成证明H0正确", "误以为α+β=1"],
        section_plan=["假设检验的基本原理", "两类错误", "平均数显著性检验"],
        component_usage=["用procedure展示检验步骤", "用worked_example展示例题", "用warning标注易错点"],
        depth_guidance="需要逐步演示计算过程",
    )


def make_plan() -> BookPlan:
    return BookPlan(
        course_id="test",
        book_title="测试教辅",
        writer_system_prompt="你是教辅书分章写作者。只用给定材料，不编造。术语统一。核心方法章要写清步骤和判定。每个例题标注来源。",
        components=[
            ComponentSpec(name="worked_example", description="课堂例题", fields=["title", "problem", "steps", "conclusion", "source_ref"], usage_instruction="每章至少1个"),
            ComponentSpec(name="tip_box", description="小贴士", fields=["title", "body"], usage_instruction="每章1-3个"),
            ComponentSpec(name="warning", description="易错警告", fields=["title", "body"], usage_instruction="每章2-4个"),
            ComponentSpec(name="procedure", description="步骤流程", fields=["title", "steps", "when_to_use"], usage_instruction="核心方法章必须有"),
        ],
        chapters=[make_instruction()],
    )


def make_profile():
    profile_path = Path(__file__).parent / "coursebook_agent" / "profiles" / "82493-v2.json"
    if profile_path.exists():
        return load_profile(profile_path)
    return None


# ── 主流程 ──────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("模板+质量门禁 快速测试")
    print("=" * 60)

    chunks = make_chunks()
    instruction = make_instruction()
    plan = make_plan()
    profile = make_profile()

    lecture = Lecture(
        lecture_id="test-lecture",
        course_id="test",
        title="假设检验原理",
        index=1,
    )

    # 从 profile 提取骨架模板
    skeleton = ""
    if profile and instruction:
        role = instruction.chapter_role or "core"
        tmpl = profile.chapter_templates.get(role) or profile.chapter_templates.get("core") or {}
        skeleton = str(tmpl.get("skeleton", ""))
        print(f"\n[模板] 章节角色: {role}")
        print(f"[模板] 骨架长度: {len(skeleton)} 字")
    else:
        print("\n[警告] 未加载 profile，将不使用模板")

    print("\n[生成] 正在调用 LLM 生成章节...\n")

    draft = await generate_chapter(
        lecture,
        chunks,
        client=LLMClient(max_retries=2, timeout=120),
        review=True,
        instruction=instruction,
        plan=plan,
        template_skeleton=skeleton,
    )

    # 质量门禁
    print("\n" + "=" * 60)
    print("质量门禁检查")
    print("=" * 60)

    # 第一层：组件契约 + 例子清理
    draft = sanitize_examples(enforce_component_contract(draft))

    # 第二层：确定性检查
    if profile:
        det = deterministic_quality_gate(draft, instruction, profile, chunks)
        print(f"\n[确定性门禁] {'通过' if det.accepted else '未通过'}")
        if det.issues:
            for issue in det.issues:
                print(f"  ⚠ {issue}")
        print(f"  指标: {det.metrics}")

    # 第三层：LLM 审校
    if profile:
        llm = await llm_quality_gate(draft, instruction, profile, chunks)
        print(f"\n[LLM 审校] {'通过' if llm.accepted else '未通过'}")
        if llm.issues:
            for issue in llm.issues[:5]:
                print(f"  ⚠ {issue}")

    # 输出
    from coursebook_agent.renderer.markdown import render_chapter
    md = render_chapter(draft)

    out_path = Path(__file__).parent / "test_output.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"\n[输出] 已写入 test_output.md")
    print(f"\n[统计] 小节数={len(draft.sections)}, 字数={sum(len(s.content) for s in draft.sections)}, 组件数={sum(len(s.components) for s in draft.sections)}, warnings={len(draft.warnings)}")


if __name__ == "__main__":
    asyncio.run(main())
