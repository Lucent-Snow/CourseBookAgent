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

    def test_zhiyun_login_rejects_blank_credentials(self):
        response = self.client.post("/api/zhiyun/login", json={"username": "", "password": ""})
        self.assertEqual(response.status_code, 401)
        self.assertIn("请输入学号和密码", response.json()["detail"])

    def test_settings_returns_config(self):
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("llm", body)
        self.assertIn("zhiyun", body)
        self.assertIn("data", body)
        self.assertIn("api_key_set", body["llm"])

    def test_list_runs(self):
        response = self.client.get("/api/runs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("data", response.json())

    def test_llm_settings_rejects_blank(self):
        response = self.client.put("/api/settings/llm", json={"base_url": "", "model": ""})
        self.assertEqual(response.status_code, 400)

    def test_confirm_missing_run_is_404(self):
        response = self.client.post("/api/runs/does-not-exist/chapters/1/confirm", json={"note": ""})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
