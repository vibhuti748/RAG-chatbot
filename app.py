import hashlib
import io
import json
import math
import os
from datetime import datetime, timezone
from functools import wraps

import redis
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from pgvector.sqlalchemy import Vector
from pypdf import PdfReader
from sqlalchemy import JSON, func, text

load_dotenv()  # reads the .env file (your API key) into environment variables

from chat import generate_answer  # noqa: E402
from chunking import chunk_text  # noqa: E402
from embeddings import EMBEDDING_DIMENSIONS, embed_texts  # noqa: E402

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://rag:rag@localhost:5433/rag",
)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # reject uploads over 10 MB
db = SQLAlchemy(app)

r = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6380/0"),
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

# ---------- settings ----------
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.25"))
MAX_QUESTION_CHARS = 500
ANSWER_CACHE_SECONDS = 3600
RATE_WINDOW_SECONDS = 60
LIMITS = {  # requests allowed per minute per IP
    "ask": int(os.getenv("ASK_RATE_LIMIT", "10")),
    "search": int(os.getenv("SEARCH_RATE_LIMIT", "20")),
    "upload": int(os.getenv("UPLOAD_RATE_LIMIT", "10")),
}
NO_ANSWER = "I don't know based on the uploaded documents."


# ---------- database models ----------
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    chunks = db.relationship(
        "Chunk", backref="document", cascade="all, delete-orphan"
    )


class Chunk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    # pgvector column on PostgreSQL; a plain JSON list in the SQLite test database
    embedding = db.Column(Vector(EMBEDDING_DIMENSIONS).with_variant(JSON(), "sqlite"))


# ---------- Redis helpers (all of them fail open: if Redis is down, the app still works) ----------
def rate_limit_retry_after(bucket: str, limit: int):
    """Fixed-window rate limiter. Returns seconds to wait if over the limit, else None."""
    key = f"rl:{bucket}:{request.remote_addr}"
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, RATE_WINDOW_SECONDS)
        if count > limit:
            return max(r.ttl(key), 1)
    except redis.RedisError:
        app.logger.warning("Redis unavailable: rate limiting skipped")
    return None


def rate_limited(bucket: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            retry_after = rate_limit_retry_after(bucket, LIMITS[bucket])
            if retry_after is not None:
                resp = jsonify(error="Too many requests. Try again later.")
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry_after)
                return resp
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def corpus_version() -> str:
    """A counter that changes whenever documents change, so old cached answers stop matching."""
    try:
        return r.get("corpus_version") or "0"
    except redis.RedisError:
        return "0"


def bump_corpus_version():
    try:
        r.incr("corpus_version")
    except redis.RedisError:
        app.logger.warning("Redis unavailable: could not bump corpus version")


def cache_get(key: str):
    try:
        return r.get(key)
    except redis.RedisError:
        return None


def cache_set(key: str, value: str):
    try:
        r.setex(key, ANSWER_CACHE_SECONDS, value)
    except redis.RedisError:
        pass


# ---------- helpers ----------
def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    raise ValueError("Only .txt and .pdf files are supported")


