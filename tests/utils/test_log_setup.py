from app.utils.log_setup import _anonymize_path, _obfuscate_message


def test_anonymize_path_windows() -> None:
    assert (
        _anonymize_path(r"C:\Users\john\Documents\file.txt")
        == r"C:\Users\...\Documents\file.txt"
    )
    assert (
        _anonymize_path(r"D:\Users\abc\Documents\file.txt")
        == r"D:\Users\...\Documents\file.txt"
    )


def test_anonymize_path_linux() -> None:
    assert (
        _anonymize_path("/home/john/Documents/file.txt")
        == "/home/.../Documents/file.txt"
    )
    assert (
        _anonymize_path("/home/abc/Documents/file.txt")
        == "/home/.../Documents/file.txt"
    )


def test_anonymize_path_macos() -> None:
    assert (
        _anonymize_path("/Users/john/Documents/file.txt")
        == "/Users/.../Documents/file.txt"
    )
    assert (
        _anonymize_path("/Users/abc/Documents/file.txt")
        == "/Users/.../Documents/file.txt"
    )


def test_anonymize_path_windows_in_message() -> None:
    assert (
        _anonymize_path(r"Error at: C:\Users\john\file.txt")
        == r"Error at: C:\Users\...\file.txt"
    )


def test_anonymize_path_linux_in_message() -> None:
    assert (
        _anonymize_path("Error at: /home/john/file.txt")
        == "Error at: /home/.../file.txt"
    )


def test_anonymize_path_macos_in_message() -> None:
    assert (
        _anonymize_path("Error at: /Users/john/file.txt")
        == "Error at: /Users/.../file.txt"
    )


def test_anonymize_path_no_path() -> None:
    assert _anonymize_path("no path here") == "no path here"


def test_obfuscate_message_delegates_to_anonymize_path() -> None:
    assert _obfuscate_message("/home/john/file.txt") == "/home/.../file.txt"


def test_obfuscate_message_skip_anonymize() -> None:
    assert (
        _obfuscate_message("/home/john/file.txt", anonymize_path=False)
        == "/home/john/file.txt"
    )
