from typing import Any

from app.utils.dict_utils import recursively_update_dict


def test_basic_merge() -> None:
    a = {"x": 1}
    b = {"y": 2}
    recursively_update_dict(a, b)
    assert a == {"x": 1, "y": 2}


def test_nested_merge() -> None:
    a = {"a": {"b": 1, "c": 2}}
    b = {"a": {"c": 3, "d": 4}}
    recursively_update_dict(a, b)
    assert a == {"a": {"b": 1, "c": 3, "d": 4}}


def test_prune_empty_dicts() -> None:
    a = {"a": {"b": 1}, "empty": {}}
    b = {"a": {"b": 2}}
    recursively_update_dict(a, b)
    assert "empty" not in a


def test_prune_exception_preserves_empty() -> None:
    a: dict[str, Any] = {"keep": {}, "drop": {}}
    b: dict[str, Any] = {}
    recursively_update_dict(a, b, prune_exceptions=["keep"])
    assert "keep" in a
    assert "drop" not in a


def test_recurse_exception_overwrites() -> None:
    a = {"x": {"nested": 1}}
    b = {"x": {"replaced": 2}}
    recursively_update_dict(a, b, recurse_exceptions=["x"])
    assert a["x"] == {"replaced": 2}


def test_recurse_exception_preserves_when_absent_from_new() -> None:
    a = {"x": {"old": 1}, "y": 2}
    b: dict[str, Any] = {"y": 3}
    recursively_update_dict(a, b, recurse_exceptions=["x"])
    assert a["x"] == {"old": 1}
    assert a["y"] == 3


def test_purge_keys() -> None:
    a = {"keep": 1, "remove": 2}
    b: dict[str, Any] = {}
    recursively_update_dict(a, b, purge_keys=["remove"])
    assert "remove" not in a
    assert a["keep"] == 1
