"""Conftest for utils tests - handles missing submodule dependencies in worktrees."""

import importlib.util
import sys
from unittest.mock import MagicMock

# Pre-populate steamworks in sys.modules if the submodule isn't available,
# allowing test collection to succeed in worktrees where submodules
# haven't been initialized.
if "steamworks" not in sys.modules:
    _spec = importlib.util.find_spec("steamworks")
    if _spec is None:
        sys.modules["steamworks"] = MagicMock()
