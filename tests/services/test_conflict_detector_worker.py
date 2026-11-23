import copy
import ctypes
import gc
import io
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.conflict_detector_fixtures import make_report


@pytest.mark.parametrize(
    ("extra", "valid"),
    [
        ({}, True),
        ({"code": None, "params": {}}, True),
        (
            {"code": "about_parse_failure", "params": {"path": "/a", "detail": "x"}},
            True,
        ),
        ({"code": 7}, False),
        ({"params": None}, False),
        ({"params": {"path": 7}}, False),
        ({"params": {3: "x"}}, False),
        ({"params": []}, False),
    ],
)
def test_diagnostic_structured_fields_validation(
    extra: dict[object, object], valid: bool
) -> None:
    from app.services.conflict_detector_worker import _diagnostic_valid

    diagnostic: dict[Any, Any] = {
        "affected_mod": None,
        "severity": "warning",
        "message": "raw",
        "source": "xml_parsing",
        "analysis_incomplete": True,
    }
    diagnostic.update(extra)
    assert _diagnostic_valid(diagnostic) is valid


@pytest.mark.parametrize("severity", ["error", "warning", "info"])
def test_shared_report_counts_match_severity(severity: str) -> None:
    report = make_report(severity, False)
    finding = report["conflicts"][0]
    mechanism = finding["mechanism"]
    if severity == "error":
        assert "direct_replacement" in mechanism
    else:
        assert mechanism == {
            "x_path_overlap": {
                "xpath_a": "a",
                "xpath_b": "b",
                "wildcard": severity == "info",
            }
        }
    summary = report["summary"]
    assert isinstance(summary, dict)
    assert summary["conflicts_by_severity"] == {
        name: int(name == severity) for name in ("error", "warning", "info")
    }


def test_missing_native_library_is_a_terminal_error(tmp_path: Path) -> None:
    env = os.environ | {
        "RIMSORT_DEV": "1",
        "RIMSORT_RCD_LIBRARY": str(tmp_path / "missing.so"),
    }
    request = {
        "protocol": 1,
        "id": "missing",
        "config": {"mod_paths": [], "ordered": True},
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.services.conflict_detector_worker"],
        input=json.dumps(request).encode(),
        capture_output=True,
        env=env,
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        timeout=10,
    )
    message = json.loads(result.stdout)
    assert message["id"] == "missing"
    assert message["kind"] == "error"
    assert result.returncode != 0


def run_guarded_entrypoint(
    tmp_path: Path, library: str, request: dict[str, object]
) -> subprocess.CompletedProcess[bytes]:
    (tmp_path / "sitecustomize.py").write_text(
        """import builtins, socket\noriginal = builtins.__import__\ndef guarded(name, *args, **kwargs):\n    if name.startswith(("app.controllers.app_controller", "app.views.dialogue", "PySide6")):\n        raise RuntimeError("GUI forbidden; GUI import forbidden")\n    return original(name, *args, **kwargs)\nbuiltins.__import__ = guarded\ndef forbidden(*args, **kwargs):\n    raise RuntimeError("network forbidden")\nsocket.socket.connect = forbidden\n"""
    )
    root = Path(__file__).resolve().parents[2]
    env = os.environ | {
        "PYTHONPATH": os.pathsep.join([str(tmp_path), str(root)]),
        "RIMSORT_DEV": "1",
        "RIMSORT_RCD_LIBRARY": library,
    }
    return subprocess.run(
        [sys.executable, "-m", "app", "--rcd-worker"],
        input=json.dumps(request).encode(),
        capture_output=True,
        env=env,
        cwd=root,
        timeout=10,
        check=False,
    )


def test_entrypoint_dispatches_before_gui_and_network(tmp_path: Path) -> None:
    request = {
        "protocol": 1,
        "id": "entry",
        "config": {"mod_paths": [], "ordered": True},
    }
    result = run_guarded_entrypoint(tmp_path, str(tmp_path / "missing.so"), request)
    assert json.loads(result.stdout)["id"] == "entry"
    assert json.loads(result.stdout)["kind"] == "error"
    assert b"GUI import forbidden" not in result.stderr
    assert b"network forbidden" not in result.stderr


