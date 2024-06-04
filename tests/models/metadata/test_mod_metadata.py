import pytest

import app.models.metadata.mod_metadata as mod_metadata


def test_case_insensitive() -> None:
    pid = mod_metadata.CaseInsensitiveStr("TestPackage")
    assert pid == "testpackage"


@pytest.mark.parametrize(
    "input1, input2",
    [
        ("TestPackage", "testpackage"),
        ("testpackage", "TestPackage"),
        ("測試包", "測試包"),
        ("TEST.測試包", "test.測試包"),
        ("testpackage", "testpackage"),
    ],
)
def test_case_insensitive_equality(input1: str, input2: str) -> None:
    pid1 = mod_metadata.CaseInsensitiveStr(input1)
    pid2 = mod_metadata.CaseInsensitiveStr(input2)
    assert pid1 == pid2


@pytest.mark.parametrize(
    "pid, string",
    [
        ("TestPackage", "testpackage"),
        ("TESTPACKAGE", "testpackage"),
        ("測試包", "測試包"),
        ("TEST.測試包", "test.測試包"),
    ],
)
def test_case_insensitive_str(pid: str, string: str) -> None:
    package_id = mod_metadata.CaseInsensitiveStr(pid)
    assert str(package_id) == string
    assert package_id == string.lower()


def test_case_insensitive_set_contains() -> None:
    package_id_set = mod_metadata.CaseInsensitiveSet(["TestPackage", "AnotherPackage"])
    assert "TestPackage" in package_id_set
    assert "AnotherPackage" in package_id_set
    assert "NonExistingPackage" not in package_id_set


def test_case_insensitive_set_add() -> None:
    package_id_set = mod_metadata.CaseInsensitiveSet()
    package_id_set.add("TestPackage")
    assert "TestPackage" in package_id_set
    assert "testpackage" in package_id_set


def test_case_insensitive_set_discard() -> None:
    package_id_set = mod_metadata.CaseInsensitiveSet(["TestPackage"])
    package_id_set.discard("TestPackage")
    assert "TestPackage" not in package_id_set

    package_id_set = mod_metadata.CaseInsensitiveSet(["TestPackage"])
    package_id_set.discard("testpackage")
    assert "TestPackage" not in package_id_set


def test_case_insensitive_set_len() -> None:
    package_id_set = mod_metadata.CaseInsensitiveSet(["TestPackage", "AnotherPackage"])
    assert len(package_id_set) == 2

    package_id_set = mod_metadata.CaseInsensitiveSet(["TestPackage", "testpackage"])
    assert len(package_id_set) == 1


def test_case_insensitive_set_iter() -> None:
    package_id_set = mod_metadata.CaseInsensitiveSet(["TestPackage", "AnotherPackage"])
    assert set(package_id_set) == {"testpackage", "anotherpackage"}


def test_case_insensitive_set_and() -> None:
    package_id_set1 = mod_metadata.CaseInsensitiveSet(["TestPackage", "AnotherPackage"])
    package_id_set2 = mod_metadata.CaseInsensitiveSet(
        ["anotherpackage", "AdditionalPackage"]
    )
    intersection = package_id_set1 & package_id_set2
    assert set(intersection) == {"anotherpackage"}


def test_case_insensitive_set_parametrize() -> None:
    package_id_set = mod_metadata.CaseInsensitiveSet(["TestPackage", "AnotherPackage"])
    assert package_id_set == mod_metadata.CaseInsensitiveSet(
        ["testpackage", "anotherpackage"]
    )
