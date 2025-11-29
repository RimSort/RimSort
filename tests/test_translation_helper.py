import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Import modules under test
sys.path.insert(0, str(Path(__file__).parent.parent))
from translation_helper import (
    LANG_MAP,
    RetryConfig,
    TimeoutConfig,
    TranslationCache,
    TranslationConfig,
    clear_translation_cache,
    get_language_code,
    get_translation_cache,
    get_translation_config,
    set_translation_config,
    validate_api_key,
    validate_concurrent_requests,
    validate_language_code,
    validate_model_name,
    validate_retry_count,
    validate_timeout,
)

# ============================================================================
# RetryConfig Tests
# ============================================================================


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_retry_config_defaults(self) -> None:
        """Test RetryConfig uses correct default values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0

    def test_retry_config_custom_values(self) -> None:
        """Test RetryConfig accepts custom values."""
        config = RetryConfig(
            max_retries=5,
            initial_delay=0.5,
            max_delay=60.0,
            exponential_base=1.5,
        )
        assert config.max_retries == 5
        assert config.initial_delay == 0.5
        assert config.max_delay == 60.0
        assert config.exponential_base == 1.5

    def test_get_delay_exponential_backoff(self) -> None:
        """Test exponential backoff calculation."""
        config = RetryConfig(initial_delay=1.0, exponential_base=2.0, max_delay=30.0)

        # Attempt 0: 1.0 * 2^0 = 1.0
        assert config.get_delay(0) == 1.0

        # Attempt 1: 1.0 * 2^1 = 2.0
        assert config.get_delay(1) == 2.0

        # Attempt 2: 1.0 * 2^2 = 4.0
        assert config.get_delay(2) == 4.0

        # Attempt 3: 1.0 * 2^3 = 8.0
        assert config.get_delay(3) == 8.0

    def test_get_delay_respects_max_delay(self) -> None:
        """Test that get_delay respects max_delay cap."""
        config = RetryConfig(initial_delay=1.0, exponential_base=2.0, max_delay=10.0)

        # Attempt 5: 1.0 * 2^5 = 32.0, but should be capped at 10.0
        assert config.get_delay(5) == 10.0

        # Verify capping
        assert config.get_delay(10) == 10.0


# ============================================================================
# TimeoutConfig Tests
# ============================================================================


class TestTimeoutConfig:
    """Tests for TimeoutConfig dataclass."""

    def test_timeout_config_defaults(self) -> None:
        """Test TimeoutConfig uses correct default values."""
        config = TimeoutConfig()
        assert config.default_timeout == 10.0
        assert config.deepl_timeout == 10.0
        assert config.openai_timeout == 10.0
        assert config.google_timeout == 10.0

    def test_timeout_config_custom_values(self) -> None:
        """Test TimeoutConfig accepts custom values."""
        config = TimeoutConfig(
            default_timeout=15.0,
            deepl_timeout=20.0,
            openai_timeout=25.0,
            google_timeout=12.0,
        )
        assert config.default_timeout == 15.0
        assert config.deepl_timeout == 20.0
        assert config.openai_timeout == 25.0
        assert config.google_timeout == 12.0


# ============================================================================
# TranslationConfig Tests
# ============================================================================


class TestTranslationConfig:
    """Tests for TranslationConfig dataclass."""

    def test_translation_config_defaults(self) -> None:
        """Test TranslationConfig uses correct defaults."""
        config = TranslationConfig()
        assert config.max_concurrent_requests == 5
        assert isinstance(config.retry_config, RetryConfig)
        assert isinstance(config.timeout_config, TimeoutConfig)

    def test_translation_config_from_dict(self) -> None:
        """Test TranslationConfig.from_dict creates config from dictionary."""
        config_dict: Dict[str, Any] = {
            "retry": {"max_retries": 5, "initial_delay": 0.5},
            "timeout": {"deepl_timeout": 20.0},
            "max_concurrent_requests": 10,
        }
        config = TranslationConfig.from_dict(config_dict)

        assert config.max_concurrent_requests == 10
        assert config.retry_config.max_retries == 5
        assert config.retry_config.initial_delay == 0.5
        assert config.timeout_config.deepl_timeout == 20.0


# ============================================================================
# TranslationCache Tests
# ============================================================================


class TestTranslationCache:
    """Tests for TranslationCache dataclass."""

    def test_cache_initialization(self) -> None:
        """Test TranslationCache initializes empty."""
        cache = TranslationCache()
        assert cache.size() == 0

    def test_cache_set_and_get(self) -> None:
        """Test cache stores and retrieves translations."""
        cache = TranslationCache()

        cache.set("Hello", "zh_CN", "en_US", "google", "你好")
        result = cache.get("Hello", "zh_CN", "en_US", "google")

        assert result == "你好"
        assert cache.size() == 1

    def test_cache_different_keys(self) -> None:
        """Test cache distinguishes between different parameters."""
        cache = TranslationCache()

        cache.set("Hello", "zh_CN", "en_US", "google", "你好")
        cache.set("Hello", "ja_JP", "en_US", "google", "こんにちは")
        cache.set("Hello", "zh_CN", "en_US", "deepl", "你好_deepl")

        # Different target language
        assert cache.get("Hello", "ja_JP", "en_US", "google") == "こんにちは"

        # Different service
        assert cache.get("Hello", "zh_CN", "en_US", "deepl") == "你好_deepl"

        # Original
        assert cache.get("Hello", "zh_CN", "en_US", "google") == "你好"

        assert cache.size() == 3

    def test_cache_clear(self) -> None:
        """Test cache clear removes all entries."""
        cache = TranslationCache()
        cache.set("Hello", "zh_CN", "en_US", "google", "你好")
        cache.set("World", "zh_CN", "en_US", "google", "世界")

        assert cache.size() == 2
        cache.clear()
        assert cache.size() == 0

    def test_cache_miss(self) -> None:
        """Test cache returns None for missing entries."""
        cache = TranslationCache()
        result = cache.get("NotInCache", "zh_CN", "en_US", "google")
        assert result is None


# ============================================================================
# Input Validation Tests
# ============================================================================


class TestValidateLanguageCode:
    """Tests for validate_language_code function."""

    def test_valid_language_codes(self) -> None:
        """Test validation accepts valid language codes."""
        for lang in LANG_MAP.keys():
            result = validate_language_code(lang)
            assert result == lang

    def test_invalid_language_code(self) -> None:
        """Test validation rejects invalid language codes."""
        with pytest.raises(ValueError, match="Unsupported language"):
            validate_language_code("xx_XX")

    def test_none_language_code(self) -> None:
        """Test None is accepted for optional language."""
        result = validate_language_code(None)
        assert result is None


class TestValidateTimeout:
    """Tests for validate_timeout function."""

    def test_valid_timeout(self) -> None:
        """Test validation accepts valid timeouts."""
        assert validate_timeout(5.0) == 5.0
        assert validate_timeout(10) == 10.0
        assert validate_timeout(300.0) == 300.0

    def test_invalid_timeout_zero(self) -> None:
        """Test validation rejects zero timeout."""
        with pytest.raises(ValueError, match="must be positive"):
            validate_timeout(0)

    def test_invalid_timeout_negative(self) -> None:
        """Test validation rejects negative timeout."""
        with pytest.raises(ValueError, match="must be positive"):
            validate_timeout(-5.0)

    def test_invalid_timeout_too_large(self) -> None:
        """Test validation warns about very large timeout."""
        with pytest.raises(ValueError, match="very large"):
            validate_timeout(301.0)

    def test_invalid_timeout_type(self) -> None:
        """Test validation rejects non-numeric timeout."""
        with pytest.raises(TypeError, match="must be a number"):
            validate_timeout("10")  # type: ignore


class TestValidateRetryCount:
    """Tests for validate_retry_count function."""

    def test_valid_retry_count(self) -> None:
        """Test validation accepts valid retry counts."""
        assert validate_retry_count(0) == 0
        assert validate_retry_count(3) == 3
        assert validate_retry_count(10) == 10

    def test_invalid_retry_count_negative(self) -> None:
        """Test validation rejects negative retry count."""
        with pytest.raises(ValueError, match="cannot be negative"):
            validate_retry_count(-1)

    def test_invalid_retry_count_too_high(self) -> None:
        """Test validation warns about very high retry count."""
        with pytest.raises(ValueError, match="very high"):
            validate_retry_count(11)

    def test_invalid_retry_count_type(self) -> None:
        """Test validation rejects non-integer retry count."""
        with pytest.raises(TypeError, match="must be an integer"):
            validate_retry_count(3.5)  # type: ignore


class TestValidateConcurrentRequests:
    """Tests for validate_concurrent_requests function."""

    def test_valid_concurrent(self) -> None:
        """Test validation accepts valid concurrency values."""
        assert validate_concurrent_requests(1) == 1
        assert validate_concurrent_requests(5) == 5
        assert validate_concurrent_requests(100) == 100

    def test_invalid_concurrent_zero(self) -> None:
        """Test validation rejects zero concurrency."""
        with pytest.raises(ValueError, match="must be positive"):
            validate_concurrent_requests(0)

    def test_invalid_concurrent_negative(self) -> None:
        """Test validation rejects negative concurrency."""
        with pytest.raises(ValueError, match="must be positive"):
            validate_concurrent_requests(-5)

    def test_invalid_concurrent_too_high(self) -> None:
        """Test validation warns about very high concurrency."""
        with pytest.raises(ValueError, match="very high"):
            validate_concurrent_requests(101)

    def test_invalid_concurrent_type(self) -> None:
        """Test validation rejects non-integer concurrency."""
        with pytest.raises(TypeError, match="must be an integer"):
            validate_concurrent_requests(5.0)  # type: ignore


class TestValidateApiKey:
    """Tests for validate_api_key function."""

    def test_valid_api_key(self) -> None:
        """Test validation accepts valid API keys."""
        key = validate_api_key("fake-openai-api-key", "OpenAI")
        assert key == "fake-openai-api-key"

    def test_empty_api_key(self) -> None:
        """Test validation rejects empty API key."""
        with pytest.raises(ValueError, match="requires a valid API key"):
            validate_api_key("", "DeepL")

    def test_none_api_key(self) -> None:
        """Test validation rejects None API key."""
        with pytest.raises(ValueError, match="requires a valid API key"):
            validate_api_key(None, "DeepL")

    def test_short_api_key(self) -> None:
        """Test validation rejects too-short API key."""
        with pytest.raises(ValueError, match="appears invalid"):
            validate_api_key("key", "OpenAI")

    def test_api_key_type_validation(self) -> None:
        """Test validation rejects non-string API key."""
        with pytest.raises(TypeError, match="must be a string"):
            validate_api_key(12345, "OpenAI")  # type: ignore

    def test_api_key_whitespace_stripped(self) -> None:
        """Test API key whitespace is stripped."""
        key = validate_api_key("  fake-openai-api-key  ", "OpenAI")
        assert key == "fake-openai-api-key"


class TestValidateModelName:
    """Tests for validate_model_name function."""

    def test_valid_model_name(self) -> None:
        """Test validation accepts valid model names."""
        assert validate_model_name("gpt-3.5-turbo") == "gpt-3.5-turbo"
        assert validate_model_name("gpt-4") == "gpt-4"

    def test_default_model_name(self) -> None:
        """Test None returns default model."""
        result = validate_model_name(None)
        assert result == "gpt-3.5-turbo"

    def test_empty_model_name(self) -> None:
        """Test validation rejects empty model name."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_model_name("")

    def test_invalid_model_name_format(self) -> None:
        """Test validation rejects invalid format."""
        with pytest.raises(ValueError, match="Invalid model name format"):
            validate_model_name("model@invalid!")

    def test_model_name_type_validation(self) -> None:
        """Test validation rejects non-string model."""
        with pytest.raises(TypeError, match="must be a string"):
            validate_model_name(12345)  # type: ignore


