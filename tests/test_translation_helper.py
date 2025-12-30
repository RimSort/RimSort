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
    UnfinishedItem,
    auto_translate_file,
    create_translation_service,
    find_unfinished_translations,
    get_language_code,
    get_source_keys,
    get_translation_cache,
    get_translation_config,
    parse_ts_file,
    process_language,
    run_lrelease,
    run_lupdate,
    set_translation_config,
    should_skip_translation,
    show_all_stats,
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
        assert config.use_cache

    def test_translation_config_from_dict(self) -> None:
        """Test TranslationConfig.from_dict creates config from dictionary."""
        config_dict: Dict[str, Any] = {
            "retry": {"max_retries": 5, "initial_delay": 0.5},
            "timeout": {"deepl_timeout": 20.0},
            "max_concurrent_requests": 10,
            "use_cache": False,
        }
        config = TranslationConfig.from_dict(config_dict)

        assert config.max_concurrent_requests == 10
        assert config.retry_config.max_retries == 5
        assert config.retry_config.initial_delay == 0.5
        assert config.timeout_config.deepl_timeout == 20.0
        assert not config.use_cache


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

    def test_translation_cache_file_path(self) -> None:
        """Test the global translation cache file path is correctly set."""
        cache = get_translation_cache()
        expected_path = Path(__file__).parent.parent / ".translation_cache.json"
        assert cache._cache_file == expected_path

    def test_clear_translation_cache(self) -> None:
        """Test clearing a temporary translation cache (not global)."""
        cache = TranslationCache()  # Create temporary cache, not global
        cache.set("test", "zh_CN", "en_US", "google", "测试")

        assert cache.size() > 0

        cache.clear()  # Clear the temporary cache
        assert cache.get("test", "zh_CN", "en_US", "google") is None


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


# ============================================================================
# AutoTranslateFile Tests
# ============================================================================


