import unittest

from fastapi.testclient import TestClient

from coursebook_agent.app import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.json()["llm_configured"])
        self.assertIn("zhiyun_live_configured", response.json())

    def test_unknown_job_is_404(self):
        response = self.client.get("/api/jobs/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_missing_book_is_404(self):
        response = self.client.get("/api/books/not-a-course")
        self.assertEqual(response.status_code, 404)

    def test_missing_v2_run_is_404(self):
        response = self.client.get("/api/runs/not-a-run/report")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
