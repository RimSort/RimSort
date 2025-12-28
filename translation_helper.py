"""RimSort Translation Helper - Comprehensive tool for managing Qt translations.

A complete translation management system for RimSort that provides interactive and
command-line interfaces for all translation workflows. The tool supports multiple
translation services and enables efficient batch operations across languages.

Core Capabilities:
- Interactive and command-line interfaces for translation workflows
- Support for multiple translation services (Google Translate, DeepL, OpenAI)
- Automatic translation with intelligent retry logic and exponential backoff
- Translation validation and auto-repair (placeholder mismatches, HTML tags)
- Statistics, progress tracking, and completion metrics
- Persistent caching system to reduce API calls and costs
- Batch operations for single or multiple languages

Key Features:
- Interactive mode: User-friendly guided workflow perfect for non-technical users
- Auto-translate: Intelligent batch translation with configurable service selection
- Batch Operations: Most commands support operating on all languages when no language specified
- Validation: Automatic detection and fixing of common translation issues
- Smart Caching: Persistent cache reduces API calls and translation costs
- Configuration: Customizable timeouts, retries, and concurrency limits
- Error Handling: Robust error recovery with automatic backups and rollback

Command Types:
1. INTERACTIVE MODE - Recommended for new users:
   python translation_helper.py --interactive

2. BASIC COMMANDS - Check and validate translations:
   python translation_helper.py check [language]              # Check specific or all languages
   python translation_helper.py stats                         # Statistics for all languages
   python translation_helper.py validate [language]           # Validate specific or all languages

3. MAINTENANCE COMMANDS:
   python translation_helper.py update-ts [language]          # Update .ts files with new strings
   python translation_helper.py compile [language]            # Compile to .qm format

4. ADVANCED COMMANDS - Auto-translate with services:
   python translation_helper.py auto-translate [language] --service google|deepl|openai
   python translation_helper.py process [language] --service google|deepl|openai

Note: When [language] parameter is omitted, most commands operate on ALL languages
(except en_US source). Use --json flag for structured output in check/stats commands.

Examples:
  # Interactive mode (easiest for new users)
  python translation_helper.py --interactive

  # Check specific language
  python translation_helper.py check zh_CN

  # Check all languages at once
  python translation_helper.py check

  # Auto-translate specific language with Google (free)
  python translation_helper.py auto-translate zh_CN --service google

  # Auto-translate all languages with DeepL (requires API key)
  python translation_helper.py auto-translate --service deepl --api-key YOUR_KEY

  # Full workflow: update → validate → translate → compile (one language)
  python translation_helper.py process zh_CN --service google

  # Full workflow for all languages
  python translation_helper.py process --service google

For detailed usage and advanced options, see docs/development-guide/translation-guide.md
"""

import argparse
import asyncio
import hashlib
import importlib
import json
import re
import shutil
import subprocess
import sys
import types
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TypedDict, cast

# Global variables for caching and configuration
import aiohttp
import lxml.etree as ET

# Try to import googletrans library (optional dependency)
try:
    from googletrans import Translator as GoogleTranslator  # type: ignore
except ImportError:
    GoogleTranslator = None

# Try to import openai library (optional dependency)
openai_module: Optional[types.ModuleType]
try:
    openai_module = importlib.import_module("openai")
except ImportError:
    openai_module = None


@dataclass
class RetryConfig:
    """Configuration for retry mechanisms with exponential backoff.

    Controls automatic retry behavior for transient API failures with configurable
    delays that increase exponentially with each retry attempt.

    Attributes:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Starting delay in seconds between retries (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 30.0)
        exponential_base: Base for exponential backoff calculation (default: 2.0)
    """

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number using exponential backoff.

        Formula: initial_delay * (exponential_base ** attempt), capped at max_delay

        Args:
            attempt: The current attempt number (0-indexed)

        Returns:
            Delay in seconds to wait before the next retry
        """
        # Calculate exponential backoff: each retry waits longer than the previous one
        # This prevents overwhelming the API and helps transient errors recover
        # Example: initial=1.0, base=2.0 gives: 1s, 2s, 4s, 8s, 16s...
        delay = self.initial_delay * (self.exponential_base**attempt)
        # Cap at max_delay to prevent unreasonably long wait times
        return min(delay, self.max_delay)


@dataclass
class TimeoutConfig:
    """Configuration for request timeouts per service.

    Defines timeout values (in seconds) for different translation services.
    Helps prevent hanging requests and allows graceful fallback/retry.

    Attributes:
        default_timeout: Fallback timeout for unspecified services (default: 10.0s)
        deepl_timeout: Timeout for DeepL API requests (default: 10.0s)
        openai_timeout: Timeout for OpenAI API requests (default: 10.0s)
        google_timeout: Timeout for Google Translate requests (default: 10.0s)
    """

    default_timeout: float = 10.0
    deepl_timeout: float = 10.0
    openai_timeout: float = 10.0
    google_timeout: float = 10.0


@dataclass
class TranslationConfig:
    """Global configuration for translation operations.

    Centralizes all configuration settings for the translation system including
    retry behavior, timeouts, and concurrency limits. Allows runtime customization
    of translation behavior without code changes.

    Attributes:
        retry_config: Configuration for retry mechanisms with exponential backoff
        timeout_config: Configuration for service-specific request timeouts
        max_concurrent_requests: Maximum number of concurrent translation requests (default: 5)
    """

    retry_config: RetryConfig = field(default_factory=RetryConfig)
    timeout_config: TimeoutConfig = field(default_factory=TimeoutConfig)
    max_concurrent_requests: int = 5
    use_cache: bool = True

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "TranslationConfig":
        """Create TranslationConfig from a dictionary.

        Args:
            config_dict: Dictionary with keys 'retry', 'timeout', 'max_concurrent_requests'

        Returns:
            TranslationConfig instance with settings from the dictionary
        """
        retry_config = RetryConfig(**config_dict.get("retry", {}))
        timeout_config = TimeoutConfig(**config_dict.get("timeout", {}))
        max_concurrent = config_dict.get("max_concurrent_requests", 5)
        use_cache = config_dict.get("use_cache", True)
        return cls(retry_config, timeout_config, max_concurrent, use_cache)


# Global configuration instance
_translation_config = TranslationConfig()


def get_translation_config() -> TranslationConfig:
    """Get the global translation configuration."""
    return _translation_config


def set_translation_config(config: TranslationConfig) -> None:
    """Set the global translation configuration."""
    global _translation_config
    _translation_config = config


@dataclass
class TranslationCache:
    """Cache for translation results to avoid redundant API calls.

    Implements a simple hash-based cache to store successful translations.
    Reduces API calls and costs by reusing previously translated strings.
    The cache is persistent and stored in a file (`.translation_cache.json`)
    to be reused across runs.

    Attributes:
        _cache: Internal dictionary storing cached translations
        _cache_file: Optional file path for persistent cache
    """

    _cache: Dict[str, str] = field(default_factory=dict)
    _cache_file: Optional[Path] = None
    _loaded: bool = field(init=False, default=False)

    def _load_if_needed(self) -> None:
        """Load the cache from disk if it hasn't been loaded yet."""
        if self._loaded:
            return
        self._loaded = True

        config = get_translation_config()
        if not config.use_cache:
            print("ℹ️  Cache is disabled for this run.")
            return

        if self._cache_file and self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                print(
                    f"✅ Loaded {len(self._cache)} items from cache file: {self._cache_file}"
                )
            except (IOError, json.JSONDecodeError) as e:
                print(f"⚠️  Could not load cache file: {e}")
                self._cache = {}

    def save(self) -> None:
        """Save cache to file."""
        config = get_translation_config()
        if not config.use_cache:
            return
        if self._cache_file:
            try:
                self._cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._cache_file, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f, indent=2)
                print(
                    f"💾 Saved {len(self._cache)} items to cache file: {self._cache_file}"
                )
            except IOError as e:
                print(f"❌ Could not save cache file: {e}")

    def _get_cache_key(
        self, text: str, target_lang: str, source_lang: str, service: str
    ) -> str:
        """Generate a unique cache key from translation parameters.

        Uses SHA256 hash to create a compact, deterministic key from the
        text and language/service combination.

        Args:
            text: The text to translate
            target_lang: Target language code
            source_lang: Source language code
            service: Translation service name

        Returns:
            SHA256 hex digest as cache key
        """
        # Create a unique key by combining all parameters with delimiter
        # Using SHA256 ensures: deterministic output, fixed length (64 chars),
        # and minimal collision probability for different translations
        key_str = f"{text}:{target_lang}:{source_lang}:{service}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(
        self, text: str, target_lang: str, source_lang: str, service: str
    ) -> Optional[str]:
        """Retrieve a translation from cache if available.

        Args:
            text: The text to look up
            target_lang: Target language code
            source_lang: Source language code
            service: Translation service name

        Returns:
            Cached translation if found, None otherwise
        """
        self._load_if_needed()
        key = self._get_cache_key(text, target_lang, source_lang, service)
        return self._cache.get(key)

    def set(
        self,
        text: str,
        target_lang: str,
        source_lang: str,
        service: str,
        translation: str,
    ) -> None:
        """Store a translation in cache.

        Args:
            text: The text that was translated
            target_lang: Target language code
            source_lang: Source language code
            service: Translation service name
            translation: The translated text to cache
        """
        self._load_if_needed()
        key = self._get_cache_key(text, target_lang, source_lang, service)
        self._cache[key] = translation

    def clear(self) -> None:
        """Clear all cached translations and remove the cache file."""
        self._cache.clear()
        if self._cache_file and self._cache_file.exists():
            try:
                self._cache_file.unlink()
                print(f"🗑️ Cache file removed: {self._cache_file}")
            except IOError as e:
                print(f"❌ Could not remove cache file: {e}")

    def size(self) -> int:
        """Get the number of cached translations.

        Returns:
            Number of entries in the cache
        """
        self._load_if_needed()
        return len(self._cache)