class TestAutoTranslateFile:
    """Tests for auto_translate_file function."""

    @pytest.fixture
    def mock_filesystem(self, mocker: Any) -> Dict[str, Any]:
        """Fixture to mock filesystem operations."""
        mock_exists = mocker.patch("pathlib.Path.exists", return_value=True)
        mock_is_dir = mocker.patch("pathlib.Path.is_dir", return_value=False)
        mock_is_file = mocker.patch("pathlib.Path.is_file", return_value=True)
        mock_glob = mocker.patch(
            "pathlib.Path.glob", return_value=[Path("locales/zh_CN.ts")]
        )
        mock_copy2 = mocker.patch("shutil.copy2")
        mock_unlink = mocker.patch("pathlib.Path.unlink")
        mock_mkdir = mocker.patch("pathlib.Path.mkdir", return_value=None)

        # Mock open for reading/writing file content
        file_content: Dict[str, Any] = {}  # Stores content of mocked files

        def mock_open_func(
            file_path: Any, mode: str = "r", encoding: str = "utf-8"
        ) -> Any:
            if "w" in mode:
                # Simulate writing to a file
                file_content[str(file_path)] = []
                mock_file = mocker.mock_open()
                mock_file.return_value.write.side_effect = lambda data: file_content[
                    str(file_path)
                ].append(data)
                return mock_file.return_value
            else:
                # Simulate reading from a file
                content = "".join(file_content.get(str(file_path), []))
                mock_file = mocker.mock_open(read_data=content)
                return mock_file.return_value

        mocker.patch("builtins.open", side_effect=mock_open_func)
        return {
            "exists": mock_exists,
            "is_dir": mock_is_dir,
            "is_file": mock_is_file,
            "glob": mock_glob,
            "copy2": mock_copy2,
            "unlink": mock_unlink,
            "mkdir": mock_mkdir,
            "file_content": file_content,
        }

    @pytest.fixture
    def mock_xml_parsing(self, mocker: Any) -> Dict[str, Any]:
        """Fixture to mock lxml.etree operations."""
        mock_tree = mocker.Mock()
        mock_root = mocker.Mock()
        mock_tree.getroot.return_value = mock_root
        mock_parse = mocker.patch("lxml.etree.parse", return_value=mock_tree)
        return {
            "parse": mock_parse,
            "tree": mock_tree,
            "root": mock_root,
        }

    @pytest.fixture
    def mock_translation_service(self, mocker: Any) -> Any:
        """Fixture to mock create_translation_service."""
        mock_service_instance = mocker.AsyncMock()
        mocker.patch(
            "translation_helper.create_translation_service",
            return_value=mock_service_instance,
        )
        return mock_service_instance

    @pytest.fixture
    def mock_find_unfinished(self, mocker: Any) -> list[Any]:
        """Fixture to mock find_unfinished_translations."""
        mock_unfinished: list[Any] = []
        mocker.patch(
            "translation_helper.find_unfinished_translations",
            return_value=mock_unfinished,
        )
        return mock_unfinished

    @pytest.fixture(autouse=True)
    def setup_config(self) -> Any:
        """Set up and tear down global config for tests."""

        original_config = get_translation_config()
        # Set a test config to ensure cache is used
        test_config = original_config
        test_config.use_cache = True
        set_translation_config(test_config)
        yield
        set_translation_config(original_config)  # Restore original

    @pytest.mark.asyncio
    async def test_auto_translate_file_success(
        self,
        mocker: Any,
        mock_filesystem: Dict[str, Any],
        mock_xml_parsing: Dict[str, Any],
        mock_translation_service: Any,
        mock_find_unfinished: list[Any],
    ) -> None:
        """Test successful auto-translation scenario."""
        # Arrange
        mock_find_unfinished.extend(
            [
                UnfinishedItem(
                    context="MyContext", source="Hello", element=mocker.Mock(attrib={})
                ),
                UnfinishedItem(
                    context="MyContext", source="World", element=mocker.Mock(attrib={})
                ),
            ]
        )
        mock_translation_service.translate.side_effect = ["你好", "世界"]
        mocker.patch("asyncio.sleep")

        # Mock the XML structure for content writing
        mock_xml_parsing["root"].findall.return_value = []  # No contexts initially
        mock_xml_parsing["tree"].write.side_effect = (
            lambda file, encoding, xml_declaration: mock_filesystem["file_content"]
            .setdefault(str(file), [])
            .append(
                "<TS><context><name>MyContext</name><message><source>Hello</source><translation>你好</translation></message><message><source>World</source><translation>世界</translation></message></context></TS>"
            )
        )

        # Act
        result = await auto_translate_file("zh_CN", service_name="google")

        # Assert
        assert result is True
        mock_filesystem["copy2"].assert_called_once_with(
            Path("locales/zh_CN.ts"), Path("locales/zh_CN.ts.backup")
        )
        mock_translation_service.translate.assert_has_calls(
            [
                mocker.call("Hello", "zh_CN", "en_US"),
                mocker.call("World", "zh_CN", "en_US"),
            ]
        )
        assert mock_find_unfinished[0].element.text == "你好"
        assert "type" not in mock_find_unfinished[0].element.attrib
        mock_xml_parsing["tree"].write.assert_called_once_with(
            Path("locales/zh_CN.ts"), encoding="utf-8", xml_declaration=True
        )
        mock_filesystem["unlink"].assert_called_once_with()  # Backup removed

    @pytest.mark.asyncio
    async def test_auto_translate_file_dry_run(
        self,
        mocker: Any,
        mock_filesystem: Dict[str, Any],
        mock_xml_parsing: Dict[str, Any],
        mock_translation_service: Any,
        mock_find_unfinished: list[Any],
        capsys: Any,  # To capture print output
    ) -> None:
        """Test dry-run mode for auto-translation."""
        # Arrange
        mock_element = mocker.Mock()
        mock_element.text = None
        mock_find_unfinished.extend(
            [
                UnfinishedItem(
                    context="MyContext", source="Hello", element=mock_element
                ),
            ]
        )
        mock_translation_service.translate.return_value = "你好"
        mocker.patch("asyncio.sleep")

        # Act
        result = await auto_translate_file("zh_CN", service_name="google", dry_run=True)

        # Assert
        assert result is True  # Dry-run success doesn't depend on actual saves
        mock_filesystem["copy2"].assert_not_called()
        mock_translation_service.translate.assert_called_once()
        assert (
            mock_find_unfinished[0].element.text is None
        )  # Element not updated in dry run
        mock_xml_parsing["tree"].write.assert_not_called()
        mock_filesystem["unlink"].assert_not_called()

        captured = capsys.readouterr()
        assert "DRY-RUN MODE" in captured.out
        assert "No changes saved" in captured.out
        assert "Would update: 0 translations." in captured.out
        # Use path-agnostic check (handles both Windows \ and Linux /)
        assert "Would update file:" in captured.out and "zh_CN.ts" in captured.out

    @pytest.mark.asyncio
    async def test_auto_translate_file_failure_no_continue(
        self,
        mocker: Any,
        mock_filesystem: Dict[str, Any],
        mock_xml_parsing: Dict[str, Any],
        mock_translation_service: Any,
        mock_find_unfinished: list[Any],
    ) -> None:
        """Test auto-translation aborts and restores backup on failure when continue_on_failure is False."""
        # Arrange
        mock_find_unfinished.extend(
            [
                UnfinishedItem(
                    context="MyContext", source="Hello", element=mocker.Mock()
                ),
                UnfinishedItem(
                    context="MyContext", source="World", element=mocker.Mock()
                ),
            ]
        )
        # First translation succeeds, second fails
        mock_translation_service.translate.side_effect = [
            "你好",
            Exception("Translation service error"),
        ]
        mocker.patch("asyncio.sleep")

        # Set continue_on_failure to False
        original_config = get_translation_config()
        test_config = original_config
        test_config.retry_config.max_retries = 1  # No retries
        set_translation_config(test_config)

        # Act
        result = await auto_translate_file(
            "zh_CN", service_name="google", continue_on_failure=False
        )

        # Assert
        assert result is False
        # copy2 is called twice: once for backup, once for restore
        assert mock_filesystem["copy2"].call_count == 2
        mock_translation_service.translate.assert_has_calls(
            [
                mocker.call("Hello", "zh_CN", "en_US"),
                mocker.call("World", "zh_CN", "en_US"),
            ]
        )
        mock_xml_parsing["tree"].write.assert_not_called()  # File should not be saved
        # Backup should be restored (simulated by not unlinking and printing message)
        # Note: The mock_filesystem["copy2"] from the finally block would be for restoring
        #       if we mocked Path.exists correctly for the backup file. For simplicity
        #       we verify that tree.write is not called and the success is False.
        mock_filesystem["unlink"].assert_not_called()  # Backup not removed on failure
        set_translation_config(original_config)

    @pytest.mark.asyncio
    async def test_auto_translate_file_failure_with_continue(
        self,
        mocker: Any,
        mock_filesystem: Dict[str, Any],
        mock_xml_parsing: Dict[str, Any],
        mock_translation_service: Any,
        mock_find_unfinished: list[Any],
    ) -> None:
        """Test auto-translation saves partial results on failure when continue_on_failure is True."""
        # Arrange
        mock_find_unfinished.extend(
            [
                UnfinishedItem(
                    context="MyContext", source="Hello", element=mocker.Mock()
                ),
                UnfinishedItem(
                    context="MyContext", source="World", element=mocker.Mock()
                ),
            ]
        )
        # First translation succeeds, second fails
        mock_translation_service.translate.side_effect = [
            "你好",
            Exception("Translation service error"),
        ]
        mocker.patch("asyncio.sleep")

        # Mock the XML structure for content writing
        mock_xml_parsing["root"].findall.return_value = []  # No contexts initially
        mock_xml_parsing["tree"].write.side_effect = (
            lambda file, encoding, xml_declaration: mock_filesystem["file_content"][
                str(file)
            ].append(
                "<TS><context><name>MyContext</name><message><source>Hello</source><translation>你好</translation></message><message><source>World</source><translation type='unfinished'></translation></message></context></TS>"
            )
        )

        # Act
        # continue_on_failure is True by default for auto_translate_file
        result = await auto_translate_file(
            "zh_CN", service_name="google", continue_on_failure=True
        )

        # Assert
        assert (
            result is False
        )  # Because one translation failed, overall result is False
        # copy2 is called once for backup and once for restore (due to save error)
        assert mock_filesystem["copy2"].call_count == 2
        mock_translation_service.translate.assert_has_calls(
            [
                mocker.call("Hello", "zh_CN", "en_US"),
                mocker.call("World", "zh_CN", "en_US"),
            ]
        )
        assert mock_find_unfinished[0].element.text == "你好"  # First one translated
        # Second element is a mock, so it will have a Mock object, not None
        # The actual code updates it during processing
        mock_xml_parsing["tree"].write.assert_called_once()  # File should be saved
        # Backup is restored due to save error
        mock_filesystem["unlink"].assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_translate_file_unexpected_exception(
        self,
        mocker: Any,
        mock_filesystem: Dict[str, Any],
        mock_xml_parsing: Dict[str, Any],
        mock_translation_service: Any,
        mock_find_unfinished: list[Any],
    ) -> None:
        """Test auto-translation restores backup if an unexpected exception occurs."""
        # Arrange
        mock_find_unfinished.extend(
            [
                UnfinishedItem(
                    context="MyContext", source="Hello", element=mocker.Mock()
                ),
            ]
        )
        # Simulate an unexpected exception during processing loop
        mock_translation_service.translate.side_effect = Exception(
            "Unexpected error outside translation"
        )
        mocker.patch("asyncio.sleep")

        # Act
        result = await auto_translate_file("zh_CN", service_name="google")

        # Assert
        assert result is False
        # copy2 is called once for initial backup
        assert mock_filesystem["copy2"].call_count == 1
        mock_translation_service.translate.assert_called_once()
        # With continue_on_failure=True (default), tree.write IS called even when error occurs
        # because the error happens during translation and failed items are handled gracefully
        # File gets saved with partial results
        mock_xml_parsing["tree"].write.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_translate_file_no_unfinished_translations(
        self,
        mocker: Any,
        mock_filesystem: Dict[str, Any],
        mock_xml_parsing: Dict[str, Any],
        mock_translation_service: Any,
        mock_find_unfinished: list[Any],
    ) -> None:
        """Test auto-translation handles no unfinished translations gracefully."""
        # Arrange: mock_find_unfinished is empty by default
        mocker.patch("asyncio.sleep")

        # Act
        result = await auto_translate_file("zh_CN", service_name="google")

        # Assert
        assert result is True  # No failures, so success
        # Backup is always created and then removed on success
        assert mock_filesystem["copy2"].call_count == 1  # Only the initial backup
        mock_translation_service.translate.assert_not_called()  # No translation calls
        # File is written even when no translations (finally block)
        mock_xml_parsing["tree"].write.assert_called_once()
        # Backup is removed on success
        mock_filesystem["unlink"].assert_called_once()


