# RAG Document Q&A API

A backend API that answers questions about your own documents. You upload PDF or
text files, and the API finds the most relevant passages and asks an AI model to
answer using only those passages, with sources.

Built with Flask, PostgreSQL + pgvector, Redis, OpenAI, Docker, Pytest and
GitHub Actions.

**Live demo:** <add your URL here, if deployed>

## How it works

    Upload:  file -> extract text -> split into chunks -> embed each chunk -> store in PostgreSQL (pgvector)
    Ask:     question -> embed -> find closest chunks (vector search) -> AI model answers from them -> answer + sources

## Features
- PDF and text upload, word-based chunking with overlap
- Vector similarity search with pgvector (cosine distance)
- `/ask` returns answers with numbered source citations
- **"I don't know" behavior:** if no chunk is similar enough, the API says so without calling the AI model
- Redis answer cache, invalidated automatically when documents change
- Per-IP rate limiting on upload, search and ask (fails open if Redis is down)
- Prompt-injection hardening: the model is told to treat document text as data
- Embedding or model failures return clean errors and never leave half-saved data
- Retrieval evaluation script (hit@1 and hit@3)
- Docker Compose, tests that need no API key, and a CI/CD pipeline to AWS EC2

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/documents` | Upload a `.pdf` or `.txt` (form field `file`) |
| GET | `/documents` | List documents |
| GET | `/documents/<id>/chunks` | Preview stored chunks |
| DELETE | `/documents/<id>` | Delete a document and its chunks |
| POST | `/search` | `{"query": "...", "top_k": 3}` returns the closest chunks with scores |
| POST | `/ask` | `{"question": "...", "top_k": 4}` returns an answer with sources |
| GET | `/health` | Health check |

Example:

    curl -X POST localhost:5001/ask -H "Content-Type: application/json" -d '{"question": "What is cache-aside?"}'

## Run locally

1. Copy `.env.example` to `.env` and add your OpenAI API key.
2. Start everything: `docker compose up -d --build`
3. The API is at `http://localhost:5001`.

For development without the app container:

    docker compose up -d db redis
    python -m venv venv && venv\Scripts\activate
    pip install -r requirements-dev.txt
    python app.py

## Tests

    pip install -r requirements-dev.txt
    pytest -v

Tests use SQLite, a fake Redis and fake AI calls, so they are free and need no key.

## Evaluating retrieval quality

With the app running and `sample_docs/redis_notes.txt` uploaded:

    python eval/run_eval.py

| Setting | hit@1 | hit@3 | Unanswerable rejected |
|---------|-------|-------|-----------------------|
| chunk 200 words, overlap 40 | <fill in> | <fill in> | <fill in> |

## Configuration

See `.env.example`. Never commit `.env`.

## Possible improvements
- Hybrid search (keyword + vector) and re-ranking
- Streaming answers, conversation history
- Vector index (HNSW) for large collections
- Authentication and per-user documents
- HTTPS with Nginx
