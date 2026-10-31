import pytest

from chunking import chunk_text


def words(n):
    return " ".join(f"w{i}" for i in range(n))


def test_empty_text_gives_no_chunks():
    assert chunk_text("   \n  ") == []


def test_short_text_is_one_chunk():
    assert len(chunk_text(words(50))) == 1


def test_exact_chunk_size_is_one_chunk():
    assert len(chunk_text(words(200))) == 1


def test_long_text_is_split_with_overlap():
    chunks = chunk_text(words(250), chunk_size=200, overlap=40)
    assert len(chunks) == 2
    first, second = chunks[0].split(), chunks[1].split()
    assert len(first) == 200
    assert first[-40:] == second[:40]  # the overlap


def test_all_words_are_covered():
    chunks = chunk_text(words(1000))
    assert chunks[0].split()[0] == "w0"
    assert chunks[-1].split()[-1] == "w999"


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=10, overlap=10)