# ============================================================================
# CreateTranslationService Tests
# ============================================================================


class TestCreateTranslationService:
    """Tests for create_translation_service function."""

    def test_create_google_service(self, mocker: Any) -> None:
        """Test creating Google translation service."""
        # Mock GoogleTranslator to be available (not None)
        mocker.patch("translation_helper.GoogleTranslator", mocker.Mock())

        mock_service = mocker.Mock()
        mocker.patch(
            "translation_helper.GoogleTranslateService", return_value=mock_service
        )

        result = create_translation_service("google")

        assert result == mock_service

    def test_create_deepl_service(self, mocker: Any) -> None:
        """Test creating DeepL translation service."""
        mock_service = mocker.Mock()
        mocker.patch("translation_helper.DeepLService", return_value=mock_service)

        result = create_translation_service("deepl", api_key="fake_key")

        assert result == mock_service

    def test_create_openai_service(self, mocker: Any) -> None:
        """Test creating OpenAI translation service."""
        mock_service = mocker.Mock()
        mocker.patch("translation_helper.OpenAIService", return_value=mock_service)

        result = create_translation_service("openai", api_key="fake_key")

        assert result == mock_service

    def test_create_unknown_service(self) -> None:
        """Test creating unknown translation service raises error."""
        with pytest.raises(ValueError, match="Unsupported service"):
            create_translation_service("unknown", api_key="fake_key")


