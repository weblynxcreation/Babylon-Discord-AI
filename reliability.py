"""Shared model selection and bounded agent settings."""
import math
import os

DEFAULT_CHAT_MODEL = "meta/llama-3.3-70b-instruct"


def chat_model() -> str:
    return os.environ.get("NVIDIA_CHAT_MODEL", "").strip() or DEFAULT_CHAT_MODEL


def timeout_seconds(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        raise ValueError(f"{name} must be a positive finite number.") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number.")
    return value