# Global cache instance
_translation_cache = TranslationCache(
    _cache_file=Path(__file__).parent / ".translation_cache.json"
)


def get_translation_cache() -> TranslationCache:
    """Get the global translation cache."""
    return _translation_cache


def clear_translation_cache() -> None:
    """Clear the global translation cache."""
    _translation_cache.clear()


# === Input Validation ===
def validate_language_code(language: Optional[str]) -> Optional[str]:
    """Validate and normalize a language code.

    Ensures the language code is in the supported list and properly formatted.

    Args:
        language: Language code to validate (e.g., 'zh_CN'). If None, returns None.

    Returns:
        Normalized language code if valid, None if language is None

    Raises:
        ValueError: If language is not in the supported language map
    """
    if language is None:
        return None

    if language not in LANG_MAP:
        supported = ", ".join(sorted(LANG_MAP.keys()))
        raise ValueError(
            f"Unsupported language: {language}\nSupported languages: {supported}"
        )

    return language


def validate_file_path(file_path: Path) -> Path:
    """Validate that a file path exists and is readable.

    Ensures the file is accessible and not a directory.

    Args:
        file_path: Path to validate

    Returns:
        The validated path

    Raises:
        FileNotFoundError: If file does not exist
        IsADirectoryError: If path points to a directory
        PermissionError: If file is not readable
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_path.is_dir():
        raise IsADirectoryError(f"Path is a directory, not a file: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a regular file: {file_path}")

    # Check if file is readable
    if not file_path.stat().st_mode & 0o400:
        raise PermissionError(f"File is not readable: {file_path}")

    return file_path


def validate_directory_path(dir_path: Path) -> Path:
    """Validate that a directory path exists and is accessible.

    Ensures the directory exists and is writable (for file operations).

    Args:
        dir_path: Directory path to validate

    Returns:
        The validated path

    Raises:
        FileNotFoundError: If directory does not exist
        NotADirectoryError: If path is not a directory
        PermissionError: If directory is not writable
    """
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {dir_path}")

    if not dir_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {dir_path}")

    # Check if directory is writable
    if not dir_path.stat().st_mode & 0o200:
        raise PermissionError(f"Directory is not writable: {dir_path}")

    return dir_path


def validate_api_key(api_key: Optional[str], service: str) -> str:
    """Validate API key for a translation service.

    Ensures API key is provided and meets minimum format requirements.

    Args:
        api_key: The API key to validate
        service: Name of the service (for error messages)

    Returns:
        The validated API key

    Raises:
        ValueError: If API key is missing or invalid
    """
    if not api_key:
        raise ValueError(f"{service} requires a valid API key")

    if not isinstance(api_key, str):
        raise TypeError(f"API key must be a string, got {type(api_key)}")

    api_key = api_key.strip()

    if len(api_key) < 5:
        raise ValueError(f"{service} API key appears invalid (too short)")

    return api_key


def validate_model_name(model: Optional[str]) -> str:
    """Validate OpenAI model name.

    Ensures model name is provided and properly formatted.

    Args:
        model: Model name to validate (e.g., 'gpt-3.5-turbo')

    Returns:
        The validated model name

    Raises:
        ValueError: If model name is invalid
    """
    if model is None:
        return "gpt-3.5-turbo"  # Default

    if not isinstance(model, str):
        raise TypeError(f"Model name must be a string, got {type(model)}")

    model = model.strip()

    if not model:
        raise ValueError("Model name cannot be empty")

    if not re.match(r"^[a-zA-Z0-9\-_.]+$", model):
        raise ValueError(f"Invalid model name format: {model}")

    return model


def validate_timeout(timeout: float) -> float:
    """Validate timeout value in seconds.

    Ensures timeout is a positive number within reasonable bounds.

    Args:
        timeout: Timeout in seconds

    Returns:
        The validated timeout value

    Raises:
        ValueError: If timeout is invalid
        TypeError: If timeout is not a number
    """
    if not isinstance(timeout, (int, float)):
        raise TypeError(f"Timeout must be a number, got {type(timeout)}")

    if timeout <= 0:
        raise ValueError(f"Timeout must be positive, got {timeout}")

    if timeout > 300:
        raise ValueError(f"Timeout is very large ({timeout}s), max recommended is 300s")

    return float(timeout)


def validate_retry_count(max_retries: int) -> int:
    """Validate maximum retry count.

    Ensures retry count is non-negative and within reasonable bounds.

    Args:
        max_retries: Maximum number of retries

    Returns:
        The validated retry count

    Raises:
        ValueError: If retry count is invalid
        TypeError: If retry count is not an integer
    """
    if not isinstance(max_retries, int):
        raise TypeError(f"Retry count must be an integer, got {type(max_retries)}")

    if max_retries < 0:
        raise ValueError(f"Retry count cannot be negative, got {max_retries}")

    if max_retries > 10:
        raise ValueError(
            f"Retry count is very high ({max_retries}), max recommended is 10"
        )

    return max_retries


def validate_concurrent_requests(max_concurrent: int) -> int:
    """Validate maximum concurrent requests setting.

    Ensures concurrency is a positive integer within reasonable bounds.

    Args:
        max_concurrent: Maximum number of concurrent requests

    Returns:
        The validated concurrency value

    Raises:
        ValueError: If value is invalid
        TypeError: If value is not an integer
    """
    if not isinstance(max_concurrent, int):
        raise TypeError(
            f"Concurrent requests must be an integer, got {type(max_concurrent)}"
        )

    if max_concurrent <= 0:
        raise ValueError(f"Concurrent requests must be positive, got {max_concurrent}")

    if max_concurrent > 100:
        raise ValueError(
            f"Concurrent requests is very high ({max_concurrent}), max recommended is 100"
        )

    return max_concurrent


class LangMapEntry(TypedDict, total=False):
    google: Optional[str]
    deepl: Optional[str]
    openai: Optional[str]


# Global language map for all supported languages
LANG_MAP: Dict[str, LangMapEntry] = {
    "zh_CN": {"google": "zh-cn", "deepl": "ZH", "openai": "Simplified Chinese"},
    "zh_TW": {"google": "zh-tw", "deepl": "ZH", "openai": "Traditional Chinese"},
    "en_US": {"google": "en", "deepl": "EN", "openai": "English"},
    "ja_JP": {"google": "ja", "deepl": "JA", "openai": "Japanese"},
    "ko_KR": {"google": "ko", "deepl": "KO", "openai": "Korean"},
    "fr_FR": {"google": "fr", "deepl": "FR", "openai": "French"},
    "de_DE": {"google": "de", "deepl": "DE", "openai": "German"},
    "es_ES": {"google": "es", "deepl": "ES", "openai": "Spanish"},
    "ru_RU": {"google": "ru", "deepl": None, "openai": None},
    "tr_TR": {"google": "tr", "deepl": None, "openai": None},
    "pt_BR": {"google": "pt", "deepl": None, "openai": None},
}


def get_language_code(lang_code: str, service: str) -> str:
    """Get the appropriate language code for a specific translation service."""
    entry: Optional[LangMapEntry] = LANG_MAP.get(lang_code)
    if entry and isinstance(entry, dict):
        code = cast(Optional[str], entry.get(service))
        if isinstance(code, str):
            return code

    # Fallback: convert underscores to hyphens for Google, uppercase for DeepL, or use as-is
    if service == "google":
        return lang_code.lower().replace("_", "-")
    elif service == "deepl":
        return lang_code.upper()
    else:
        return lang_code


async def retry_with_backoff(
    async_func: Any, *args: Any, config: Optional[RetryConfig] = None, **kwargs: Any
) -> Optional[Any]:
    """
    Retry an async function with exponential backoff.

    Args:
        async_func: The async function to call
        *args: Positional arguments for the function
        config: RetryConfig instance (uses global config if None)
        **kwargs: Keyword arguments for the function

    Returns:
        Result from the function or None if all retries failed
    """
    # Use provided config or fall back to global configuration
    if config is None:
        config = get_translation_config().retry_config

    # Attempt execution up to max_retries times
    for attempt in range(config.max_retries):
        try:
            # Try to execute the async function with provided arguments
            return await async_func(*args, **kwargs)
        except Exception as e:
            # Check if we have more retries available
            if attempt < config.max_retries - 1:
                # Calculate exponential backoff delay
                delay = config.get_delay(attempt)
                print(
                    f"⚠️  Attempt {attempt + 1} failed, retrying in {delay:.1f}s: {str(e)[:100]}"
                )
                # Wait before next attempt (prevents API rate limiting)
                await asyncio.sleep(delay)
            else:
                # All retries exhausted, log final failure
                print(f"❌ All {config.max_retries} retry attempts failed")

    # Return None if all attempts failed
    return None


def print_dry_run_summary(title: str) -> None:
    """Print a formatted dry-run summary header."""
    print(f"\n{'=' * 60}")
    print(f"📋 DRY-RUN PREVIEW: {title}")
    print(f"{'=' * 60}")


# === Translation Services ===
class TranslationService:
    """Abstract base class for translation service implementations.

    Defines the interface that all translation service adapters must implement.
    Subclasses provide concrete implementations for specific translation APIs
    (Google Translate, DeepL, OpenAI, etc.).
    """

    async def translate(
        self, text: str, target_lang: str, source_lang: str = "en_US"
    ) -> Optional[str]:
        """Translate text from source language to target language.

        Args:
            text: The text to translate
            target_lang: Target language code (e.g., 'zh_CN', 'fr_FR')
            source_lang: Source language code (default: 'en_US')

        Returns:
            Translated text if successful, None if translation failed
        """
        raise NotImplementedError


class GoogleTranslateService(TranslationService):
    """Google Translate service implementation with exponential backoff retry.

    Uses the free googletrans library to provide translation capabilities.
    Includes automatic retry logic with exponential backoff for handling
    transient failures and rate limiting.

    Attributes:
        translator: The googletrans Translator instance
        config: Global translation configuration with retry settings
    """

    def __init__(self) -> None:
        """Initialize Google Translate service.

        Raises:
            ImportError: If googletrans library is not installed
        """
        if GoogleTranslator is None:
            raise ImportError("googletrans library not available")
        assert GoogleTranslator is not None
        self.translator = GoogleTranslator()
        self.config = get_translation_config()
        self._setup_translator()

    def _setup_translator(self) -> None:
        """Configure translator session properties (e.g., SSL verification)."""
        # This is a workaround for a common issue with googletrans library where
        # SSL verification fails. By accessing the internal session and setting
        # verify to False, we can bypass these errors.
        try:
            session = getattr(self.translator, "_session", None)
            if session:
                session.verify = False
        except AttributeError:
            # If the session object doesn't exist, we can't configure it.
            # This is not a critical error, so we can safely ignore it.
            pass

    async def translate(
        self, text: str, target_lang: str, source_lang: str = "en_US"
    ) -> Optional[str]:
        config = get_translation_config()
        cache = get_translation_cache()

        if config.use_cache:
            cached = cache.get(text, target_lang, source_lang, "google")
            if cached is not None:
                return cached

        target_entry: Optional[LangMapEntry] = LANG_MAP.get(target_lang)
        target = target_entry.get("google") if target_entry else None
        if not target:
            target = target_lang.lower().replace("_", "-")

        source_entry: Optional[LangMapEntry] = LANG_MAP.get(source_lang)
        source = source_entry.get("google") if source_entry else None
        if not source:
            source = source_lang.lower().replace("_", "-")

        for attempt in range(self.config.retry_config.max_retries):
            try:
                # The googletrans 4.0.0rc1 library has an async translate method
                result: Any = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.translator.translate(text, dest=target, src=source),
                )

                translation = result.text if hasattr(result, "text") else str(result)

                if translation and config.use_cache:
                    cache.set(text, target_lang, source_lang, "google", translation)

                return translation
            except Exception as e:
                error_str = str(e)
                if attempt < self.config.retry_config.max_retries - 1:
                    if (
                        "SSL" in error_str
                        or "TLS" in error_str
                        or "sslv3" in error_str.lower()
                    ):
                        # Re-instantiate translator on SSL errors
                        assert GoogleTranslator is not None
                        self.translator = GoogleTranslator()
                        self._setup_translator()

                    delay = self.config.retry_config.get_delay(attempt)
                    print(
                        f"⚠️  Google translate attempt {attempt + 1} failed, retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    print(f"❌ Google translate failed: {e}")
                    return None
        return None


class DeepLService(TranslationService):
    """DeepL translation service with configurable timeouts and retry logic.

    Provides high-quality neural machine translation using DeepL's API.
    Supports both synchronous and asynchronous translation with configurable
    timeouts and automatic retry logic on transient failures.

    Attributes:
        api_key: DeepL API key for authentication
        base_url: DeepL API endpoint URL (free tier)
        config: Global translation configuration with timeout settings
    """

    def __init__(self, api_key: str) -> None:
        """Initialize DeepL service.

        Args:
            api_key: Your DeepL API key (required for authentication)
        """
        self.api_key = api_key
        self.base_url = "https://api-free.deepl.com/v2/translate"
        self.config = get_translation_config()

    async def translate(
        self, text: str, target_lang: str, source_lang: str = "en_US"
    ) -> Optional[str]:
        # First, check if the translation is already in the cache.
        config = get_translation_config()
        cache = get_translation_cache()

        if config.use_cache:
            cached = cache.get(text, target_lang, source_lang, "deepl")
            if cached is not None:
                # If found, return the cached translation.
                return cached

        # Get the language code for the target language from the LANG_MAP.
        target_entry: Optional[LangMapEntry] = LANG_MAP.get(target_lang)
        target: Optional[str] = None
        if target_entry is not None:
            target = target_entry.get("deepl")
        if not target:
            # If the language code is not in the map, use a fallback.
            target = target_lang.upper()

        # Get the language code for the source language from the LANG_MAP.
        source_entry: Optional[LangMapEntry] = LANG_MAP.get(source_lang)
        source: Optional[str] = None
        if source_entry is not None:
            source = source_entry.get("deepl")
        if not source:
            # If the language code is not in the map, use a fallback.
            source = source_lang.upper()

        # The data to be sent to the DeepL API.
        data = {
            "auth_key": self.api_key,
            "text": text,
            "target_lang": target,
            "source_lang": source,
        }

        # Retry the translation up to the configured number of times.
        for attempt in range(self.config.retry_config.max_retries):
            try:
                # Set the timeout for the request.
                timeout = aiohttp.ClientTimeout(
                    total=self.config.timeout_config.deepl_timeout
                )
                # Create a new aiohttp session for each request.
                async with aiohttp.ClientSession() as session:
                    # Send the request to the DeepL API.
                    async with session.post(
                        self.base_url, data=data, timeout=timeout
                    ) as response:
                        # Raise an exception if the request fails.
                        response.raise_for_status()
                        # Get the JSON response.
                        result = await response.json()
                        # The translation is in the 'translations' list.
                        translation = result["translations"][0]["text"]
                        # Cache the translation.
                        if config.use_cache:
                            cache.set(
                                text, target_lang, source_lang, "deepl", translation
                            )
                        return translation
            except asyncio.TimeoutError:
                # If the request times out, check if we should retry.
                if attempt < self.config.retry_config.max_retries - 1:
                    # Calculate the delay for the next retry.
                    delay = self.config.retry_config.get_delay(attempt)
                    print(
                        f"⚠️  DeepL timeout, retrying in {delay:.1f}s: Request {text[:50]}..."
                    )
                    # Wait for the calculated delay.
                    await asyncio.sleep(delay)
                else:
                    # If all retries fail, print an error message.
                    print(
                        f"❌ DeepL translation timed out after {self.config.retry_config.max_retries} attempts"
                    )
                    return None
            except Exception as e:
                # If the request fails, check if we should retry.
                if attempt < self.config.retry_config.max_retries - 1:
                    # Calculate the delay for the next retry.
                    delay = self.config.retry_config.get_delay(attempt)
                    print(
                        f"⚠️  DeepL attempt {attempt + 1} failed, retrying in {delay:.1f}s"
                    )
                    # Wait for the calculated delay.
                    await asyncio.sleep(delay)
                else:
                    # If all retries fail, print an error message.
                    print(f"❌ DeepL translation failed: {e}")
                    return None
        # If the translation fails, return None.
        return None


class OpenAIService(TranslationService):
    """OpenAI GPT translation service with configurable timeouts and retry logic.

    Uses OpenAI's language models (GPT-3.5-turbo or better) to provide context-aware
    translations. Ideal for UI text where quality and naturalness are important.
    Supports configurable models and automatic retry with exponential backoff.

    Attributes:
        client: OpenAI API client instance
        model: The model to use for translation (default: 'gpt-3.5-turbo')
        config: Global translation configuration with timeout settings
    """

    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo") -> None:
        """Initialize OpenAI translation service.

        Args:
            api_key: Your OpenAI API key (required for authentication)
            model: The model to use for translation. Defaults to 'gpt-3.5-turbo'.
                   Other options: 'gpt-4', 'gpt-4-turbo-preview', etc.

        Raises:
            ImportError: If OpenAI library is not installed
        """
        if openai_module is None:
            raise ImportError("openai library not available")
        self.config = get_translation_config()
        self.client = openai_module.OpenAI(
            api_key=api_key,
            timeout=self.config.timeout_config.openai_timeout,
        )
        self.model = model

    async def translate(
        self, text: str, target_lang: str, source_lang: str = "en_US"
    ) -> Optional[str]:
        assert openai_module is not None

        config = get_translation_config()
        cache = get_translation_cache()
        # First, check if the translation is already in the cache.
        if config.use_cache:
            cached = cache.get(text, target_lang, source_lang, "openai")
            if cached is not None:
                # If found, return the cached translation.
                return cached

        # Get the language name for the target language from the LANG_MAP.
        target_entry: Optional[LangMapEntry] = LANG_MAP.get(target_lang)
        target_name: Optional[str] = None
        if target_entry is not None:
            target_name = target_entry.get("openai")
        if not target_name:
            # If the language name is not in the map, use the language code.
            target_name = target_lang

        # Get the language name for the source language from the LANG_MAP.
        source_entry: Optional[LangMapEntry] = LANG_MAP.get(source_lang)
        source_name: Optional[str] = None
        if source_entry is not None:
            source_name = source_entry.get("openai")
        if not source_name:
            # If the language name is not in the map, use the language code.
            source_name = source_lang

        # The prompt to be sent to the OpenAI API.
        prompt = """Translate the following {} text to {}.
