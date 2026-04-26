from __future__ import annotations

from typing import Any


def chat_completion_options(model: str, max_tokens: int, temperature: float = 0.1) -> dict[str, Any]:
    """Return Chat Completions options compatible with the configured model."""
    normalized = model.lower().strip()
    if _uses_completion_token_limit(normalized):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens, "temperature": temperature}


def _uses_completion_token_limit(model: str) -> bool:
    return model.startswith(("gpt-5", "o1", "o3", "o4"))
