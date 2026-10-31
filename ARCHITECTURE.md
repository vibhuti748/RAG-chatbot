# Architecture guide (read this to understand every file)

## The one-minute picture

1. **Upload a document.** The app reads the text and cuts it into small overlapping pieces called *chunks*.
2. Each chunk is sent to an *embedding model*, which returns a long list of numbers (a *vector*) that captures the chunk's meaning. Chunks about similar things get similar numbers.
3. Chunks and vectors are stored in PostgreSQL. The **pgvector** extension lets PostgreSQL compare vectors.
4. **Ask a question.** The question is turned into a vector the same way. PostgreSQL finds the chunks whose vectors are closest (vector search).
5. Those chunks are put into a prompt, and the AI model writes an answer using only them, citing sources like [1].

This pattern is called **RAG** (Retrieval-Augmented Generation): first retrieve, then generate.

## What each file does

| File | Plain-language role |
|------|---------------------|
| `app.py` | The main program: all the API endpoints, the database tables, caching and rate limiting. |
| `chunking.py` | Cuts text into ~200-word pieces with a 40-word overlap, so a sentence on a boundary is not lost. |
| `embeddings.py` | Talks to OpenAI to turn text into vectors. |
| `chat.py` | Builds the prompt (context plus question) and asks the AI model for an answer. |
| `requirements.txt` | Python packages the app needs. |
| `requirements-dev.txt` | The same plus testing tools. |
| `.env.example` | Template for your secrets and settings. You copy it to `.env`. |
| `Dockerfile` | Recipe to package the app into a container. |
| `docker-compose.yml` | Starts the app, PostgreSQL (with pgvector) and Redis together. |
| `.dockerignore`, `.gitignore` | Lists of files to leave out of the container image and out of Git (for example `.env`). |
| `tests/conftest.py` | Test setup: fake database, fake Redis and fake AI, so tests are free and fast. |
| `tests/test_api.py` | Tests upload, listing, chunks and delete. |
| `tests/test_search.py` | Tests vector search and embedding failures. |
| `tests/test_ask.py` | Tests answers, "I don't know", caching, rate limiting and Redis-down behavior. |
| `tests/test_chat.py` | Tests the prompt that is sent to the model. |
| `pytest.ini` | Tells pytest where the tests are. |
| `eval/run_eval.py` and `eval/eval_questions.json` | Measures how often search finds the right chunk. |
| `postman/` | A Postman collection to try every endpoint. |
| `README.md`, `DEPLOYMENT.md` | Project front page, and optional AWS deployment steps. |

## What happens during `POST /ask` (inside `app.py`)

1. **Rate limit check** (Redis): more than 10 asks per minute from one IP gets a 429.
2. **Validate** the question (not empty, under 500 characters).
3. **Cache lookup** (Redis): the key includes a "corpus version" counter. Uploading or deleting a document bumps the counter, so old cached answers stop matching.
4. **Embed the question** (OpenAI) and **search** the closest chunks (PostgreSQL, `<=>` operator).
5. **Relevance filter:** chunks scoring below `RELEVANCE_THRESHOLD` are dropped. If none remain, the API answers "I don't know" without calling the AI model, which saves cost and avoids made-up answers.
6. **Generate** the answer with the remaining chunks (`chat.py`).
7. **Cache and return** the answer with its sources.

## Design decisions (good interview material)

- **Why pgvector instead of a separate vector database?** One database to run, back up and query. It is plenty for a small project.
- **Why chunk overlap?** Without overlap, an answer that spans a chunk boundary could be split and lost.
- **Why a relevance threshold?** It reduces hallucination: no relevant context, no answer. Tune it with `eval/run_eval.py`.
- **Why embed before saving?** If the embedding call fails, nothing is half-saved.
- **Why does the cache key include a corpus version?** So a new document never leaves stale answers in the cache.
- **Why do the Redis helpers "fail open"?** Cache and rate limiting are helpers. A Redis outage should not take down the whole API.
- **How is prompt injection handled?** The system prompt tells the model to treat document text as untrusted data. This reduces the risk but is not a complete defense.
- **How is cost controlled?** Rate limits, a short question limit, caching, and skipping the model call when nothing is relevant.

## Things to know about the limits

- Scanned PDFs have no text to extract (they would need OCR).
- Chunking is by words, not by sentences or sections.
- Search is vector-only. Hybrid keyword + vector search would help for exact terms such as IDs.
- If you change the embedding model, the vector size changes (`EMBEDDING_DIMENSIONS` in `embeddings.py`) and you must re-embed your documents.
