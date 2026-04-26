from __future__ import annotations

from contextvars import ContextVar
from typing import Literal

from app.core.config import Settings


ModelMode = Literal["quality", "fast"]

MODEL_MODE_TO_MODEL: dict[ModelMode, str] = {
    "quality": "gpt-5.5",
    "fast": "gpt-5.4-mini",
}

_model_mode: ContextVar[ModelMode | None] = ContextVar("openai_model_mode", default=None)


def normalize_model_mode(value: str | None) -> ModelMode:
    normalized = (value or "quality").strip().lower().replace("_", "-")
    if normalized in {"fast", "mini", "5.4-mini", "gpt-5.4-mini"}:
        return "fast"
    return "quality"


def set_model_mode(value: str | None):
    return _model_mode.set(normalize_model_mode(value))


def reset_model_mode(token) -> None:
    _model_mode.reset(token)


def current_model_mode() -> ModelMode:
    return _model_mode.get() or "quality"


def current_openai_model(settings: Settings) -> str:
    mode = _model_mode.get()
    if mode is None:
        return settings.openai_model
    return MODEL_MODE_TO_MODEL[mode]


def openai_model_candidates(settings: Settings) -> list[str]:
    preferred = current_openai_model(settings)
    fallback = settings.openai_model
    return [preferred] if preferred == fallback else [preferred, fallback]


def is_model_access_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    body = str(getattr(exc, "body", "") or "")
    message = str(exc)
    combined = f"{body} {message}".lower()
    return status_code in {403, 404} and (
        "model_not_found" in combined
        or "does not have access to model" in combined
        or "model" in combined and "not found" in combined
    )
