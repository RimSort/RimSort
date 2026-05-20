from app.utils.obfuscate_message import (
    _anonymize_path,
    _redact_secrets,
    obfuscate_message,
)


def test__anonymize_path_windows_path_only() -> None:
    message = r"C:\Users\user\Documents\file.txt"
    expected = r"C:\Users\...\Documents\file.txt"
    assert _anonymize_path(message) == expected

    message = r"C:\Users\abc\Documents\file.txt"
    assert _anonymize_path(message) == expected

    message = r"D:\Users\user\Documents\file.txt"
    expected = r"D:\Users\...\Documents\file.txt"
    assert _anonymize_path(message) == expected

    message = r"D:\Users\abc\Documents\file.txt"
    assert _anonymize_path(message) == expected


def test__anonymize_path_linux_path_only() -> None:
    message = "/home/user/Documents/file.txt"
    expected = "/home/.../Documents/file.txt"
    assert _anonymize_path(message) == expected

    message = "/home/abc/Documents/file.txt"
    assert _anonymize_path(message) == expected


def test__anonymize_path_windows_mixed_message() -> None:
    message = "C:\\Users\\user\\Documents\\file.txt: error"
    expected = "C:\\Users\\...\\Documents\\file.txt: error"
    assert _anonymize_path(message) == expected

    message = "Error!!! at: C:\\Users\\user\\Documents\\file.txt"
    expected = "Error!!! at: C:\\Users\\...\\Documents\\file.txt"
    assert _anonymize_path(message) == expected


def test__anonymize_path_linux_mixed_message() -> None:
    message = "/home/user/Documents/file.txt: error"
    expected = "/home/.../Documents/file.txt: error"
    assert _anonymize_path(message) == expected

    message = "Error!!! at: /home/user/Documents/file.txt"
    expected = "Error!!! at: /home/.../Documents/file.txt"
    assert _anonymize_path(message) == expected


def test__anonymize_path_macos_path_only() -> None:
    message = "/Users/user/Documents/file.txt"
    expected = "/Users/.../Documents/file.txt"
    assert _anonymize_path(message) == expected

    message = "/Users/abc/Documents/file.txt"
    assert _anonymize_path(message) == expected


def test__anonymize_path_macos_mixed_message() -> None:
    message = "/Users/user/Documents/file.txt: error"
    expected = "/Users/.../Documents/file.txt: error"
    assert _anonymize_path(message) == expected

    message = "Error!!! at: /Users/user/Documents/file.txt"
    expected = "Error!!! at: /Users/.../Documents/file.txt"
    assert _anonymize_path(message) == expected


class TestRedactSecrets:
    """Test API key and token redaction."""

    def test_redact_query_param_key(self) -> None:
        msg = "https://api.steam.com/ISteam?key=ABC123DEF456&format=json"
        result = _redact_secrets(msg)
        assert "ABC123DEF456" not in result
        assert "?key=[REDACTED]" in result
        assert "&format=json" in result

    def test_redact_ampersand_key(self) -> None:
        msg = "https://api.steam.com/ISteam?format=json&key=SECRET123"
        result = _redact_secrets(msg)
        assert "SECRET123" not in result
        assert "&key=[REDACTED]" in result

    def test_no_key_unchanged(self) -> None:
        msg = "Normal error message without any keys"
        assert _redact_secrets(msg) == msg

    def test_multiple_keys_redacted(self) -> None:
        msg = "url1?key=AAA and url2&key=BBB"
        result = _redact_secrets(msg)
        assert "AAA" not in result
        assert "BBB" not in result

    def test_obfuscate_message_includes_redaction(self) -> None:
        msg = "Error at /home/user/app: ?key=SECRET"
        result = obfuscate_message(msg)
        assert "SECRET" not in result
        assert "user" not in result
        assert "?key=[REDACTED]" in result

    def test_preserves_delimiter(self) -> None:
        msg = "?key=SECRET"
        result = _redact_secrets(msg)
        assert result == "?key=[REDACTED]"

        msg2 = "&key=SECRET"
        result2 = _redact_secrets(msg2)
        assert result2 == "&key=[REDACTED]"

    def test_non_url_key_not_redacted(self) -> None:
        """Strings like 'encryption key=AES256' should NOT be redacted."""
        msg = "encryption key=AES256"
        result = _redact_secrets(msg)
        assert result == msg
