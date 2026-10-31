import io


def upload(client, name="notes.txt", content=None):
    if content is None:
        content = " ".join(f"word{i}" for i in range(250))
    return client.post(
        "/documents",
        data={"file": (io.BytesIO(content.encode()), name)},
        content_type="multipart/form-data",
    )


def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_upload_txt_creates_chunks(client):
    resp = upload(client)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["filename"] == "notes.txt"
    assert body["num_chunks"] == 2


def test_upload_without_file_returns_400(client):
    assert client.post("/documents").status_code == 400


def test_unsupported_file_type_returns_400(client):
    assert upload(client, name="notes.docx").status_code == 400


def test_empty_file_returns_400(client):
    assert upload(client, content="   ").status_code == 400


def test_list_documents(client):
    upload(client, name="a.txt")
    upload(client, name="b.txt")
    docs = client.get("/documents").get_json()
    assert [d["filename"] for d in docs] == ["a.txt", "b.txt"]
    assert docs[0]["num_chunks"] == 2


def test_get_chunks(client):
    doc_id = upload(client).get_json()["id"]
    resp = client.get(f"/documents/{doc_id}/chunks?limit=1")
    body = resp.get_json()
    assert resp.status_code == 200
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["index"] == 0


def test_chunks_for_unknown_document_returns_404(client):
    assert client.get("/documents/999/chunks").status_code == 404


def test_delete_document(client):
    doc_id = upload(client).get_json()["id"]
    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.get("/documents").get_json() == []
    assert client.delete(f"/documents/{doc_id}").status_code == 404
