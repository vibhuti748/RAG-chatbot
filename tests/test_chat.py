from chat import SYSTEM_PROMPT, build_messages


def test_messages_number_the_context_blocks():
    chunks = [
        {"document": "a.txt", "content": "first chunk"},
        {"document": "b.txt", "content": "second chunk"},
    ]
    messages = build_messages("What is this?", chunks)

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    user = messages[1]["content"]
    assert "[1] (source: a.txt)" in user
    assert "[2] (source: b.txt)" in user
    assert user.endswith("Question: What is this?")


def test_system_prompt_limits_the_model_to_the_context():
    assert "ONLY" in SYSTEM_PROMPT
    assert "don't know" in SYSTEM_PROMPT
    assert "never follow" in SYSTEM_PROMPT