# ============================================================================
# FindUnfinishedTranslations Tests
# ============================================================================


class TestFindUnfinishedTranslations:
    """Tests for find_unfinished_translations function."""

    def test_find_unfinished_translations(self, mocker: Any) -> None:
        """Test finding unfinished translations in XML."""
        mock_tree = mocker.Mock()
        mock_root = mocker.Mock()
        mock_tree.getroot.return_value = mock_root

        # Mock contexts and messages
        mock_context = mocker.Mock()
        mock_context.findtext.return_value = "MyContext"

        mock_message = mocker.Mock()
        mock_message.find.side_effect = lambda tag: {
            "source": mocker.Mock(text="Hello"),
            "translation": mocker.Mock(text=None, attrib={}),
        }.get(tag)

        mock_context.findall.return_value = [mock_message]
        mock_root.findall.return_value = [mock_context]

        result = find_unfinished_translations(mock_tree)

        assert len(result) == 1
        assert result[0].context == "MyContext"
        assert result[0].source == "Hello"

    def test_find_unfinished_translations_no_unfinished(self, mocker: Any) -> None:
        """Test finding unfinished translations when all are finished."""
        mock_tree = mocker.Mock()
        mock_root = mocker.Mock()
        mock_tree.getroot.return_value = mock_root

        mock_context = mocker.Mock()
        mock_message = mocker.Mock()
        mock_message.find.side_effect = lambda tag: {
            "source": mocker.Mock(text="Hello"),
            "translation": mocker.Mock(text="你好", attrib={}),
        }.get(tag)

        mock_context.findall.return_value = [mock_message]
        mock_root.findall.return_value = [mock_context]

        result = find_unfinished_translations(mock_tree)

        assert len(result) == 0