This is UI text from a software application. Keep it concise and user-friendly.
Only return the translation, no explanation:

{}""".format(source_name, target_name, text)

        # Retry the translation up to the configured number of times.
        for attempt in range(self.config.retry_config.max_retries):
            try:
                # Send the request to the OpenAI API.
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200,
                    temperature=0.1,
                )
                # The translation is in the 'content' of the first choice.
                translation = response.choices[0].message.content.strip()
                # Cache the translation.
                if config.use_cache:
                    cache.set(text, target_lang, source_lang, "openai", translation)
                return translation
            except Exception as e:
                # If the request fails, check if we should retry.
                error_str = str(e).lower()
                is_timeout = "timeout" in error_str

                if attempt < self.config.retry_config.max_retries - 1:
                    # Calculate the delay for the next retry.
                    delay = self.config.retry_config.get_delay(attempt)
                    if is_timeout:
                        print(
                            f"⚠️  OpenAI timeout, retrying in {delay:.1f}s: Request {text[:50]}..."
                        )
                    else:
                        print(
                            f"⚠️  OpenAI attempt {attempt + 1} failed, retrying in {delay:.1f}s"
                        )
                    # Wait for the calculated delay.
                    await asyncio.sleep(delay)
                else:
                    # If all retries fail, print an error message.
                    if is_timeout:
                        print(
                            f"❌ OpenAI translation timed out after {self.config.retry_config.max_retries} attempts"
                        )
                    else:
                        print(f"❌ OpenAI translation failed: {e}")
                    return None
        # If the translation fails, return None.
        return None


# === Existing Helper Functions ===
def get_source_keys_from_file(source_file: Path) -> Set[str]:
    """Extract all translation keys from source language file."""
    try:
        tree = ET.parse(source_file)
        root = tree.getroot()

        if root is None:
            return set()

        keys = set()
        for context in root.findall("context"):
            name_element = context.find("name")
            context_name = name_element.text if name_element is not None else "Unknown"

            for message in context.findall("message"):
                source = message.find("source")
                if source is not None and source.text:
                    # Create unique key from context + source
                    key = f"{context_name}::{source.text}"
                    keys.add(key)

        return keys
    except Exception:
        return set()


def get_source_keys(unfinished: list["UnfinishedItem"]) -> Dict[str, List[str]]:
    """Get source keys grouped by context from unfinished items."""
    result: Dict[str, List[str]] = {}
    for item in unfinished:
        if item.context not in result:
            result[item.context] = []
        result[item.context].append(item.source)
    return result


def parse_ts_file(
    file_path: Path, source_keys: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """Parse a .ts file and extract translation information."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        if root is None:
            return {"error": "Root element is None"}

        stats = {
            "total": 0,
            "translated": 0,
            "unfinished": 0,
            "obsolete": 0,
            "missing": 0,
        }

        issues = []
        translated_keys = set()

        for context in root.findall("context"):
            name_element = context.find("name")
            context_name = name_element.text if name_element is not None else "Unknown"

            for message in context.findall("message"):
                stats["total"] += 1

                source = message.find("source")
                translation = message.find("translation")

                source_text = source.text if source is not None and source.text else ""
                translated_keys.add(f"{context_name}::{source_text}")

                if translation is not None:
                    translation_type = translation.get("type")
                    translation_text = translation.text or ""

                    if translation_type == "unfinished":
                        stats["unfinished"] += 1
                        stats["missing"] += 1
                        issues.append(
                            f"Unfinished: {context_name} - {source_text[:50]}..."
                        )
                    elif translation_type == "obsolete":
                        stats["obsolete"] += 1
                    elif not translation_text.strip():
                        stats["missing"] += 1
                        issues.append(
                            f"Empty translation: {context_name} - {source_text[:50]}..."
                        )
                    else:
                        stats["translated"] += 1
                else:
                    stats["missing"] += 1
                    issues.append(
                        f"Missing translation tag: {context_name} - {source_text[:50]}..."
                    )

        # Calculate missing keys based on source language
        if source_keys:
            missing_keys = source_keys - translated_keys
            stats["missing_from_source"] = len(missing_keys)

            for key in list(missing_keys)[:5]:  # Show first 5 missing keys
                context_key, source_text_key = key.split("::", 1)
                issues.append(
                    f"Missing from source: {context_key} - {source_text_key[:50]}..."
                )

        return {
            "stats": stats,
            "issues": issues,
            "language": root.get("language", "unknown"),
        }

    except Exception as e:
        return {"error": str(e)}