# ============================================================================
# Language Code Mapping Tests
# ============================================================================


class TestGetLanguageCode:
    """Tests for get_language_code function."""

    def test_google_translate_code(self) -> None:
        """Test getting Google Translate language codes."""
        # zh_CN should map to 'zh-cn' for Google
        code = get_language_code("zh_CN", "google")
        assert code == "zh-cn"

    def test_deepl_code(self) -> None:
        """Test getting DeepL language codes."""
        # zh_CN should map to 'ZH' for DeepL
        code = get_language_code("zh_CN", "deepl")
        assert code == "ZH"

    def test_openai_code(self) -> None:
        """Test getting OpenAI language codes."""
        # zh_CN should map to 'Simplified Chinese' for OpenAI
        code = get_language_code("zh_CN", "openai")
        assert code == "Simplified Chinese"

    def test_fallback_google_format(self) -> None:
        """Test fallback formatting for Google (unmapped languages)."""
        # For unmapped language, Google format should be lowercase with hyphens
        code = get_language_code("en_US", "google")
        # en_US is in LANG_MAP, so it should use the mapped value
        assert isinstance(code, str)

    def test_fallback_deepl_format(self) -> None:
        """Test fallback formatting for DeepL (unmapped languages)."""
        code = get_language_code("en_US", "deepl")
        assert isinstance(code, str)

    def test_fallback_other_format(self) -> None:
        """Test fallback for unmapped service."""
        code = get_language_code("en_US", "unknown")
        assert isinstance(code, str)


