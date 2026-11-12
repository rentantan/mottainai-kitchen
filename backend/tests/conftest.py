import os
import sys
import tempfile
from pathlib import Path

import pytest

# Configure before the app modules are imported: config.py reads env vars at import time,
# and load_dotenv() never overrides variables that are already set.
_tmp = tempfile.mkdtemp(prefix="mottainai-test-")
os.environ["DATABASE_PATH"] = str(Path(_tmp) / "test.db")
os.environ["GEMINI_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import auth  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture
def client():
    auth._clear_login_failures()
    return TestClient(app)


@pytest.fixture
def make_user(client):
    counter = {"n": 0}

    def _make():
        counter["n"] += 1
        email = f"user{counter['n']}-{os.urandom(4).hex()}@example.com"
        response = client.post("/api/auth/register", json={"email": email, "password": "password123"})
        assert response.status_code == 200
        return email, {"Authorization": f"Bearer {response.json()['token']}"}

    return _make
