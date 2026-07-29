#!/usr/bin/env python3
"""Overnight book-quality regeneration runner.

Runs lecture-by-lecture with retries, skips already-V2 chapters unless forced,
then synthesizes the whole coursebook.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import traceback
from datetime import datetime
from pathlib import Path

from coursebook_agent.config import config
from coursebook_agent.models import LectureDraft
from coursebook_agent.pipeline import CourseBookPipeline
from coursebook_agent.renderer.markdown import render_chapter, render_coursebook


def is_v2(draft: LectureDraft) -> bool:
    return bool(draft.bridge_from_prev or draft.key_points or draft.learning_goals)


async def generate_one(pipeline: CourseBookPipeline, course_id: str, index: int, *, review: bool, force: bool, plan) -> dict:
    lectures = await asyncio.to_thread(pipeline.source.list_lectures, course_id, False)
    lecture = lectures[index - 1]
    path = pipeline.intermediate_dir / f"chapter-{lecture.lecture_id}.json"
    if path.exists() and not force:
        draft = LectureDraft.model_validate_json(path.read_text(encoding="utf-8"))
        if is_v2(draft):
            return {"index": index, "status": "skip_v2", "title": draft.title, "lecture_id": lecture.lecture_id}

    previous = None
    if index > 1:
        prev = lectures[index - 2]
        prev_path = pipeline.intermediate_dir / f"chapter-{prev.lecture_id}.json"
        if prev_path.exists():
            previous = LectureDraft.model_validate_json(prev_path.read_text(encoding="utf-8"))

    last_error = None
    for attempt in range(1, 4):
        try:
            draft = await pipeline.generate_lecture(
                course_id,
                index,
                regenerate=True,
                review=review,
                use_book_plan=True,
                previous_draft=previous,
                plan=plan,
            )
            md = render_chapter(draft)
            (config.output_dir / f"lecture-{index:02d}-{lecture.lecture_id}.md").write_text(md, encoding="utf-8")
            return {
                "index": index,
                "status": "ok",
                "attempt": attempt,
                "title": draft.title,
                "lecture_id": lecture.lecture_id,
                "v2": is_v2(draft),
                "sections": len(draft.sections),
                "key_points": len(draft.key_points),
            }
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(3 * attempt)
    return {
        "index": index,
        "status": "failed",
        "lecture_id": lecture.lecture_id,
        "error": str(last_error),
        "trace": traceback.format_exc()[-2000:],
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-id", default="82493")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=14)
    parser.add_argument("--force", action="store_true", help="Regenerate even if chapter already V2")
    parser.add_argument("--review", action="store_true", default=True)
    parser.add_argument("--no-review", action="store_true")
    parser.add_argument("--synthesize", action="store_true", default=True)
    parser.add_argument("--no-synthesize", action="store_true")
    parser.add_argument("--only", default="", help="Comma indices, overrides start/end")
    args = parser.parse_args()

    review = False if args.no_review else True
    synthesize = False if args.no_synthesize else True
    if args.only:
        indices = [int(x) for x in args.only.split(",") if x.strip()]
    else:
        indices = list(range(args.start, args.end + 1))

    exp_dir = config.data_dir / "experiments" / "overnight"
    exp_dir.mkdir(parents=True, exist_ok=True)
    log_path = exp_dir / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"

    pipeline = CourseBookPipeline()
    print(f"[start] course={args.course_id} indices={indices} review={review}", flush=True)
    plan = await pipeline.ensure_book_plan(args.course_id, refresh=False)
    print(f"[plan] {plan.book_title} chapters={len(plan.chapters)}", flush=True)

    results = []
    for index in indices:
        print(f"[chapter {index}] generating...", flush=True)
        result = await generate_one(pipeline, args.course_id, index, review=review, force=args.force, plan=plan)
        results.append(result)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(f"[chapter {index}] {result['status']} {result.get('title') or result.get('error')}", flush=True)

    summary = {
        "course_id": args.course_id,
        "indices": indices,
        "results": results,
        "ok": sum(1 for r in results if r["status"] in {"ok", "skip_v2"}),
        "failed": [r for r in results if r["status"] == "failed"],
    }

    if synthesize:
        print("[synthesize] building coursebook...", flush=True)
        try:
            book = await pipeline.generate_course(
                args.course_id,
                regenerate=False,
                review=False,
                use_book_plan=True,
                synthesize=True,
                only_indices=[],  # load all cached chapters
                progress=lambda done, total, message: print(f"[synth {done}/{total}] {message}", flush=True),
            )
            # only_indices=[] means selected empty set -> all skipped to cache path. Good.
            out_md = config.output_dir / f"coursebook-{args.course_id}.md"
            out_md.write_text(render_coursebook(book), encoding="utf-8")
            (exp_dir / f"coursebook-{args.course_id}.md").write_text(render_coursebook(book), encoding="utf-8")
            summary["book_title"] = book.title
            summary["glossary"] = len(book.glossary)
            summary["key_point_index"] = len(book.key_point_index)
            summary["book_warnings"] = book.warnings[:10]
            summary["quality_notes"] = book.quality_notes[:10]
            summary["synthesize"] = "ok"
        except Exception as exc:
            summary["synthesize"] = f"failed: {exc}"
            summary["synthesize_trace"] = traceback.format_exc()[-2000:]
            print(f"[synthesize] failed: {exc}", flush=True)

    summary_path = exp_dir / "latest-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "results"}, ensure_ascii=False, indent=2), flush=True)
    print(f"[done] log={log_path} summary={summary_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