def test_real_entrypoint_with_local_ffi(tmp_path: Path) -> None:
    lib = os.environ.get("RIMSORT_RCD_LIBRARY")
    if not lib or not Path(lib).is_file():
        pytest.skip("set RIMSORT_RCD_LIBRARY to an authorized local debug library")
    mod = tmp_path / "mod"
    (mod / "About").mkdir(parents=True)
    (mod / "About" / "About.xml").write_text(
        "<ModMetaData><name>Example</name><packageId>test.example</packageId></ModMetaData>"
    )
    request = {
        "protocol": 1,
        "id": "real",
        "config": {"mod_paths": [str(mod)], "ordered": True},
    }
    result = run_guarded_entrypoint(tmp_path, lib, request)
    frames = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode == 0, result.stderr
    assert all(frame["id"] == "real" for frame in frames)
    assert frames[-1]["kind"] == "report"
    assert (
        frames[-1]["report"]["metadata"]["mods_scanned"][0]["package_id"]
        == "test.example"
    )
    assert (
        b"GUI forbidden" not in result.stderr
        and b"network forbidden" not in result.stderr
    )


def test_concurrent_progress_preserves_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import conflict_detector_worker as worker

    def fake_analyze(config: dict[str, object], callback: Any) -> dict[str, object]:
        threads = [
            threading.Thread(target=callback, args=(index, 20, "x" * 1000))
            for index in range(20)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return make_report("error", False)

    monkeypatch.setattr(worker, "analyze", fake_analyze)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.TextIOWrapper(
            io.BytesIO(
                json.dumps({"protocol": 1, "id": "threaded", "config": {}}).encode()
            )
        ),
    )
    output = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(output, write_through=True))
    assert worker.main() == 0
    frames = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(frames) == 21
    assert {frame["current"] for frame in frames[:-1]} == set(range(20))
    assert frames[-1]["kind"] == "report"


def test_worker_protocol_is_utf8_independent_of_stdio_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import conflict_detector_worker as worker

    seen: list[object] = []

    def fake_analyze(config: dict[str, object], callback: Any) -> dict[str, object]:
        seen.append(config["mod_paths"])
        return make_report("error", False)

    monkeypatch.setattr(worker, "analyze", fake_analyze)
    request = json.dumps(
        {"protocol": 1, "id": "é", "config": {"mod_paths": ["/é"]}}, ensure_ascii=False
    ).encode("utf-8")
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(request), encoding="ascii")
    )
    output = io.BytesIO()
    monkeypatch.setattr(
        sys, "stdout", io.TextIOWrapper(output, encoding="ascii", write_through=True)
    )
    assert worker.main() == 0
    assert seen == [["/é"]]
    assert json.loads(output.getvalue())["id"] == "é"


class Function:
    def __init__(self, fn: Any) -> None:
        self.fn = fn
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args: Any) -> Any:
        return self.fn(*args)


class FakeLibrary:
    def __init__(self, payload: bytes) -> None:
        self.buffer = ctypes.create_string_buffer(payload)
        self.freed: list[int] = []
        self.config: dict[str, object] = {}
        self.rcd_analyze = Function(self._analyze)
        self.rcd_free = Function(self.freed.append)

    def _analyze(self, config: bytes, callback: Any) -> int:
        self.config = json.loads(config)
        gc.collect()
        callback(1, 2, b"xml")
        return ctypes.addressof(self.buffer)


@pytest.fixture
def valid_native_library(monkeypatch: pytest.MonkeyPatch) -> FakeLibrary:
    from app.services import conflict_detector_worker as worker

    lib = FakeLibrary(json.dumps(make_report("error", False)).encode())
    monkeypatch.setattr(worker, "load_library", lambda: lib)
    return lib


