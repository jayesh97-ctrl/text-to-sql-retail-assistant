"""
llm.py
One small function that turns a question into model output. The provider is
isolated here so it can be swapped (another vendor, a local model) without
touching the rest of the project.

Setup: copy .env.example to .env and add your key. The key is never committed.
"""
import os

from dotenv import load_dotenv

from app.schema import SCHEMA_CONTEXT

load_dotenv()


def ask_model(question: str) -> str:
    """Send the schema context plus the question to the model, return its raw reply."""
    import anthropic  # imported here so tests and mock mode work without a key

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
    model = os.environ.get("ANTHROPIC_MODEL")
    if not model:
        raise RuntimeError("ANTHROPIC_MODEL is not set. See .env.example.")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=600,
        temperature=0,
        system=SCHEMA_CONTEXT,
        messages=[{"role": "user", "content": question}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