def cosine_similarity(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def search_chunks(query_vector: list[float], top_k: int) -> list[dict]:
    """Return the top_k chunks closest in meaning to the query vector."""
    if db.engine.dialect.name == "postgresql":
        # <=> is pgvector's cosine distance operator (0 = identical meaning).
        # similarity = 1 - distance, so higher means a better match.
        rows = db.session.execute(
            text(
                """
                SELECT d.filename, c.chunk_index, c.content,
                       1 - (c.embedding <=> CAST(:q AS vector)) AS score
                FROM chunk c
                JOIN document d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> CAST(:q AS vector)
                LIMIT :k
                """
            ),
            {"q": str(query_vector), "k": top_k},
        ).all()
        return [
            {
                "document": row.filename,
                "chunk_index": row.chunk_index,
                "content": row.content,
                "score": round(float(row.score), 4),
            }
            for row in rows
        ]

    # Fallback used only by the SQLite test database (no pgvector there)
    scored = []
    for chunk in Chunk.query.filter(Chunk.embedding.isnot(None)).all():
        scored.append(
            {
                "document": chunk.document.filename,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "score": round(cosine_similarity(query_vector, chunk.embedding), 4),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def parse_top_k(body: dict, default: int):
    top_k = body.get("top_k", default)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 10:
        return None
    return top_k


# ---------- routes ----------
@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/documents")
@rate_limited("upload")
def upload_document():
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify(error="Send a file in the 'file' form field"), 400

    data = file.read()
    try:
        content = extract_text(file.filename, data)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        return jsonify(error="Could not read this file"), 400

    pieces = chunk_text(content)
    if not pieces:
        return jsonify(
            error="No text found in the file (scanned PDFs need OCR)"
        ), 400

    # Embed BEFORE saving anything, so a failure never leaves a half-saved document
    try:
        vectors = embed_texts(pieces)
    except Exception:
        app.logger.exception("Embedding request failed")
        return jsonify(error="Embedding service failed. Check your API key and credit."), 502

    doc = Document(filename=file.filename)
    db.session.add(doc)
    db.session.flush()  # gives doc an id before commit
    for i, (piece, vector) in enumerate(zip(pieces, vectors)):
        db.session.add(
            Chunk(document_id=doc.id, chunk_index=i, content=piece, embedding=vector)
        )
    db.session.commit()
    bump_corpus_version()  # cached answers may now be out of date

    return jsonify(id=doc.id, filename=doc.filename, num_chunks=len(pieces)), 201


@app.post("/search")
@rate_limited("search")
def search():
    body = request.get_json(silent=True) or {}
    query = str(body.get("query", "")).strip()
    if not query:
        return jsonify(error="Provide a non-empty 'query'"), 400

    top_k = parse_top_k(body, default=3)
    if top_k is None:
        return jsonify(error="'top_k' must be an integer from 1 to 10"), 400

    try:
        query_vector = embed_texts([query])[0]
    except Exception:
        app.logger.exception("Embedding request failed")
        return jsonify(error="Embedding service failed. Check your API key and credit."), 502

    return jsonify(query=query, results=search_chunks(query_vector, top_k))


@app.post("/ask")
@rate_limited("ask")
def ask():
    body = request.get_json(silent=True) or {}
    question = str(body.get("question", "")).strip()
    if not question:
        return jsonify(error="Provide a non-empty 'question'"), 400
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify(error=f"Question must be at most {MAX_QUESTION_CHARS} characters"), 400

    top_k = parse_top_k(body, default=4)
    if top_k is None:
        return jsonify(error="'top_k' must be an integer from 1 to 10"), 400

    # 1. Answer cache (the key changes whenever documents change)
    question_hash = hashlib.sha256(question.lower().encode()).hexdigest()
    cache_key = f"ask:{corpus_version()}:{top_k}:{question_hash}"
    cached = cache_get(cache_key)
    if cached:
        payload = json.loads(cached)
        payload["cached"] = True
        return jsonify(payload)

    # 2. Retrieve: find the chunks closest in meaning to the question
    try:
        query_vector = embed_texts([question])[0]
    except Exception:
        app.logger.exception("Embedding request failed")
        return jsonify(error="Embedding service failed. Check your API key and credit."), 502

    results = search_chunks(query_vector, top_k)
    relevant = [item for item in results if item["score"] >= RELEVANCE_THRESHOLD]

    # 3. Generate: if nothing is relevant, say so without calling the AI model
    if not relevant:
        payload = {"answer": NO_ANSWER, "answered": False, "sources": []}
    else:
        try:
            answer = generate_answer(question, relevant)
        except Exception:
            app.logger.exception("Chat request failed")
            return jsonify(error="Answer service failed. Check CHAT_MODEL, your API key and credit."), 502
        payload = {
            "answer": answer,
            "answered": True,
            "sources": [
                {
                    "ref": i,
                    "document": item["document"],
                    "chunk_index": item["chunk_index"],
                    "score": item["score"],
                    "content": item["content"][:300],
                }
                for i, item in enumerate(relevant, start=1)
            ],
        }

    cache_set(cache_key, json.dumps(payload))
    payload["cached"] = False
    return jsonify(payload)


@app.get("/documents")
def list_documents():
    rows = (
        db.session.query(Document, func.count(Chunk.id))
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .group_by(Document.id)
        .order_by(Document.id)
        .all()
    )
    return jsonify(
        [
            {
                "id": d.id,
                "filename": d.filename,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "num_chunks": n,
            }
            for d, n in rows
        ]
    )


@app.get("/documents/<int:doc_id>/chunks")
def get_chunks(doc_id):
    doc = db.session.get(Document, doc_id)
    if doc is None:
        return jsonify(error="Document not found"), 404

    limit = min(request.args.get("limit", default=5, type=int), 50)
    chunks = (
        Chunk.query.filter_by(document_id=doc_id)
        .order_by(Chunk.chunk_index)
        .limit(limit)
        .all()
    )
    return jsonify(
        document=doc.filename,
        chunks=[{"index": c.chunk_index, "content": c.content} for c in chunks],
    )


@app.delete("/documents/<int:doc_id>")
def delete_document(doc_id):
    doc = db.session.get(Document, doc_id)
    if doc is None:
        return jsonify(error="Document not found"), 404
    db.session.delete(doc)
    db.session.commit()
    bump_corpus_version()
    return "", 204


with app.app_context():
    if db.engine.dialect.name == "postgresql":
        db.session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.session.commit()
    db.create_all()
    if db.engine.dialect.name == "postgresql":
        # Older versions created the chunk table without this column; add it if missing
        db.session.execute(
            text(
                f"ALTER TABLE chunk ADD COLUMN IF NOT EXISTS "
                f"embedding vector({EMBEDDING_DIMENSIONS})"
            )
        )
        db.session.commit()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