def test_owned_result_and_progress(valid_native_library: FakeLibrary) -> None:
    from app.services import conflict_detector_worker as worker

    lib = valid_native_library
    progress: list[tuple[int, int, str]] = []
    report = worker.analyze(
        {"mod_paths": [], "ordered": True, "game_version": "Unknown"},
        lambda *args: progress.append(args),
    )
    assert report["schema_version"] == 3
    assert progress == [(1, 2, "xml")]
    assert "game_version" not in lib.config
    assert lib.freed == [ctypes.addressof(lib.buffer)]
    assert lib.rcd_analyze.restype is ctypes.c_void_p


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b'{"error":"bad","diagnostics":[{"message":"details"}]}',
        b'{"schema_version":2}',
    ],
)
def test_bad_result_freed(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    from app.services import conflict_detector_worker as worker

    lib = FakeLibrary(payload)
    monkeypatch.setattr(worker, "load_library", lambda: lib)
    with pytest.raises((ValueError, RuntimeError)):
        worker.analyze({"mod_paths": [], "ordered": True}, lambda *_: None)
    assert lib.freed == [ctypes.addressof(lib.buffer)]


def test_resolver_ignores_untrusted_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import conflict_detector_worker as worker

    monkeypatch.setenv("RIMSORT_RCD_LIBRARY", str(tmp_path / "hostile.so"))
    monkeypatch.setenv("RIMSORT_DEV", "1")
    monkeypatch.setenv("RIMSORT_RCD_PACKAGED", "1")
    assert worker.library_path() != tmp_path / "hostile.so"
    monkeypatch.delenv("RIMSORT_RCD_PACKAGED")
    monkeypatch.setattr(worker, "_compiled", lambda: True)
    assert worker.library_path() != tmp_path / "hostile.so"
    monkeypatch.setattr(worker, "_compiled", lambda: False)
    monkeypatch.setenv("RIMSORT_RCD_LIBRARY", "relative.so")
    with pytest.raises(ValueError):
        worker.library_path()
    monkeypatch.setenv("RIMSORT_DEV", "0")
    assert worker.library_path().is_absolute()


def test_large_config_reaches_ffi(valid_native_library: FakeLibrary) -> None:
    from app.services import conflict_detector_worker as worker

    lib = valid_native_library
    big = "/" + "x" * (9 * 1024 * 1024)
    worker.analyze({"mod_paths": [big], "ordered": True}, lambda *_: None)
    assert lib.config["mod_paths"] == [big]


def test_null_and_copy_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import conflict_detector_worker as worker

    lib = FakeLibrary(b"{}")
    monkeypatch.setattr(worker, "load_library", lambda: lib)
    lib.rcd_analyze.fn = lambda *_: 0
    with pytest.raises(RuntimeError, match="null"):
        worker.analyze({"mod_paths": [], "ordered": True}, lambda *_: None)
    assert not lib.freed
    lib.rcd_analyze.fn = lib._analyze
    monkeypatch.setattr(
        ctypes,
        "string_at",
        lambda *_: (_ for _ in ()).throw(RuntimeError("copy failed")),
    )
    with pytest.raises(RuntimeError, match="copy failed"):
        worker.analyze({"mod_paths": [], "ordered": True}, lambda *_: None)
    assert lib.freed == [ctypes.addressof(lib.buffer)]


def test_ffi_error_keeps_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import conflict_detector_worker as worker

    lib = FakeLibrary(b'{"error":"bad","diagnostics":[{"message":"details"}]}')
    monkeypatch.setattr(worker, "load_library", lambda: lib)
    with pytest.raises(RuntimeError, match="details"):
        worker.analyze({"mod_paths": [], "ordered": True}, lambda *_: None)


def assert_report_rejected(
    monkeypatch: pytest.MonkeyPatch, report: dict[str, object]
) -> None:
    from app.services import conflict_detector_worker as worker

    lib = FakeLibrary(json.dumps(report).encode())
    monkeypatch.setattr(worker, "load_library", lambda: lib)
    with pytest.raises((ValueError, TypeError)):
        worker.analyze({"mod_paths": [], "ordered": True}, lambda *_: None)


@pytest.mark.parametrize("field", ["metadata", "summary", "conflicts", "diagnostics"])
def test_missing_report_field_rejected(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    report = make_report("error", False)
    del report[field]
    assert_report_rejected(monkeypatch, report)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda report: report["conflicts"][0].pop("severity"),
        lambda report: report["diagnostics"][0].pop("analysis_incomplete"),
        lambda report: report["metadata"].pop("mods_scanned"),
        lambda report: report["summary"]["conflicts_by_severity"].pop("error"),
        lambda report: report["conflicts"][0]["target"].pop("def_name"),
        lambda report: report["metadata"]["mods_scanned"][0].pop("package_id"),
        lambda report: report["metadata"].__setitem__("order_aware", "yes"),
        lambda report: report["summary"].__setitem__("total_mods", "one"),
    ],
)
def test_invalid_v3_fields_rejected(
    monkeypatch: pytest.MonkeyPatch, mutate: Any
) -> None:
    report = make_report("error", False)
    mutate(report)
    assert_report_rejected(monkeypatch, report)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["metadata"]["mods_scanned"][0].__setitem__("package_id", None),
        lambda r: r["conflicts"][0]["target"].__setitem__("def_name", None),
        lambda r: r["conflicts"][0].__setitem__("mods", None),
        lambda r: r["conflicts"][0]["mods"][0].__setitem__("is_base_content", 1),
        lambda r: r["conflicts"][0].__setitem__(
            "mechanism", {"direct_replacement": {"divergent_fields": [None]}}
        ),
        lambda r: r["diagnostics"][0].__setitem__("severity", None),
        lambda r: r["diagnostics"][0].__setitem__("message", {}),
        lambda r: r["diagnostics"][0].__setitem__("source", "invented"),
    ],
)
def test_real_ffi_nested_mutations_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: Any
) -> None:
    from app.services import conflict_detector_worker as worker

    lib = os.environ.get("RIMSORT_RCD_LIBRARY")
    if not lib or not Path(lib).is_file():
        pytest.skip("set RIMSORT_RCD_LIBRARY to authorized debug library")
    monkeypatch.setenv("RIMSORT_DEV", "1")
    monkeypatch.setenv("RIMSORT_RCD_LIBRARY", lib)
    paths = []
    for name in ("a", "b"):
        root = tmp_path / name
        (root / "About").mkdir(parents=True)
        (root / "Defs").mkdir()
        (root / "Patches").mkdir()
        (root / "Patches" / "shared.xml").write_text(
            '<Patch><Operation Class="PatchOperationReplace"><xpath>Defs/ThingDef[defName="Steel"]/label</xpath></Operation></Patch>'
        )
        (root / "About" / "About.xml").write_text(
            f"<ModMetaData><packageId>example.{name}</packageId><name>{name}</name></ModMetaData>"
        )
        (root / "Defs" / "shared.xml").write_text(
            f"<Defs><ThingDef><defName>Steel</defName><label>{name}</label></ThingDef><SongDef><label>unnamed</label></SongDef></Defs>"
        )
        paths.append(str(root))
    report = worker.analyze({"mod_paths": paths, "ordered": True}, lambda *_: None)
    conflicts = report["conflicts"]
    assert isinstance(conflicts, list) and conflicts and report["diagnostics"]
    kinds = {kind for conflict in conflicts for kind in conflict["mechanism"]}
    assert {"direct_replacement", "x_path_overlap", "x_path_on_replaced_def"} <= kinds
    mutation(report)
    with pytest.raises((ValueError, TypeError)):
        worker._validate_report(report)


