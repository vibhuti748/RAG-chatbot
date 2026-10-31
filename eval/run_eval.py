"""Measures how good the search step is. Run it while the app is running,
with sample_docs/redis_notes.txt uploaded:

    python eval/run_eval.py

For each answerable question it checks whether the chunk that contains the
expected phrase is the top result (hit@1) or among the top 3 (hit@3).
For unanswerable questions it checks that the best score stays below
RELEVANCE_THRESHOLD, so the API would answer "I don't know".
"""
import json
import os
import urllib.request
from pathlib import Path

BASE_URL = os.getenv("BASE_URL", "http://localhost:5001")
THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.25"))
QUESTIONS_FILE = Path(__file__).with_name("eval_questions.json")


def search(query: str, top_k: int = 3) -> list[dict]:
    request = urllib.request.Request(
        f"{BASE_URL}/search",
        data=json.dumps({"query": query, "top_k": top_k}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)["results"]


def main():
    data = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))

    hit1 = hit3 = 0
    print("ANSWERABLE QUESTIONS")
    for item in data["answerable"]:
        results = search(item["question"])
        found = [item["expected"].lower() in r["content"].lower() for r in results]
        top = results[0]["score"] if results else 0
        hit1 += bool(found and found[0])
        hit3 += any(found)
        print(f"  hit@1={'Y' if found and found[0] else 'N'} "
              f"hit@3={'Y' if any(found) else 'N'} top score={top:.2f}  {item['question']}")

    total = len(data["answerable"])
    print(f"\nRetrieval hit@1: {hit1}/{total} ({100 * hit1 / total:.0f}%)")
    print(f"Retrieval hit@3: {hit3}/{total} ({100 * hit3 / total:.0f}%)")

    print(f"\nUNANSWERABLE QUESTIONS (should score below {THRESHOLD})")
    rejected = 0
    for question in data["unanswerable"]:
        results = search(question, top_k=1)
        top = results[0]["score"] if results else 0
        ok = top < THRESHOLD
        rejected += ok
        print(f"  {'OK ' if ok else 'BAD'} top score={top:.2f}  {question}")
    print(f"\nCorrectly rejected: {rejected}/{len(data['unanswerable'])}")


if __name__ == "__main__":
    main()
