"""Developer CLI for inspecting generation quality."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from coursebook_agent.config import config
from coursebook_agent.pipeline import CourseBookPipeline
from coursebook_agent.renderer.markdown import render_chapter, render_coursebook


def main() -> None:
    parser = argparse.ArgumentParser(description="CourseBookAgent quality CLI")
    parser.add_argument("--course-id", default="82493")
    parser.add_argument("--lecture", type=int, default=None, help="1-based lecture index")
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("--plan-only", action="store_true", help="Only build/refresh the book plan")
    parser.add_argument("--refresh-plan", action="store_true")
    parser.add_argument("--review", action="store_true", help="Enable per-chapter review pass")
    parser.add_argument("--no-book-plan", action="store_true")
    parser.add_argument("--only", type=str, default="", help="Comma-separated lecture indices for partial course regen")
    parser.add_argument("--out", type=str, default="", help="Optional markdown output path")
    parser.add_argument("--v2-profile", type=str, default="", help="Run the versioned v2 workflow using this course profile JSON")
    parser.add_argument("--v2-pilot", type=str, default="", help="Comma-separated v2 pilot lecture indices (for example: 2,7,10,14)")
    args = parser.parse_args()

    if args.v2_profile:
        if not args.v2_pilot:
            parser.error("--v2-profile requires --v2-pilot; v2 currently runs an explicit pilot only")
        from coursebook_agent.v2 import V2Pipeline, load_profile
        profile = load_profile(args.v2_profile)
        indices = [int(value) for value in args.v2_pilot.split(",") if value.strip()]

        async def run_v2():
            report = await V2Pipeline(profile).generate_pilot(indices)
            print(json.dumps(report, ensure_ascii=False, indent=2))

        asyncio.run(run_v2())
        return

    pipeline = CourseBookPipeline()

    async def run():
        if args.plan_only:
            plan = await pipeline.ensure_book_plan(
                args.course_id,
                refresh=args.refresh_plan or args.regenerate,
            )
            print(plan.model_dump_json(indent=2))
            return
        if args.lecture is not None:
            if args.refresh_plan:
                await pipeline.ensure_book_plan(args.course_id, refresh=True)
            draft = await pipeline.generate_lecture(
                args.course_id,
                args.lecture,
                regenerate=args.regenerate,
                review=args.review,
                use_book_plan=not args.no_book_plan,
            )
            text = render_chapter(draft)
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
            print(text)
            return

        only_indices = [int(x) for x in args.only.split(",") if x.strip()] if args.only else None
        book = await pipeline.generate_course(
            args.course_id,
            regenerate=args.regenerate,
            review=args.review,
            use_book_plan=not args.no_book_plan,
            synthesize=True,
            only_indices=only_indices,
            progress=lambda done, total, message: print(f"[{done}/{total}] {message}", flush=True),
        )
        text = render_coursebook(book)
        out = Path(args.out) if args.out else config.output_dir / f"coursebook-{args.course_id}.md"
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out}")
        print(json.dumps({
            "title": book.title,
            "chapters": len(book.chapters),
            "glossary": len(book.glossary),
            "key_points": len(book.key_point_index),
            "warnings": book.warnings[:5],
            "quality_notes": book.quality_notes[:5],
        }, ensure_ascii=False, indent=2))

    asyncio.run(run())


if __name__ == "__main__":
    main()