def test_rust_serialization_variants_are_accepted() -> None:
    from app.services import conflict_detector_worker as worker

    report = make_report("error", False)
    conflict = report["conflicts"][0]
    mechanisms = [
        {"direct_replacement": {"divergent_fields": ["label"]}},
        {"x_path_overlap": {"xpath_a": "a", "xpath_b": "b", "wildcard": False}},
        {"x_path_on_replaced_def": {"xpath": "a", "replaced_by": "b"}},
        {"xpath_same_def_non_overlap": {"xpath_pairs": [["a", "b"]]}},
    ]
    for mechanism in mechanisms:
        conflict["mechanism"] = mechanism
        worker._validate_report(report)
    mod = report["metadata"]["mods_scanned"][0]
    harmony: dict[str, Any] = {
        "type": "harmony",
        "severity": "info",
        "target": {"type_name": "T", "method_name": "M", "parameter_types": None},
        "patches": [
            {
                "mod_summary": mod,
                "dll_name": "a.dll",
                "patch_kind": "prefix",
                "priority": 0,
                "before": [],
                "after": [],
                "returns_bool": False,
            }
        ],
        "short_circuit_risk": False,
        "execution_order": None,
    }
    report["conflicts"] = [harmony]
    report["summary"]["conflicts_by_severity"] = {"error": 0, "warning": 0, "info": 1}
    worker._validate_report(report)
    for kind in ("prefix", "postfix", "transpiler", "finalizer"):
        harmony["patches"][0]["patch_kind"] = kind
        worker._validate_report(report)
    harmony["target"]["parameter_types"] = ["System.String"]
    harmony["execution_order"] = ["example.a"]
    worker._validate_report(report)
    mutations: list[Callable[[Any], None]] = [
        lambda conflict: conflict["patches"][0].__setitem__("priority", True),
        lambda conflict: conflict["patches"][0]["mod_summary"].__setitem__(
            "name", None
        ),
        lambda conflict: conflict["patches"][0].__setitem__("patch_kind", "invented"),
        lambda conflict: conflict["patches"][0].__setitem__("before", [None]),
        lambda conflict: conflict["patches"][0].__setitem__("returns_bool", 1),
        lambda conflict: conflict["target"].__setitem__("parameter_types", [None]),
        lambda conflict: conflict.__setitem__("execution_order", [None]),
        lambda conflict: conflict.__setitem__("short_circuit_risk", 1),
    ]
    for mutation in mutations:
        malformed = copy.deepcopy(report)
        malformed_conflict = malformed["conflicts"][0]
        mutation(malformed_conflict)
        with pytest.raises((TypeError, ValueError)):
            worker._validate_report(malformed)


