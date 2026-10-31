def chunk_text(text: str, chunk_size: int = 200, overlap: int = 40) -> list[str]:
    """Split text into overlapping chunks of about `chunk_size` words.

    The overlap keeps a sentence that falls on a chunk boundary readable
    in at least one of the two chunks.
    """
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be larger than overlap")

    words = text.split()
    if not words:
        return []

    step = chunk_size - overlap
    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start:start + chunk_size]))
        if start + chunk_size >= len(words):
            break  # the last chunk already reaches the end of the text
    return chunks
