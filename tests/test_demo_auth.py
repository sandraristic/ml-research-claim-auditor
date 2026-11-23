"""Run: python -m unittest discover -s tests -p 'test_demo_auth.py' -v"""
import base64
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from claim_auditor.demo_auth import install_demo_auth


def make_app():
    app = FastAPI()

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/private")
    def private():
        return {"ok": True}

    install_demo_auth(app)
    return app


def header(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class DemoAuthTests(unittest.TestCase):
    def test_local_mode_does_not_require_auth(self):
        with patch.dict(os.environ, {"APP_ENV": "development"}):
            with TestClient(make_app()) as client:
                self.assertEqual(client.get("/api/v1/private").status_code, 200)

    def test_production_requires_secrets(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "DEMO_USERNAME": "", "DEMO_PASSWORD": ""}):
            with self.assertRaises(RuntimeError):
                make_app()

    def test_protected_routes_and_public_health(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "DEMO_USERNAME": "demo", "DEMO_PASSWORD": "secret"}):
            with TestClient(make_app()) as client:
                self.assertEqual(client.get("/api/v1/health").status_code, 200)
                unauthorized = client.get("/api/v1/private")
                self.assertEqual(unauthorized.status_code, 401)
                self.assertIn("Basic", unauthorized.headers["www-authenticate"])
                self.assertEqual(client.get("/api/v1/private", headers=header("demo", "bad")).status_code, 401)
                self.assertEqual(client.get("/api/v1/private", headers=header("demo", "secret")).status_code, 200)
                self.assertEqual(client.get("/docs").status_code, 401)


if __name__ == "__main__":
    unittest.main()