# === New Auto-Translation Functions ===
@dataclass
class UnfinishedItem:
    context: str
    source: str
    element: Any


def find_unfinished_translations(
    tree: Any,
) -> List[UnfinishedItem]:
    """Find all unfinished translation entries in a .ts file.

    Searches through the XML structure to identify entries that are either:
    - Marked as type="unfinished"
    - Have empty translation text

    Args:
        tree: Parsed XML ElementTree from a .ts file

    Returns:
        List of UnfinishedItem objects containing context, source text, and element reference
    """
    unfinished: list[UnfinishedItem] = []
    root = tree.getroot()

    if root is None:
        return []

    for context in root.findall("context"):
        context_name = context.findtext("name") or "Unknown"

        for msg in context.findall("message"):
            src_elem = msg.find("source")
            tr_elem = msg.find("translation")
            if src_elem is None or tr_elem is None:
                continue

            src_text = (src_elem.text or "").strip()
            tr_text = (tr_elem.text or "").strip()
            tr_type = (tr_elem.get("type") or "").strip()

            if tr_type == "unfinished" or not tr_text:
                unfinished.append(
                    UnfinishedItem(
                        context=context_name.strip(),
                        source=src_text,
                        element=tr_elem,
                    )
                )

    return unfinished


def should_skip_translation(text: str) -> bool:
    """Determine if a text should be skipped during translation.

    Skips empty strings, single characters, numbers, and pure symbols
    as these typically don't need translation.

    Args:
        text: The text to evaluate for skipping

    Returns:
        True if the text should be skipped, False otherwise
    """
    if not text.strip():
        return True
    if len(text.strip()) <= 1:
        return True
    if text.isdigit():
        return True
    if re.match(r"^[^\w\s]+$", text):
        return True
    return False


def create_translation_service(service_name: str, **kwargs: Any) -> TranslationService:
    """Create a translation service instance based on the specified service name.

    Factory function to instantiate the appropriate translation service with
    its required configuration and credentials.

    Args:
        service_name: Name of the translation service ('google', 'deepl', or 'openai')
        **kwargs: Service-specific configuration:
            - For 'google': no additional arguments required
            - For 'deepl': api_key (required)
            - For 'openai': api_key (required), model (optional, default: 'gpt-3.5-turbo')

    Returns:
        TranslationService: An instance of the requested translation service

    Raises:
        ImportError: If the required library is not installed (e.g., googletrans)
        ValueError: If required arguments are missing or service name is invalid
    """
    if service_name == "google":
        if GoogleTranslator is None:
            raise ImportError(
                "googletrans not available. Install with: pip install googletrans==4.0.0rc1"
            )
        return GoogleTranslateService()

    elif service_name == "deepl":
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("DeepL requires API key")
        return DeepLService(api_key)

    elif service_name == "openai":
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("OpenAI requires API key")
        model = kwargs.get("model", "gpt-3.5-turbo")
        return OpenAIService(api_key, model)
    else:
        raise ValueError(f"Unsupported service: {service_name}")


