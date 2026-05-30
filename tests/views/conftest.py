"""Conftest for views tests — mock compiled C extensions that may not be available."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

# The steamworks module is a compiled C extension from the SteamworksPy submodule.
# It is not available in dev/CI environments without running distribute.py first.
# Mock it so that imports through the chain (main_content_panel -> metadata ->
# steamcmd/wrapper -> runner_panel -> steamworks/wrapper -> steamworks) succeed.
if "steamworks" not in sys.modules:
    _mock_steamworks = ModuleType("steamworks")
    _mock_steamworks.STEAMWORKS = MagicMock()  # type: ignore[attr-defined]
    sys.modules["steamworks"] = _mock_steamworks