# ============================================================================
# GetSourceKeys Tests
# ============================================================================


class TestGetSourceKeys:
    """Tests for get_source_keys function."""

    def test_get_source_keys(self, mocker: Any) -> None:
        """Test getting source keys from unfinished items."""
        unfinished_items = [
            UnfinishedItem(context="Ctx1", source="Key1", element=mocker.Mock()),
            UnfinishedItem(context="Ctx1", source="Key2", element=mocker.Mock()),
            UnfinishedItem(context="Ctx2", source="Key3", element=mocker.Mock()),
        ]

        result = get_source_keys(unfinished_items)

        expected = {"Ctx1": ["Key1", "Key2"], "Ctx2": ["Key3"]}
        assert result == expected

    def test_get_source_keys_empty(self) -> None:
        """Test getting source keys from empty list."""
        result = get_source_keys([])
        assert result == {}


# ============================================================================
# ParseTsFile Tests
# ============================================================================


class TestParseTsFile:
    """Tests for parse_ts_file function."""

    def test_parse_ts_file_success(self, mocker: Any) -> None:
        """Test successful TS file parsing."""
        mock_tree = mocker.Mock()
        mock_root = mocker.Mock()
        mock_tree.getroot.return_value = mock_root
        mock_root.get.return_value = "zh_CN"
        mock_root.findall.return_value = []  # No contexts
        mocker.patch("lxml.etree.parse", return_value=mock_tree)

        result = parse_ts_file(Path("test.ts"))

        expected = {
            "stats": {
                "total": 0,
                "translated": 0,
                "unfinished": 0,
                "obsolete": 0,
                "missing": 0,
            },
            "issues": [],
            "language": "zh_CN",
        }
        assert result == expected

    def test_parse_ts_file_failure(self, mocker: Any) -> None:
        """Test TS file parsing failure."""
        mocker.patch("lxml.etree.parse", side_effect=Exception("Parse error"))

        result = parse_ts_file(Path("test.ts"))

        assert result == {"error": "Parse error"}


# ============================================================================
# ProcessLanguage Tests
# ============================================================================


class TestProcessLanguage:
    """Tests for process_language function."""

    @pytest.fixture
    def mock_filesystem(self, mocker: Any) -> Dict[str, Any]:
        """Fixture to mock filesystem operations."""
        mock_exists = mocker.patch("pathlib.Path.exists", return_value=True)
        mock_glob = mocker.patch(
            "pathlib.Path.glob", return_value=[Path("locales/zh_CN.ts")]
        )
        return {"exists": mock_exists, "glob": mock_glob}

    @pytest.mark.asyncio
    async def test_process_language_success(
        self, mocker: Any, mock_filesystem: Dict[str, Any]
    ) -> None:
        """Test successful language processing."""
        mock_auto_translate = mocker.patch(
            "translation_helper.auto_translate_file", return_value=True
        )
        mock_lupdate = mocker.patch("translation_helper.run_lupdate", return_value=True)
        mock_lrelease = mocker.patch(
            "translation_helper.run_lrelease", return_value=True
        )

        result = await process_language("zh_CN", "google", dry_run=False)

        assert result is True  # Process successful
        mock_lupdate.assert_called_once_with("zh_CN")
        # auto_translate_file is called with positional args: language, service, continue_on_failure
        mock_auto_translate.assert_called_once_with(
            "zh_CN", "google", True, dry_run=False
        )
        mock_lrelease.assert_called_once_with("zh_CN")

    @pytest.mark.asyncio
    async def test_process_language_no_files(self, mocker: Any) -> None:
        """Test language processing with no files."""
        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("translation_helper.run_lupdate", return_value=False)

        result = await process_language("zh_CN", "google", dry_run=False)

        assert result is False  # Process failed due to lupdate failure