async def auto_translate_file(
    language: Optional[str],
    service_name: str = "google",
    continue_on_failure: bool = True,
    dry_run: bool = False,
    **service_kwargs: Any,
) -> bool:
    """Auto-translate unfinished strings in a .ts file or all if language is None.

    Args:
        language: Language code to translate (None for all)
        service_name: Translation service (google, deepl, openai)
        continue_on_failure: Continue if some translations fail
        dry_run: Preview changes without saving files
        **service_kwargs: Additional arguments for translation service

    Returns:
        True if successful, False otherwise
    """
    locales_dir = Path("locales")

    # Determine which languages to process
    languages: List[str] = []
    if language:
        # If a language is specified, process only that one.
        languages = [language]
    else:
        # If no language specified, process all .ts files except source (en_US)
        languages = [f.stem for f in locales_dir.glob("*.ts") if f.stem != "en_US"]

    all_success = True

    for lang in languages:
        ts_file = locales_dir / f"{lang}.ts"

        if not ts_file.exists():
            print(f"❌ Translation file not found: {ts_file}")
            all_success = False
            continue

        # Create a backup copy (unless in dry-run mode) to enable rollback on failure
        backup_file = ts_file.with_suffix(".ts.backup")
        if not dry_run:
            shutil.copy2(ts_file, backup_file)
            print(f"📁 Backup created: {backup_file}")

        translation_failed_midway = False
        tree = None
        successful = 0  # Count of successfully translated items
        failed = 0  # Count of failed translation attempts

        try:
            # Initialize the translation service with configured API keys and settings
            service = create_translation_service(service_name, **service_kwargs)

            # Parse the .ts XML file to access translation entries
            tree = ET.parse(ts_file)
            # Find all unfinished or empty translation entries
            unfinished = find_unfinished_translations(tree)

            if not unfinished:
                print(f"✅ No unfinished translations found for {lang}!")
                continue

            print(f"🔍 Found {len(unfinished)} unfinished translations for {lang}")

            config = get_translation_config()
            # Semaphore limits concurrent API requests to prevent rate limiting/overload
            semaphore = asyncio.Semaphore(config.max_concurrent_requests)

            async def translate_item(
                i: int, item: UnfinishedItem
            ) -> tuple[int, UnfinishedItem, Optional[str]]:
                """Inner coroutine to translate a single item with concurrency control."""
                source_text = item.source
                # Skip trivial strings (empty, single char, numbers, symbols)
                if should_skip_translation(source_text):
                    print(f"⏭️  Skipping [{i}/{len(unfinished)}]: {source_text}")
                    return i, item, None

                # Use semaphore to limit concurrent API requests
                async with semaphore:
                    print(
                        f"🔄 Translating [{i}/{len(unfinished)}]: {source_text[:50]}..."
                    )
                    try:
                        # Call translation service with configured timeout
                        translated = await asyncio.wait_for(
                            service.translate(source_text, lang, "en_US"),
                            timeout=config.timeout_config.default_timeout,
                        )
                    except asyncio.TimeoutError:
                        print(f"❌ Translation timeout for [{i}]")
                        translated = ""  # Return empty string for failures
                    except Exception as e:
                        print(f"❌ Translation error for [{i}]: {e}")
                        translated = ""  # Return empty string for failures
                    return i, item, translated

            # Create concurrent tasks for all unfinished items
            tasks = [translate_item(i, item) for i, item in enumerate(unfinished, 1)]
            # Run all translation tasks concurrently and wait for completion
            results = await asyncio.gather(*tasks)

            # Process translation results and update XML elements
            for i, item, translated in results:
                if translated is None:
                    continue  # Skip items that were skipped or failed

                if translated and translated.strip():
                    if dry_run:
                        # In dry-run mode, show preview without updating elements or counting as successful
                        print(f"📝 [{i}] {item.source[:40]} → {translated[:40]}...")
                    else:
                        # Update the XML element with the translated text
                        item.element.text = translated
                        # Remove "unfinished" marker to mark as completed
                        if item.element.get("type") == "unfinished":
                            del item.element.attrib["type"]
                        print(f"✅ Success [{i}]: {translated[:50]}...")
                        successful += 1
                else:
                    print(f"❌ Failed to translate [{i}]: {item.source[:50]}...")
                    failed += 1
                    # Stop if continue_on_failure is False (abort on first failure)
                    if not continue_on_failure:
                        translation_failed_midway = True
                        break

        except Exception as e:
            print(f"⚠️  An unexpected error occurred during auto-translation: {e}")
            translation_failed_midway = True  # Mark as failed if an exception occurs

        finally:
            if dry_run:
                print("\n📋 DRY-RUN MODE (No changes saved):")
                print(f"   ✅ Would update: {successful} translations.")
                print(f"   ❌ Failed: {failed}")
                print(f"   📁 Would update file: {ts_file}")
                print("   💾 Use without --dry-run to apply changes")
                if failed > 0:
                    all_success = (
                        False  # Even in dry run, if failures, report overall failure
                    )
            elif tree is not None:
                if not translation_failed_midway and (
                    continue_on_failure or failed == 0
                ):
                    try:
                        # Save file
                        tree.write(ts_file, encoding="utf-8", xml_declaration=True)

                        # Fix DOCTYPE
                        with open(ts_file, "r", encoding="utf-8") as f:
                            content = f.read()

                        if "<!DOCTYPE TS>" not in content:
                            lines = content.split("\n")
                            lines.insert(1, "<!DOCTYPE TS>")
                            content = "\n".join(lines)

                        with open(ts_file, "w", encoding="utf-8") as f:
                            f.write(content)

                        print("\n📊 Auto-translation completed:")
                        print(f"   ✅ Successful: {successful}")
                        print(f"   ❌ Failed: {failed}")
                        print(f"   📁 File updated: {ts_file}")
                        # Remove backup if successful save
                        if backup_file.exists():
                            backup_file.unlink()
                            print(f"🗑️  Backup removed: {backup_file}")
                        # Save the cache
                        get_translation_cache().save()
                        if failed > 0:  # If continue_on_failure is True but some failed
                            all_success = False
                    except Exception as save_e:
                        print(f"❌ Error saving the file: {save_e}")
                        print(f"🔄 Restoring from backup: {backup_file}")
                        if backup_file.exists():
                            shutil.copy2(backup_file, ts_file)
                        all_success = False
                else:  # translation_failed_midway or (not continue_on_failure and failed > 0)
                    print(
                        "\n❌ Auto-translation aborted due to failure. Restoring from backup."
                    )
                    if backup_file.exists():
                        shutil.copy2(backup_file, ts_file)
                        # No need to unlink backup here, it's the working copy now
                    all_success = False

    return all_success


