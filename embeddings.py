import os

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = 1536  # the size of text-embedding-3-small vectors
BATCH_SIZE = 100

_client = None


def get_client():
    """Create the OpenAI client on first use (it reads OPENAI_API_KEY)."""
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI()
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Turn each text into a list of numbers that captures its meaning."""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        response = get_client().embeddings.create(model=EMBEDDING_MODEL, input=batch)
        vectors.extend(item.embedding for item in response.data)
    return vectors
