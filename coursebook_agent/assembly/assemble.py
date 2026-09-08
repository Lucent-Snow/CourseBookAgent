"""Chapter-context assembler.

The BookPlan contains ``resource_tags`` (revision_id -> tag list).  This
module turns that into one ``ChapterContext`` per chapter.  Resources
with no tag are not used.  Resources tagged ``__global__`` are fed into
every chapter's global context.  Chapter tags pin a resource to specific
chapters' primary contexts.
"""

from __future__ import annotations

from coursebook_agent.models import (
    BookPlan,
    ChapterContext,
    Course,
    ParsedResource,
)


def _by_revision(parsed_resources: list[ParsedResource]) -> dict[str, ParsedResource]:
    return {r.revision_id: r for r in parsed_resources}


def assemble_chapter_contexts(
    plan: BookPlan,
    parsed_resources: list[ParsedResource],
    *,
    course: Course | None = None,
    snapshot_id: str | None = None,
) -> list[ChapterContext]:
    rev_index = _by_revision(parsed_resources)

    global_rev_ids = list(plan.global_resource_ids or [])
    global_resources: list[ParsedResource] = []
    for rev_id in global_rev_ids:
        parsed = rev_index.get(rev_id)
        if parsed is not None:
            global_resources.append(parsed)

    contexts: list[ChapterContext] = []
    for chapter in plan.chapters:
        chapter_res_ids = list(plan.chapter_resources.get(chapter.chapter_id) or [])
        chapter_resources: list[ParsedResource] = []
        for rev_id in chapter_res_ids:
            parsed = rev_index.get(rev_id)
            if parsed is not None:
                chapter_resources.append(parsed)
        contexts.append(ChapterContext(
            chapter=chapter,
            global_resources=list(global_resources),
            chapter_resources=chapter_resources,
            global_writing_prompt=plan.writer_system_prompt or "",
            component_specs=list(plan.components or []),
            course=course,
            snapshot_id=snapshot_id,
        ))
    return contexts