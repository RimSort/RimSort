"""Gemini model catalog and quota-limit hints for the AI assistant."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeminiModelSpec:
    model_id: str
    label: str
    rpm: int | None = None
    rpd: int | None = None


# Free-tier limits (approximate); used for UI hints and fallback ordering.
GEMINI_MODELS: tuple[GeminiModelSpec, ...] = (
    GeminiModelSpec(
        "gemini-3.5-flash-lite",
        "Gemini 3.5 Flash Lite",
        rpm=15,
        rpd=500,
    ),
    GeminiModelSpec(
        "gemini-2.5-flash-lite",
        "Gemini 2.5 Flash Lite",
        rpm=10,
        rpd=20,
    ),
    GeminiModelSpec(
        "gemini-2.5-flash",
        "Gemini 2.5 Flash",
        rpm=5,
        rpd=20,
    ),
    GeminiModelSpec(
        "gemini-3-flash",
        "Gemini 3 Flash",
        rpm=5,
        rpd=20,
    ),
    GeminiModelSpec(
        "gemini-3.5-flash",
        "Gemini 3.5 Flash",
        rpm=5,
        rpd=20,
    ),
    GeminiModelSpec(
        "gemini-3.6-flash",
        "Gemini 3.6 Flash",
        rpm=5,
        rpd=20,
    ),
    GeminiModelSpec(
        "gemini-3.7-flash",
        "Gemini 3.7 Flash",
        rpm=5,
        rpd=20,
    ),
)

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"

_MODEL_BY_ID = {spec.model_id: spec for spec in GEMINI_MODELS}


def get_model_spec(model_id: str) -> GeminiModelSpec | None:
    return _MODEL_BY_ID.get(model_id)


def normalize_model_id(model_id: str | None) -> str:
    if model_id and model_id in _MODEL_BY_ID:
        return model_id
    return DEFAULT_GEMINI_MODEL


def suggest_models_excluding(current_model_id: str) -> list[GeminiModelSpec]:
    current = normalize_model_id(current_model_id)
    others = [spec for spec in GEMINI_MODELS if spec.model_id != current]
    return sorted(others, key=lambda spec: (-(spec.rpd or 0), -(spec.rpm or 0)))


def format_quota_error_message(current_model_id: str) -> str:
    current = get_model_spec(normalize_model_id(current_model_id))
    current_label = current.label if current else current_model_id
    suggestions = suggest_models_excluding(current_model_id)
    lines = [
        f"Rate limit or daily quota exceeded for {current_label}.",
        "Try another model in the AI Assistant (Model dropdown):",
    ]
    for spec in suggestions[:5]:
        limit_bits: list[str] = []
        if spec.rpm is not None:
            limit_bits.append(f"{spec.rpm} RPM")
        if spec.rpd is not None:
            limit_bits.append(f"{spec.rpd} RPD")
        limits = f" ({', '.join(limit_bits)})" if limit_bits else ""
        lines.append(f"  - {spec.label} [{spec.model_id}]{limits}")
    return "\n".join(lines)


def is_quota_error_message(message: str) -> bool:
    lowered = message.lower()
    return (
        "rate limit or daily quota exceeded" in lowered
        or "try another model in the ai assistant" in lowered
    )