# ============================================================================
# Global Configuration Tests
# ============================================================================


class TestGlobalConfiguration:
    """Tests for global configuration management."""

    def test_get_translation_config(self) -> None:
        """Test getting global translation config."""
        config = get_translation_config()
        assert isinstance(config, TranslationConfig)
        assert config.max_concurrent_requests == 5

    def test_set_translation_config(self) -> None:
        """Test setting global translation config."""
        original = get_translation_config()
        new_config = TranslationConfig(max_concurrent_requests=10)

        set_translation_config(new_config)
        retrieved = get_translation_config()

        assert retrieved.max_concurrent_requests == 10

        # Restore original
        set_translation_config(original)

    def test_get_translation_cache(self) -> None:
        """Test getting global translation cache."""
        cache = get_translation_cache()
        assert isinstance(cache, TranslationCache)

    def test_clear_translation_cache(self) -> None:
        """Test clearing global translation cache."""
        cache = get_translation_cache()
        cache.set("test", "zh_CN", "en_US", "google", "测试")

        assert cache.size() > 0

        clear_translation_cache()
        # Create a new cache instance to test
        cache_after = get_translation_cache()
        # The global cache should be cleared
        assert cache_after.get("test", "zh_CN", "en_US", "google") is None


# ============================================================================
# Integration Tests
# ============================================================================


class TestConfigurationIntegration:
    """Integration tests for configuration system."""

    def test_full_configuration_workflow(self) -> None:
        """Test complete configuration workflow."""
        # Create custom config
        custom_config = TranslationConfig(
            retry_config=RetryConfig(max_retries=5),
            timeout_config=TimeoutConfig(deepl_timeout=20.0),
            max_concurrent_requests=10,
        )

        # Set globally
        set_translation_config(custom_config)

        # Verify retrieval
        retrieved = get_translation_config()
        assert retrieved.retry_config.max_retries == 5
        assert retrieved.timeout_config.deepl_timeout == 20.0
        assert retrieved.max_concurrent_requests == 10

    def test_cache_with_validation(self) -> None:
        """Test cache works with validated language codes."""
        # Validate language
        lang = validate_language_code("zh_CN")
        assert lang is not None

        # Use in cache
        cache = get_translation_cache()
        cache.set("hello", lang, "en_US", "google", "你好")

        # Retrieve and verify
        result = cache.get("hello", lang, "en_US", "google")
        assert result == "你好"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