@pytest.mark.parametrize("version", [3.0, True, False, "3", None])
def test_schema_version_requires_integer_three(version: object) -> None:
    from app.services.conflict_detector_worker import _validate_report

    report = make_report("error", False)
    report["schema_version"] = version
    with pytest.raises(ValueError, match="schema"):
        _validate_report(report)


def test_integer_schema_and_unbounded_summary_counts_are_accepted() -> None:
    from app.services.conflict_detector_worker import _validate_report

    report = make_report("error", False)
    summary = report["summary"]
    assert isinstance(summary, dict)
    large_count = 2**128
    summary["total_mods"] = large_count
    summary["mods_with_conflicts"] = large_count
    summary["conflicts_by_severity"] = dict.fromkeys(
        ("error", "warning", "info"), large_count
    )
    assert _validate_report(report) is report


def test_actual_debug_ffi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import conflict_detector_worker as worker

    lib_path = os.environ.get("RIMSORT_RCD_LIBRARY")
    if not lib_path:
        pytest.skip("set RIMSORT_RCD_LIBRARY to an authorized local debug library")
    lib = Path(lib_path)
    if not lib.is_file():
        pytest.skip("local authorized debug library unavailable")
    mod = tmp_path / "example"
    (mod / "About").mkdir(parents=True)
    (mod / "About" / "About.xml").write_text(
        "<ModMetaData><name>Example</name><packageId>test.example</packageId></ModMetaData>"
    )
    monkeypatch.setenv("RIMSORT_DEV", "1")
    monkeypatch.setenv("RIMSORT_RCD_LIBRARY", str(lib))
    report = worker.analyze({"mod_paths": [str(mod)], "ordered": True}, lambda *_: None)
    assert report["schema_version"] == 3
    metadata = report["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["mods_scanned"][0]["package_id"] == "test.example"