def run_lupdate(language: Optional[str] = None) -> bool:
    """Run pyside6-lupdate to update translation files with new strings.

    Extracts new translatable strings from Python source files and updates
    the corresponding .ts (translation source) files. Removes obsolete entries
    that are no longer needed.

    Args:
        language: Language code to update (e.g., 'zh_CN'). If None, updates all
                 .ts files in the locales directory

    Returns:
        True if lupdate succeeded, False otherwise

    Requires:
        PySide6-Essentials package installed (pyside6-lupdate command available)
    """
    try:
        # Check if pyside6-lupdate is available
        cmd = ["pyside6-lupdate"]

        # Find all Python source files in the app directory
        py_files = list(Path("app").rglob("*.py"))
        if not py_files:
            print("⚠️ No Python source files found under app/")
            return False

        cmd.extend(str(f) for f in py_files)

        # If a specific language is provided, update that .ts file
        if language:
            print(f"🔄 Updating translation file for {language}...")
            ts_file = Path("locales") / f"{language}.ts"
            cmd.extend(["-ts", str(ts_file), "-no-obsolete", "-locations", "none"])
        else:
            print("🔄 Updating all translation files...")
            locales_dir = Path("locales")
            ts_files = list(locales_dir.glob("*.ts"))
            if ts_files:
                cmd.extend(
                    ["-ts"]
                    + [str(f) for f in ts_files]
                    + ["-no-obsolete", "-locations", "none"]
                )
            else:
                print("⚠️ No .ts files found in locales/")
                return False

        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Translation files updated successfully!")
            return True
        else:
            print(f"❌ Error running lupdate:\n{result.stderr}")
            return False

    except FileNotFoundError:
        print("❌ pyside6-lupdate not found. Please install PySide6-Essentials.")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def run_lrelease(language: Optional[str] = None) -> bool:
    """Run pyside6-lrelease to compile translation files to binary format.

    Converts .ts (translation source) files to .qm (compiled translation) files
    that can be loaded by PySide6 applications at runtime.

    Args:
        language: Language code to compile (e.g., 'zh_CN'). If None, compiles all
                 .ts files in the locales directory

    Returns:
        True if lrelease succeeded, False otherwise

    Requires:
        PySide6-Essentials package installed (pyside6-lrelease command available)
    """
    try:
        locales_dir = Path("locales")
        if not locales_dir.exists():
            print("❌ Locales directory not found")
            return False

        if language:
            ts_file = locales_dir / f"{language}.ts"
            if not ts_file.exists():
                print(f"❌ Translation file not found: {ts_file}")
                return False

            print(f"🔄 Compiling translation for {language}...")
            cmd = ["pyside6-lrelease", str(ts_file)]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"✅ Translation compiled: {language}.qm")
                return True
            else:
                print(f"❌ Error compiling {language}: {result.stderr}")
                return False
        else:
            print("🔄 Compiling all translation files...")
            ts_files = list(locales_dir.glob("*.ts"))
            success_count = 0

            for ts_file in ts_files:
                cmd = ["pyside6-lrelease", str(ts_file)]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    print(f"✅ Compiled: {ts_file.stem}.qm")
                    success_count += 1
                else:
                    print(f"❌ Failed to compile {ts_file.stem}: {result.stderr}")

            print(f"📊 Compiled {success_count}/{len(ts_files)} translation files")
            return success_count > 0

    except FileNotFoundError:
        print("❌ pyside6-lrelease not found. Please install PySide6-Essentials.")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def check_translation(
    language: Optional[str] = None, json_output: bool = False
) -> None:
    """Check translation completeness for a specific language or all languages.

    Compares each translation file against the source language (en_US) to verify
    that all strings are present and translated. Outputs results in human-readable
    or JSON format for programmatic consumption.

    Args:
        language: Language code to check (e.g., 'zh_CN'). If None, checks all
                 languages except en_US
        json_output: If True, outputs results as JSON; otherwise uses human-readable format

    Output:
        Prints statistics including total strings, translated count, and completion
        percentage for each language. With json_output=True, outputs structured JSON
        with language, total, translated, and percentage fields.

    Raises:
        ValueError: If provided language is not supported
        FileNotFoundError: If locales directory does not exist
    """
    locales_dir: Path = Path("locales")

    # Validate locales directory exists
    try:
        validate_directory_path(locales_dir)
    except FileNotFoundError:
        error_msg = f"Locales directory not found: {locales_dir}"
        if json_output:
            print(json.dumps({"error": error_msg}, indent=2))
        else:
            print(f"❌ {error_msg}")
        return

    languages: List[str] = []
    if language:
        # Validate language code if provided
        try:
            validated_lang = validate_language_code(language)
            if validated_lang:
                languages = [validated_lang]
        except ValueError as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ {e}")
            return
    else:
        # All languages except en_US
        languages = [f.stem for f in locales_dir.glob("*.ts") if f.stem != "en_US"]

    source_file: Path = locales_dir / "en_US.ts"  # Assume en_US is source
    source_keys: Set[str] = set()
    if source_file.exists():
        source_keys = get_source_keys_from_file(source_file)
        if not json_output:
            print(f"📚 Found {len(source_keys)} keys in source language")

    results: List[Dict[str, Any]] = []

    for lang in languages:
        ts_file: Path = locales_dir / f"{lang}.ts"
        if not ts_file.exists():
            if json_output:
                results.append(
                    {"language": lang, "error": "Translation file not found"}
                )
            else:
                print(f"❌ Translation file not found: {ts_file}")
            continue

        if not json_output:
            print(f"🔍 Checking translation for {lang}...")

        # Parse the translation file to extract statistics and issues
        result: Dict[str, Any] = parse_ts_file(ts_file, source_keys)

        # Check if there was an error during parsing
        if "error" in result:
            if json_output:
                results.append({"language": lang, "error": result["error"]})
            else:
                print(f"❌ Error parsing file: {result['error']}")
            continue

        stats: Dict[str, Any] = result["stats"]
        issues: List[str] = result["issues"]

        # Calculate completion percentage: translated strings / total strings
        completion: float = (
            (stats["translated"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        )

        # Determine status level based on completion percentage
        status = (
            "complete"
            if completion >= 95
            else "mostly_complete"
            if completion >= 80
            else "partially_complete"
            if completion >= 50
            else "incomplete"
        )

        # Build result object with all relevant statistics
        lang_result: Dict[str, Any] = {
            "language": lang,
            "completion_percentage": round(completion, 1),
            "status": status,
            "stats": {
                "total": stats["total"],
                "translated": stats["translated"],
                "unfinished": stats["unfinished"],
                "missing": stats["missing"],
                "obsolete": stats["obsolete"],
            },
            "issues": issues,
        }

        results.append(lang_result)

        if not json_output:
            print("\n📊 Translation Statistics:")
            print(f"   Total strings: {stats['total']}")
            print(f"   Translated: {stats['translated']} ({completion:.1f}%)")
            print(f"   Unfinished: {stats['unfinished']}")
            print(f"   Missing: {stats['missing']}")
            print(f"   Obsolete: {stats['obsolete']}")

            if source_keys and "missing_from_source" in stats:
                print(f"   Missing from source: {stats['missing_from_source']}")

            if completion >= 95:
                print("✅ Translation is nearly complete!")
            elif completion >= 80:
                print("🟡 Translation is mostly complete")
            elif completion >= 50:
                print("🟠 Translation is partially complete")
            else:
                print("🔴 Translation needs significant work")

            if issues and len(issues) <= 10:
                print("\n⚠️  Issues found:")
                for issue in issues[:10]:
                    print(f"   • {issue}")
                if len(issues) > 10:
                    print(f"   ... and {len(issues) - 10} more issues")

    if json_output:
        print(json.dumps({"type": "check", "results": results}, indent=2))


def show_all_stats(json_output: bool = False) -> None:
    """Show comprehensive statistics for all available translations.

    Displays the total number of strings, completed translations, and other metrics
    across all language files. Provides both human-readable and JSON output options.

    Args:
        json_output: If True, outputs results as JSON; otherwise uses human-readable format
                    with visual indicators and color coding

    Output:
        Prints detailed statistics including string counts, completion percentages,
        and visual health indicators (green/yellow/red) for each language. With
        json_output=True, outputs structured JSON with comprehensive statistics.
    """
    locales_dir = Path("locales")
    if not locales_dir.exists():
        if json_output:
            print(
                json.dumps(
                    {"type": "stats", "error": "Locales directory not found"}, indent=2
                )
            )
        else:
            print("❌ Locales directory not found")
        return

    ts_files = list(locales_dir.glob("*.ts"))
    if not ts_files:
        if json_output:
            print(
                json.dumps(
                    {"type": "stats", "error": "No translation files found"}, indent=2
                )
            )
        else:
            print("❌ No translation files found")
        return

    # Get source keys
    source_file = locales_dir / "en_US.ts"
    source_keys: Set[str] = set()
    if source_file.exists():
        source_keys = get_source_keys_from_file(source_file)

    results: List[Dict[str, Any]] = []

    if not json_output:
        print("📊 Translation Statistics for All Languages:\n")
        print(f"Total files: {len(ts_files)}\n")
        print(
            f"{'Language':<10} {'Progress':<10} {'Translated':<12} {'Unfinished ':<12} {'Missing':<12} {'Status'}"
        )
        print("-" * 75)

    for ts_file in sorted(ts_files):
        language = ts_file.stem
        result = parse_ts_file(ts_file, source_keys if language != "en_US" else None)

        if "error" in result:
            if json_output:
                results.append(
                    {
                        "language": language,
                        "error": result["error"],
                    }
                )
            else:
                print(
                    f"{language:<10} {'ERROR':<10} {'N/A':<12} {'N/A':<10} {'N/A':<12} ❌"
                )
            continue

        stats = result["stats"]
        completion = (
            (stats["translated"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        )

        status = (
            "complete"
            if completion >= 95
            else "mostly_complete"
            if completion >= 80
            else "partially_complete"
            if completion >= 50
            else "incomplete"
        )

        missing_from_source = stats.get("missing_from_source", 0)

        lang_result = {
            "language": language,
            "completion_percentage": round(completion, 1),
            "status": status,
            "stats": {
                "total": stats["total"],
                "translated": stats["translated"],
                "unfinished": stats["unfinished"],
                "missing_from_source": missing_from_source,
            },
        }
        results.append(lang_result)

        if not json_output:
            status_emoji = (
                "✅"
                if completion >= 95
                else "🟡"
                if completion >= 80
                else "🟠"
                if completion >= 50
                else "🔴"
            )

            print(
                f"{language:<10} {completion:>6.1f}% {stats['translated']:>9}/{stats['total']:<4} {stats['unfinished']:>10} {missing_from_source:>10} {status_emoji:>8}"
            )

    if json_output:
        print(json.dumps({"type": "stats", "results": results}, indent=2))


def validate_translation(language: Optional[str] = None, dry_run: bool = False) -> None:
    """Validate and repair translation files for common issues.

    Checks for and automatically fixes:
    - Missing language attributes in XML
    - Empty translations
    - Placeholder mismatches between source and translation
    - Obsolete entries
    - XML structural issues

    Args:
        language: Language code to validate (e.g., 'zh_CN'). If None, validates
                 all languages except en_US
        dry_run: If True, previews changes without saving the file.

    Output:
        Prints validation results including issues found and fixes applied.
        Automatically saves corrected files without prompting.
    """
    locales_dir = Path("locales")

    languages = []
    if language:
        languages = [language]
    else:
        languages = [f.stem for f in locales_dir.glob("*.ts") if f.stem != "en_US"]

    for lang in languages:
        ts_file = locales_dir / f"{lang}.ts"
        if not ts_file.exists():
            print(f"❌ Translation file not found: {ts_file}")
            continue

        print(f"🔍 Validating translation for {lang}...")

        try:
            tree = ET.parse(ts_file)
            root = tree.getroot()

            issues = []
            made_changes = False

            # Check XML structure
            if root.tag != "TS":
                issues.append("❌ Root element should be 'TS'")

            if not root.get("language"):
                issues.append("❌ Missing language attribute")
                root.set("language", lang)
                made_changes = True
                print(f"🔧 Fixed missing language attribute for {lang}")

            # Check for common translation issues and fix placeholders and tags
            for context in root.findall("context"):
                for message in context.findall("message"):
                    source = message.find("source")
                    translation = message.find("translation")

                    if source is not None and translation is not None:
                        source_text = source.text or ""
                        trans_text = translation.text or ""

                        # Check for placeholder mismatches
                        source_placeholders = set(re.findall(r"\{[^}]+\}", source_text))
                        trans_placeholders = set(re.findall(r"\{[^}]+\}", trans_text))

                        if source_placeholders != trans_placeholders and trans_text:
                            issues.append(
                                f"⚠️  Placeholder mismatch: '{source_text[:30]}...' -> '{trans_text[:30]}...'"
                            )
                            made_changes = True
                            # Attempt to fix by aligning placeholders
                            # Remove placeholders not in source from translation
                            for ph in list(re.findall(r"\{[^}]+\}", trans_text)):
                                if ph not in source_placeholders:
                                    trans_text = trans_text.replace(ph, "")
                            # Add missing placeholders from source to translation if not present
                            for ph in source_placeholders:
                                if ph not in trans_text:
                                    trans_text += f" {ph}"
                            translation.text = trans_text.strip()
                            print(
                                f"🔧 Fixed placeholder mismatch in message: {source_text[:30]}..."
                            )

                        # Check for HTML tag mismatches
                        source_tags_list = re.findall(r"<[^>]+>", source_text)
                        trans_tags_list = re.findall(r"<[^>]+>", trans_text)
                        source_tags_counts = Counter(source_tags_list)
                        trans_tags_counts = Counter(trans_tags_list)

                        if source_tags_counts != trans_tags_counts and trans_text:
                            issues.append(
                                f"⚠️  HTML tag mismatch: '{source_text[:30]}...' -> '{trans_text[:30]}...'"
                            )
                            made_changes = True
                            # Attempt to fix by adding/removing tags. This is naive.

                            # Remove extra tags from translation
                            extra_tags = trans_tags_counts - source_tags_counts
                            for tag, count in extra_tags.items():
                                trans_text = trans_text.replace(tag, "", count)

                            # Add missing tags to translation
                            missing_tags = source_tags_counts - trans_tags_counts
                            for tag, count in missing_tags.items():
                                for _ in range(count):
                                    trans_text += f" {tag}"

                            translation.text = trans_text.strip()
                            print(
                                f"🔧 Fixed HTML tag mismatch in message: {source_text[:30]}..."
                            )

            if not issues:
                print("✅ Translation file is valid!")
            else:
                print(f"⚠️  Found {len(issues)} validation issues (some fixed):")
                for issue in issues[:10]:
                    print(f"   {issue}")
                if len(issues) > 10:
                    print(f"   ... and {len(issues) - 10} more issues")

            # Save fixed file if changes were made
            if made_changes:
                if dry_run:
                    print(f"📋 DRY-RUN: Would have saved fixes to {ts_file}")
                else:
                    tree.write(ts_file, encoding="utf-8", xml_declaration=True)
                    # Fix DOCTYPE
                    with open(ts_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    if "<!DOCTYPE TS>" not in content:
                        lines = content.split("\n")
                        lines.insert(1, "<!DOCTYPE TS>")
                        content = "\n".join(lines)

                    with open(ts_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"💾 Saved fixes to {ts_file}")

        except Exception as e:
            print(f"❌ Error validating file: {e}")


async def process_language(
    language: Optional[str],
    service: str,
    continue_on_failure: bool = True,
    dry_run: bool = False,
    **service_kwargs: Any,
) -> bool:
    """Run the full pipeline for a language or all languages if None.

    Args:
        language: Language code to process (None for all)
        service: Translation service to use
        continue_on_failure: Continue if some translations fail
        dry_run: Preview changes without modifying files
        **service_kwargs: Additional arguments for translation service

    Returns:
        True if the process was successful, False otherwise.
    """
    if language:
        print(f"🚀 Starting one-click process for {language} ...")
        if dry_run:
            print("📋 DRY-RUN MODE: Preview changes without saving")

        if not dry_run:
            if not run_lupdate(language):
                print("❌ Aborting: lupdate failed.")
                return False
            validate_translation(language, dry_run=dry_run)
        elif dry_run:
            print(f"📋 Would run: pyside6-lupdate for {language}")
            print(f"📋 Would run: validate for {language}")

        if not await auto_translate_file(
            language, service, continue_on_failure, dry_run=dry_run, **service_kwargs
        ):
            print("❌ Aborting: auto-translation failed.")
            return False

        if not dry_run and not run_lrelease(language):
            print("❌ Aborting: lrelease failed.")
            return False
        elif dry_run:
            print(f"📋 Would run: pyside6-lrelease for {language}")

        if dry_run:
            print(
                "✅ Dry-run preview complete. Use without --dry-run to apply changes."
            )
        else:
            print("✅ One-click process completed successfully!")
        return True
    else:
        print("🚀 Starting one-click process for all languages ...")
        if dry_run:
            print("📋 DRY-RUN MODE: Preview changes without saving")

        locales_dir = Path("locales")
        languages = [f.stem for f in locales_dir.glob("*.ts") if f.stem != "en_US"]
        all_successful = True

        for lang in languages:
            print(f"\n🚀 Processing {lang} ...")

            if not dry_run:
                if not run_lupdate(lang):
                    print(f"❌ Aborting {lang}: lupdate failed.")
                    if not continue_on_failure:
                        return False
                    all_successful = False
                    continue
                validate_translation(lang, dry_run=dry_run)
            elif dry_run:
                print(f"📋 Would run: pyside6-lupdate for {lang}")
                print(f"📋 Would run: validate for {lang}")

            if not await auto_translate_file(
                lang, service, continue_on_failure, dry_run=dry_run, **service_kwargs
            ):
                print(f"❌ Aborting {lang}: auto-translation failed.")
                if not continue_on_failure:
                    return False
                all_successful = False
                continue

            if not dry_run and not run_lrelease(lang):
                print(f"❌ Aborting {lang}: lrelease failed.")
                if not continue_on_failure:
                    return False
                all_successful = False
                continue
            elif dry_run:
                print(f"📋 Would run: pyside6-lrelease for {lang}")

            print(f"✅ {lang} process preview complete!")

        if dry_run:
            print(
                "\n✅ Dry-run preview complete for all languages. Use without --dry-run to apply changes."
            )
        else:
            print("\n✅ All languages processed!")
        return all_successful


def interactive_mode() -> None:
    """Interactive guided workflow for new users."""
    print("\n" + "=" * 60)
    print("🌍 RimSort Translation Helper - Interactive Mode")
    print("=" * 60)
    print("\nWelcome! This guided mode will help you manage translations.\n")

    while True:
        print("\n📋 Main Menu:")
        print("1. Check translation completeness")
        print("2. View translation statistics")
        print("3. Validate and fix translation files")
        print("4. Auto-translate missing strings")
        print("5. Run full process (update → translate → compile)")
        print("6. Exit")

        choice = input("\nSelect an option (1-6): ").strip()

        if choice == "1":
            _interactive_check()
        elif choice == "2":
            _interactive_stats()
        elif choice == "3":
            _interactive_validate()
        elif choice == "4":
            _interactive_auto_translate()
        elif choice == "5":
            _interactive_process()
        elif choice == "6":
            print("\n✨ Thank you for using RimSort Translation Helper!")
            break
        else:
            print("❌ Invalid option. Please try again.")


def _interactive_check() -> None:
    """Interactive check translation workflow."""
    print("\n" + "-" * 60)
    print("📋 Check Translation Completeness")
    print("-" * 60)

    locales_dir = Path("locales")
    if not locales_dir.exists():
        print("❌ Locales directory not found")
        return

    available_langs = sorted(
        [f.stem for f in locales_dir.glob("*.ts") if f.stem != "en_US"]
    )

    print(f"\nAvailable languages: {', '.join(available_langs)}")
    print("(Press Enter to check all languages)")

    lang_input = input("\nEnter language code or leave blank for all: ").strip()
    language = lang_input if lang_input else None

    json_output = input("Output as JSON? (y/n): ").strip().lower() == "y"

    print("\n🔄 Checking translation completeness...")
    check_translation(language, json_output=json_output)


def _interactive_stats() -> None:
    """Interactive view statistics workflow."""
    print("\n" + "-" * 60)
    print("📊 Translation Statistics")
    print("-" * 60)

    json_output = input("Output as JSON? (y/n): ").strip().lower() == "y"

    print("\n🔄 Gathering statistics...")
    show_all_stats(json_output=json_output)


def _interactive_validate() -> None:
    """Interactive validate and fix workflow."""
    print("\n" + "-" * 60)
    print("✅ Validate and Fix Translation Files")
    print("-" * 60)

    locales_dir = Path("locales")
    if not locales_dir.exists():
        print("❌ Locales directory not found")
        return

    available_langs = sorted(
        [f.stem for f in locales_dir.glob("*.ts") if f.stem != "en_US"]
    )

    print(f"\nAvailable languages: {', '.join(available_langs)}")
    print("(Press Enter to validate all languages)")

    lang_input = input("\nEnter language code or leave blank for all: ").strip()
    language = lang_input if lang_input else None

    print("\n🔄 Validating translation files...")
    validate_translation(language)
    print("✅ Validation complete!")


def _get_interactive_translation_config() -> (
    tuple[
        Optional[str],
        str,
        dict[str, Any],
        bool,
    ]
    | tuple[None, None, None, None]
):
    """Get translation configuration interactively from the user."""
    locales_dir = Path("locales")
    if not locales_dir.exists():
        print("❌ Locales directory not found")
        return None, None, None, None

    available_langs = sorted(
        [f.stem for f in locales_dir.glob("*.ts") if f.stem != "en_US"]
    )

    print(f"\nAvailable languages: {', '.join(available_langs)}")
    print("(Press Enter to process all languages)")

    lang_input = input("\nEnter language code or leave blank for all: ").strip()
    language = lang_input if lang_input else None

    # Service selection
    print("\n📡 Available translation services:")
    print("1. Google Translate (free, no API key needed)")
    print("2. DeepL (requires API key)")
    print("3. OpenAI GPT (requires API key)")

    service_choice = input("\nSelect service (1-3): ").strip()
    service_map = {"1": "google", "2": "deepl", "3": "openai"}
    service = service_map.get(service_choice, "google")

    service_kwargs: dict[str, Any] = {}

    if service == "deepl":
        api_key = input("Enter your DeepL API key: ").strip()
        if not api_key:
            print("❌ API key is required for DeepL")
            return None, None, None, None
        service_kwargs["api_key"] = api_key
    elif service == "openai":
        api_key = input("Enter your OpenAI API key: ").strip()
        if not api_key:
            print("❌ API key is required for OpenAI")
            return None, None, None, None
        service_kwargs["api_key"] = api_key

        model = input("Enter model (default: gpt-3.5-turbo): ").strip()
        if model:
            service_kwargs["model"] = model

    # Configuration options
    print("\n⚙️  Configuration Options:")
    timeout_input = input("Request timeout in seconds (default: 10.0): ").strip()
    timeout = float(timeout_input) if timeout_input else 10.0

    retries_input = input("Max retry attempts (default: 3): ").strip()
    max_retries = int(retries_input) if retries_input else 3

    concurrent_input = input("Max concurrent requests (default: 5): ").strip()
    max_concurrent = int(concurrent_input) if concurrent_input else 5

    # Dry-run option
    dry_run_input = (
        input(
            "\nPreview mode (dry-run)? This shows what would change without saving (y/n): "
        )
        .strip()
        .lower()
    )
    dry_run = dry_run_input == "y"

    # Confirm before starting
    print("\n📝 Configuration:")
    print(f"  Language: {language or 'All'}")
    print(f"  Service: {service}")
    print(f"  Timeout: {timeout}s")
    print(f"  Max retries: {max_retries}")
    print(f"  Concurrent requests: {max_concurrent}")
    if dry_run:
        print("  Mode: 📋 DRY-RUN (preview only)")

    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled")
        return None, None, None, None

    config = TranslationConfig(
        retry_config=RetryConfig(max_retries=max_retries),
        timeout_config=TimeoutConfig(
            default_timeout=timeout,
            deepl_timeout=timeout,
            openai_timeout=timeout,
            google_timeout=timeout,
        ),
        max_concurrent_requests=max_concurrent,
    )
    set_translation_config(config)

    return language, service, service_kwargs, dry_run


def _interactive_auto_translate() -> None:
    """Interactive auto-translate workflow."""
    print("\n" + "-" * 60)
    print("🤖 Auto-Translate Missing Strings")
    print("-" * 60)

    config_result = _get_interactive_translation_config()
    if config_result[1] is None:
        return

    language, service, service_kwargs, dry_run = config_result

    if dry_run:
        print("\n🔄 Starting dry-run preview...")
    else:
        print("\n🔄 Starting auto-translation...")
    asyncio.run(
        auto_translate_file(language, service, True, dry_run=dry_run, **service_kwargs)
    )
    if not dry_run:
        print("✅ Auto-translation complete!")


def _interactive_process() -> None:
    """Interactive full process workflow."""
    print("\n" + "-" * 60)
    print("🚀 Full Translation Process")
    print("-" * 60)
    print("\nThis will run the complete pipeline:")
    print("  1. Update .ts files with new strings (lupdate)")
    print("  2. Auto-translate missing strings")
    print("  3. Compile .ts files to .qm format (lrelease)")

    config_result = _get_interactive_translation_config()
    if config_result[1] is None:
        return

    language, service, service_kwargs, dry_run = config_result

    if dry_run:
        print("\n🔄 Starting dry-run preview...")
    else:
        print("\n🔄 Starting full translation process...")
    asyncio.run(
        process_language(language, service, True, dry_run=dry_run, **service_kwargs)
    )
    if not dry_run:
        print("✅ Full process complete!")


def add_translation_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments for translation to an argparse parser."""
    service_choices = ["google", "deepl", "openai"]
    parser.add_argument(
        "--service",
        choices=service_choices,
        default="google",
        help="Translation service",
    )
    parser.add_argument("--api-key", help="API key for DeepL/OpenAI")
    parser.add_argument("--model", default="gpt-3.5-turbo", help="OpenAI model to use")
    parser.add_argument(
        "--continue-on-failure",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Continue translating even if some fail (disable with --no-continue-on-failure)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Request timeout in seconds (default: 10.0)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retry attempts (default: 3)",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent requests (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip using the translation cache for the current run.",
    )


def get_translation_config_from_args(
    args: argparse.Namespace,
) -> tuple[TranslationConfig, dict[str, Any]]:
    """Get translation config and service kwargs from parsed arguments."""
    try:
        validated_timeout = validate_timeout(args.timeout)
        validated_retries = validate_retry_count(args.max_retries)
        validated_concurrent = validate_concurrent_requests(args.max_concurrent)

        # Validate API key if service requires it
        if args.service in ["deepl", "openai"] and args.api_key:
            validate_api_key(args.api_key, args.service.upper())

        # Validate model name if provided
        if args.model:
            validate_model_name(args.model)
    except (ValueError, TypeError) as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)

    config = TranslationConfig(
        retry_config=RetryConfig(max_retries=validated_retries),
        timeout_config=TimeoutConfig(
            default_timeout=validated_timeout,
            deepl_timeout=validated_timeout,
            openai_timeout=validated_timeout,
            google_timeout=validated_timeout,
        ),
        max_concurrent_requests=validated_concurrent,
        use_cache=not args.no_cache,
    )

    service_kwargs = {}
    if args.api_key:
        service_kwargs["api_key"] = args.api_key
    if args.model:
        service_kwargs["model"] = args.model

    return config, service_kwargs


def main() -> None:
    """Main entry point for the translation helper CLI.

    Provides an interactive and command-line interface for managing translations.
    Supports both interactive mode (--interactive) and command-based workflows
    (check, stats, validate, update-ts, compile, auto-translate, process).
    """
    parser = argparse.ArgumentParser(
        description="Enhanced RimSort Translation Helper",
        epilog="Use 'python translation_helper.py --interactive' for guided workflow",
    )

    # Add interactive flag
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Launch interactive guided mode for new users",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check translation completeness")
    check_parser.add_argument(
        "language", nargs="?", help="Language code (e.g., zh_CN), optional"
    )
    check_parser.add_argument(
        "--json", action="store_true", help="Output results as structured JSON"
    )

    # Stats command
    stats_parser = subparsers.add_parser(
        "stats", help="Show statistics for all translations"
    )
    stats_parser.add_argument(
        "--json", action="store_true", help="Output results as structured JSON"
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate translation file"
    )
    validate_parser.add_argument(
        "language", nargs="?", help="Language code (e.g., zh_CN), optional"
    )
    validate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files",
    )

    # Update command
    update_parser = subparsers.add_parser(
        "update-ts", help="Update translation files using lupdate"
    )
    update_parser.add_argument(
        "language",
        nargs="?",
        help="Language code (optional, updates all if not specified)",
    )

    # Compile command
    compile_parser = subparsers.add_parser(
        "compile", help="Compile translation file using lrelease"
    )
    compile_parser.add_argument(
        "language", nargs="?", help="Language code (e.g., zh_CN), optional"
    )

    # Auto-translate command
    auto_parser = subparsers.add_parser(
        "auto-translate", help="Auto-translate unfinished strings"
    )
    auto_parser.add_argument(
        "language", nargs="?", help="Language code (e.g., zh_CN), optional"
    )
    add_translation_args(auto_parser)

    process_parser = subparsers.add_parser(
        "process",
        help="One-click workflow: update .ts → validate → auto-translate → compile .qm",
    )
    process_parser.add_argument(
        "language", nargs="?", help="Language code, e.g. zh_CN, optional"
    )
    add_translation_args(process_parser)

    args = parser.parse_args()

    # Handle interactive mode
    if args.interactive:
        interactive_mode()
        return

    if args.command == "check":
        check_translation(args.language, json_output=getattr(args, "json", False))
    elif args.command == "stats":
        show_all_stats(json_output=getattr(args, "json", False))
    elif args.command == "validate":
        validate_translation(args.language, dry_run=getattr(args, "dry_run", False))
    elif args.command == "update-ts":
        run_lupdate(args.language)
    elif args.command == "compile":
        run_lrelease(args.language)
    elif args.command in ["auto-translate", "process"]:
        config, service_kwargs = get_translation_config_from_args(args)
        set_translation_config(config)

        if args.command == "auto-translate":
            success = asyncio.run(
                auto_translate_file(
                    args.language,
                    args.service,
                    args.continue_on_failure,
                    dry_run=getattr(args, "dry_run", False),
                    **service_kwargs,
                )
            )
            if not success:
                sys.exit(1)
        elif args.command == "process":
            success = asyncio.run(
                process_language(
                    args.language,
                    args.service,
                    args.continue_on_failure,
                    dry_run=getattr(args, "dry_run", False),
                    **service_kwargs,
                )
            )
            if not success:
                sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
