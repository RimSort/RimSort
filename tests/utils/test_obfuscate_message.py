from app.utils.obfuscate_message import _anonymize_path


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
