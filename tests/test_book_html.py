"""Published book HTML: template embedding and video node index."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coursebook_agent.config import config
from coursebook_agent.models import (
    ChapterSection,
    Course,
    CourseBook,
    LectureDraft,
    ParsedResource,
)
from coursebook_agent.renderer.book_html import (
    render_coursebook_html,
    replay_page_url,
    resolve_video_index,
)


def _chapter(title: str, lecture_id: str, time_links: list[str]) -> LectureDraft:
    return LectureDraft(
        chapter_id=lecture_id or title,
        lecture_id=lecture_id,
        title=title,
        overview="本章导读示例。",
        sections=[ChapterSection(heading="核心内容", content="正文内容。", time_links=time_links)],
        summary=["小结要点"],
    )


def _book() -> CourseBook:
    return CourseBook(
        course=Course(course_id="84429", name="示例课程"),
        title="示例教辅",
        chapters=[
            _chapter("第 1 讲：示例导论", "1921621", ["01:09:01-01:12:28"]),
            _chapter("第 2 讲：示例进阶", "1923497", ["32:42-37:20"]),
        ],
    )


class ReplayUrlTests(unittest.TestCase):
    def test_replay_url_matches_zhiyun_route(self):
        url = replay_page_url("84429", "1929565")
        self.assertEqual(
            url,
            "https://interactivemeta.cmc.zju.edu.cn/#/replay"
            "?course_id=84429&sub_id=1929565&tenant_code=112",
        )


class VideoIndexTests(unittest.TestCase):
    def test_index_uses_resource_metadata(self):
        book = _book()
        resources = [
            ParsedResource(
                revision_id="zhiyun-transcript-1921621",
                resource_id="zhiyun-lecture-1921621",
                kind="transcript",
                source_type="zhiyun",
                provider="zhiyun",
                title="2026-04-30第11-13节",
                meta={
                    "lecture_id": "1921621",
                    "video_url": "https://resource.example/1.mp4",
                    "replay_url": replay_page_url("84429", "1921621"),
                },
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(config, "data_dir", Path(tmp)):
                index = resolve_video_index(book, resources)
        self.assertEqual(
            index["第 1 讲：示例导论"]["file"], "https://resource.example/1.mp4"
        )
        self.assertIn("sub_id=1921621", index["第 1 讲：示例导论"]["link"])
        # chapters without video metadata are simply left unlinked
        self.assertNotIn("第 2 讲：示例进阶", index)


class RenderTests(unittest.TestCase):
    def test_render_embeds_markdown_and_video_maps(self):
        book = _book()
        book.render_config = {
            "video_index": {
                "第 1 讲：示例导论": {
                    "file": "https://resource.example/1.mp4",
                    "link": replay_page_url("84429", "1921621"),
                }
            }
        }
        html = render_coursebook_html(book)
        self.assertIn("<title>示例教辅</title>", html)
        self.assertIn("第 1 讲：示例导论", html)
        self.assertIn("字幕时间段：01:09:01", html)
        self.assertIn("https://resource.example/1.mp4", html)
        self.assertIn("sub_id=1921621", html)
        self.assertIn("marked", html)
        self.assertIn("openVideoNode", html)
        # Markdown lives in an inert script block, never as raw HTML markup.
        self.assertNotIn("</script>\n# ", html)

    def test_render_without_index_still_produces_book(self):
        html = render_coursebook_html(_book())
        self.assertIn("BOOK_VIDEO_FILES", html)
        self.assertIn("BOOK_VIDEO_LINKS", html)
        self.assertIn("第 2 讲：示例进阶", html)


if __name__ == "__main__":
    unittest.main()
