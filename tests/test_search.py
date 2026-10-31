import io

import app as app_module


def upload(client, name, content):
    return client.post(
        "/documents",
        data={"file": (io.BytesIO(content.encode()), name)},
        content_type="multipart/form-data",
    )


def search(client, query, top_k=None):
    body = {"query": query}
    if top_k is not None:
        body["top_k"] = top_k
    return client.post("/search", json=body)


def test_search_returns_closest_document_first(client):
    upload(client, "alphas.txt", "alpha " * 250)
    upload(client, "betas.txt", "beta " * 250)

    resp = search(client, "alpha", top_k=2)
    results = resp.get_json()["results"]

    assert resp.status_code == 200
    assert results[0]["document"] == "alphas.txt"
    assert results[0]["score"] > results[1]["score"]


def test_search_respects_top_k(client):
    upload(client, "alphas.txt", "alpha " * 250)  # 2 chunks
    assert len(search(client, "alpha", top_k=1).get_json()["results"]) == 1


def test_search_with_no_documents_returns_empty_list(client):
    assert search(client, "alpha").get_json()["results"] == []


def test_empty_query_returns_400(client):
    assert search(client, "   ").status_code == 400


def test_invalid_top_k_returns_400(client):
    assert search(client, "alpha", top_k=50).status_code == 400


def test_embedding_failure_on_upload_returns_502_and_saves_nothing(client, monkeypatch):
    def broken(_texts):
        raise RuntimeError("API down")

    monkeypatch.setattr(app_module, "embed_texts", broken)

    assert upload(client, "a.txt", "alpha " * 50).status_code == 502
    assert client.get("/documents").get_json() == []


def test_embedding_failure_on_search_returns_502(client, monkeypatch):
    def broken(_texts):
        raise RuntimeError("API down")

    monkeypatch.setattr(app_module, "embed_texts", broken)
    assert search(client, "alpha").status_code == 502
