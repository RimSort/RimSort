from app.ai.gemini_models import (
    DEFAULT_GEMINI_MODEL,
    GEMINI_MODELS,
    format_quota_error_message,
    is_quota_error_message,
    normalize_model_id,
    suggest_models_excluding,
)


def test_normalize_model_id_unknown_defaults() -> None:
    assert normalize_model_id("unknown-model") == DEFAULT_GEMINI_MODEL


def test_suggest_models_prefers_higher_rpd() -> None:
    suggestions = suggest_models_excluding("gemini-3.5-flash")
    assert suggestions[0].model_id == "gemini-3.5-flash-lite"


def test_format_quota_error_lists_alternatives() -> None:
    message = format_quota_error_message("gemini-3.5-flash")
    assert "gemini-3.5-flash-lite" in message
    assert is_quota_error_message(message)


def test_all_catalog_models_have_ids() -> None:
    assert len({spec.model_id for spec in GEMINI_MODELS}) == len(GEMINI_MODELS)
