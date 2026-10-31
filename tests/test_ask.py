import io

import redis

import app as app_module


def upload(client, name, content):
    return client.post(
        "/documents",
        data={"file": (io.BytesIO(content.encode()), name)},
        content_type="multipart/form-data",
    )


def ask(client, question, **extra):
    return client.post("/ask", json={"question": question, **extra})


def test_ask_returns_answer_with_sources(client, llm_calls):
    upload(client, "alphas.txt", "alpha " * 250)

    resp = ask(client, "alpha")
    body = resp.get_json()

    assert resp.status_code == 200
    assert body["answer"] == "Fake answer [1]"
    assert body["answered"] is True
    assert body["cached"] is False
    assert body["sources"][0]["document"] == "alphas.txt"
    assert body["sources"][0]["ref"] == 1
    assert len(llm_calls) == 1


def test_irrelevant_question_says_dont_know_without_calling_the_model(client, llm_calls):
    upload(client, "alphas.txt", "alpha " * 250)

    body = ask(client, "beta").get_json()  # nothing in the documents is about 'beta'

    assert body["answered"] is False
    assert body["sources"] == []
    assert "don't know" in body["answer"]
    assert llm_calls == []  # no AI call, so no cost


def test_no_documents_says_dont_know(client, llm_calls):
    body = ask(client, "alpha").get_json()
    assert body["answered"] is False
    assert llm_calls == []


def test_second_identical_question_is_served_from_cache(client, llm_calls):
    upload(client, "alphas.txt", "alpha " * 250)

    first = ask(client, "alpha").get_json()
    second = ask(client, "alpha").get_json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["answer"] == first["answer"]
    assert len(llm_calls) == 1


def test_uploading_a_document_invalidates_cached_answers(client, llm_calls):
    upload(client, "alphas.txt", "alpha " * 250)
    ask(client, "alpha")

    upload(client, "more.txt", "alpha " * 250)
    second = ask(client, "alpha").get_json()

    assert second["cached"] is False
    assert len(llm_calls) == 2


def test_empty_question_returns_400(client):
    assert ask(client, "   ").status_code == 400


def test_too_long_question_returns_400(client):
    assert ask(client, "a" * 501).status_code == 400


def test_invalid_top_k_returns_400(client):
    assert ask(client, "alpha", top_k=0).status_code == 400


def test_model_failure_returns_502(client, monkeypatch):
    upload(client, "alphas.txt", "alpha " * 250)

    def broken(_question, _chunks):
        raise RuntimeError("model down")

    monkeypatch.setattr(app_module, "generate_answer", broken)
    assert ask(client, "alpha").status_code == 502


def test_ask_is_rate_limited(client):
    for _ in range(10):
        assert ask(client, "alpha").status_code == 200

    resp = ask(client, "alpha")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_app_still_works_when_redis_is_down(client, monkeypatch, llm_calls):
    class BrokenRedis:
        def __getattr__(self, name):
            raise redis.exceptions.ConnectionError("redis is down")

    monkeypatch.setattr(app_module, "r", BrokenRedis())
    upload(client, "alphas.txt", "alpha " * 250)

    resp = ask(client, "alpha")
    assert resp.status_code == 200
    assert resp.get_json()["answered"] is True
