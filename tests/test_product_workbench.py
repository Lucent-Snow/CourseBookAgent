import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from coursebook_agent.app import app
from coursebook_agent.models import Course, Lecture, TranscriptSegment
from coursebook_agent.product.models import DatasetCreate, SnapshotCreate
from coursebook_agent.product.service import ProductService


class ProductServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = ProductService(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_upload_preview_and_snapshot(self):
        dataset = self.service.create_dataset(DatasetCreate(name="统计学资料"))
        resource = self.service.add_file(dataset.dataset_id, "notes.md", b"# Notes\nHypothesis testing")
        revision = resource.current_revision
        self.assertIsNotNone(revision)
        self.assertEqual(revision.parse_status, "ready")
        self.assertIn("Hypothesis", self.service.preview_revision(revision.revision_id).text)

        snapshot = self.service.create_snapshot(
            dataset.dataset_id,
            SnapshotCreate(resource_revision_ids=[revision.revision_id], label="First run"),
        )
        self.assertEqual(snapshot.resource_count, 1)
        self.assertEqual(snapshot.resource_revision_ids, [revision.revision_id])
        self.assertEqual(snapshot.sha256, self.service.get_snapshot(snapshot.snapshot_id).sha256)

    def test_snapshot_rejects_revision_from_another_dataset(self):
        first = self.service.create_dataset(DatasetCreate(name="First"))
        second = self.service.create_dataset(DatasetCreate(name="Second"))
        revision = self.service.add_file(first.dataset_id, "a.txt", b"a").current_revision
        with self.assertRaisesRegex(ValueError, "不属于"):
            self.service.create_snapshot(second.dataset_id, SnapshotCreate(resource_revision_ids=[revision.revision_id]))

    @patch("coursebook_agent.product.service.ZhiyunSource")
    def test_zhiyun_import_creates_one_resource_per_lecture(self, source_class):
        source = source_class.return_value
        source.get_course.return_value = Course(course_id="82493", name="应用统计学", teacher="张老师")
        source.list_lectures.return_value = [
            Lecture(lecture_id="l1", course_id="82493", title="第一讲", index=1, duration=120),
            Lecture(lecture_id="l2", course_id="82493", title="第二讲", index=2, duration=180),
        ]
        source.get_transcript.side_effect = lambda lecture: [
            TranscriptSegment(lecture_id=lecture.lecture_id, index=0, start_sec=0, end_sec=10, text="课程内容")
        ]
        dataset = self.service.create_dataset(DatasetCreate(name="统计学"))
        resources = self.service.import_zhiyun_course(dataset.dataset_id, "82493")
        self.assertEqual([item.title for item in resources], ["第一讲", "第二讲"])
        self.assertEqual(resources[0].current_revision.metadata["lecture_index"], 1)


class ProductApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch("coursebook_agent.product.api.service", return_value=ProductService(Path(self.temp.name)))
        self.patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_dataset_upload_flow(self):
        created = self.client.post("/api/product/datasets", json={"name": "课程资料"})
        self.assertEqual(created.status_code, 201)
        dataset_id = created.json()["dataset_id"]
        uploaded = self.client.post(
            f"/api/product/datasets/{dataset_id}/resources",
            files={"file": ("outline.txt", "course outline", "text/plain")},
        )
        self.assertEqual(uploaded.status_code, 201)
        revision_id = uploaded.json()["current_revision"]["revision_id"]
        snapshot = self.client.post(
            f"/api/product/datasets/{dataset_id}/snapshots",
            json={"resource_revision_ids": [revision_id], "label": "Run input"},
        )
        self.assertEqual(snapshot.status_code, 201)
        detail = self.client.get(f"/api/product/datasets/{dataset_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.json()["resources"]), 1)
        self.assertEqual(len(detail.json()["snapshots"]), 1)

    def test_workflow_preset_is_available(self):
        response = self.client.get("/api/product/workflow-presets")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["preset_id"], "coursebook")


if __name__ == "__main__":
    unittest.main()
