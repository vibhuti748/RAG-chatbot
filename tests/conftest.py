import os

# Use an in-memory SQLite database for tests, set BEFORE importing the app
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import fakeredis
import pytest

import app as app_module


def fake_embed(texts):
    """A tiny fake embedding: counts of 'alpha' and 'beta', plus a constant.
    No network call and no API cost in tests."""
    return [
        [float(t.lower().count("alpha")), float(t.lower().count("beta")), 1.0]
        for t in texts
    ]


@pytest.fixture(autouse=True)
def mock_embeddings(monkeypatch):
    monkeypatch.setattr(app_module, "embed_texts", fake_embed)


@pytest.fixture(autouse=True)
def llm_calls(monkeypatch):
    """Replaces the AI model with a fake and records every call made to it."""
    calls = []

    def fake_generate(question, chunks):
        calls.append((question, chunks))
        return "Fake answer [1]"

    monkeypatch.setattr(app_module, "generate_answer", fake_generate)
    return calls


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(app_module, "r", fake)
    yield fake
    fake.flushall()


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.app_context():
        app_module.db.drop_all()
        app_module.db.create_all()
    return app_module.app.test_client()
