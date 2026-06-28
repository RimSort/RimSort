"""Centralized, SSL-safe import of pygit2.

pygit2 initializes libgit2's TLS certificate locations at import time using
``ssl.get_default_verify_paths()``. Inside bundled builds (e.g. the AppImage),
the embedded OpenSSL reports certificate paths that do not exist on the host
system, so importing pygit2 raises::

    _pygit2.GitError: OpenSSL error: failed to load certificates

When that happens we fall back to the certificate bundle shipped by ``certifi``
and retry the import.

Every module that needs pygit2 (or its submodules) must import it from here
rather than importing ``pygit2`` directly, so that this fallback runs before
pygit2's first import no matter which module triggers it. See
https://github.com/RimSort/RimSort/issues/2234.
"""

import os

from loguru import logger

try:
    import pygit2
    from pygit2.enums import CheckoutStrategy, ResetMode, SortMode
    from pygit2.repository import Repository
except Exception:
    import certifi

    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ["SSL_CERT_DIR"] = os.path.dirname(certifi.where())
    logger.warning("Set SSL certificates using certifi for pygit2 import")

    try:
        import pygit2
        from pygit2.enums import CheckoutStrategy, ResetMode, SortMode
        from pygit2.repository import Repository
    except Exception as e:
        logger.error("Failed to import pygit2 after setting SSL certificates.")
        raise ImportError("Failed to import pygit2.") from e

__all__ = [
    "CheckoutStrategy",
    "Repository",
    "ResetMode",
    "SortMode",
    "pygit2",
]
