"""
This module is to be used with loguru to remove potentially sensitive information such as the user's name.
"""

import re


def obfuscate_message(message: str, anonymize_path: bool = True) -> str:
    """
    Obfuscate the message such that it does not reveal user information.

    The message may contain a path, in which case the path will be anonymized.

    Args:
        message: The message to obfuscate.
        anonymize_path: Whether to anonymize the path in the message.

    Returns:
        The obfuscated message.
    """
    if anonymize_path:
        message = _anonymize_path(message)

    return message


def _anonymize_path(message: str) -> str:
    """
    Anonymize the path in the message such that
    it does not reveal user information such as usernames.

    The input message may or may not contain a path at all.

    OS agnostic.
    """
    # Windows - Only remove the username, keep the drive letter
    message = message = re.sub(r"([A-Z]:\\Users\\)[^\\]+\\", r"\1...\\", message)
    # Linux - Only remove the username
    message = re.sub(r"/home/[^/]+/", r"/home/../", message)
    
    return message