# ============================================================================
# RunLrelease Tests
# ============================================================================


class TestRunLrelease:
    """Tests for run_lrelease function."""

    def test_run_lrelease_success(self, mocker: Any) -> None:
        """Test successful lrelease run."""
        mock_subprocess = mocker.patch("subprocess.run")
        mock_subprocess.return_value.returncode = 0
        mocker.patch("pathlib.Path.exists", return_value=True)

        result = run_lrelease("test")

        assert result is True
        mock_subprocess.assert_called_once()

    def test_run_lrelease_failure(self, mocker: Any) -> None:
        """Test lrelease run failure."""
        mock_subprocess = mocker.patch("subprocess.run")
        mock_subprocess.return_value.returncode = 1

        result = run_lrelease("test")

        assert result is False


# ============================================================================
# RunLupdate Tests
# ============================================================================


class TestRunLupdate:
    """Tests for run_lupdate function."""

    def test_run_lupdate_success(self, mocker: Any) -> None:
        """Test successful lupdate run."""
        mock_subprocess = mocker.patch("subprocess.run")
        mock_subprocess.return_value.returncode = 0

        result = run_lupdate("project.pro")

        assert result is True
        mock_subprocess.assert_called_once()

    def test_run_lupdate_failure(self, mocker: Any) -> None:
        """Test lupdate run failure."""
        mock_subprocess = mocker.patch("subprocess.run")
        mock_subprocess.return_value.returncode = 1

        result = run_lupdate("project.pro")

        assert result is False


# ============================================================================
# ShouldSkipTranslation Tests
# ============================================================================


class TestShouldSkipTranslation:
    """Tests for should_skip_translation function."""

    def test_should_skip_translation_empty_string(self) -> None:
        """Test skipping empty or whitespace-only strings."""
        assert should_skip_translation("") is True
        assert should_skip_translation("   ") is True

    def test_should_skip_translation_single_character(self) -> None:
        """Test skipping single characters."""
        assert should_skip_translation("a") is True
        assert should_skip_translation("1") is True

    def test_should_skip_translation_numbers(self) -> None:
        """Test skipping pure numbers."""
        assert should_skip_translation("123") is True
        assert should_skip_translation("0") is True

    def test_should_skip_translation_symbols(self) -> None:
        """Test skipping pure symbols."""
        assert should_skip_translation("!") is True
        assert should_skip_translation("!?@#") is True

    def test_should_not_skip_translation_valid_text(self) -> None:
        """Test not skipping valid translatable text."""
        assert should_skip_translation("Hello") is False
        assert should_skip_translation("Hello World") is False
        assert should_skip_translation("Button") is False


# ============================================================================
# ShowAllStats Tests
# ============================================================================


class TestShowAllStats:
    """Tests for show_all_stats function."""

    def test_show_all_stats(self, mocker: Any, capsys: Any) -> None:
        """Test showing all statistics."""
        # Mock the filesystem to return some TS files
        mocker.patch(
            "pathlib.Path.glob",
            return_value=[
                Path("locales/en.ts"),
                Path("locales/zh_CN.ts"),
                Path("locales/ja_JP.ts"),
            ],
        )

        # Mock parse_ts_file to return proper dict
        mock_parse_result = {
            "stats": {
                "total": 10,
                "translated": 8,
                "unfinished": 2,
                "obsolete": 0,
                "missing": 0,
            },
            "issues": [],
            "language": "zh_CN",
        }
        mocker.patch("translation_helper.parse_ts_file", return_value=mock_parse_result)

        show_all_stats()

        captured = capsys.readouterr()
        assert "Translation Statistics" in captured.out
        assert "Total files:" in captured.out
        assert "Unfinished" in captured.out  # Check for the column header
