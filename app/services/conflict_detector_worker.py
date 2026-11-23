"""Isolated JSON/ctypes worker for the native conflict detector."""

import ctypes
import json
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path

ProgressCallback = ctypes.CFUNCTYPE(
    None, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_char_p
)


def _compiled() -> bool:
    return "__compiled__" in globals() or bool(getattr(sys, "frozen", False))


def library_path() -> Path:
    compiled = _compiled()
    packaged = os.environ.get("RIMSORT_RCD_PACKAGED") == "1"
    override = os.environ.get("RIMSORT_RCD_LIBRARY")
    if (
        not compiled
        and not packaged
        and os.environ.get("RIMSORT_DEV") == "1"
        and override
    ):
        path = Path(override)
        if not path.is_absolute():
            raise ValueError("RIMSORT_RCD_LIBRARY must be an absolute path")
        return path
    name = {"win32": "rcd_ffi.dll", "darwin": "librcd_ffi.dylib"}.get(
        sys.platform, "librcd_ffi.so"
    )
    root = (
        Path(sys.executable).resolve().parent
        if compiled
        else Path(__file__).resolve().parents[2]
    )
    return root / name


def load_library() -> ctypes.CDLL:
    return ctypes.CDLL(str(library_path()))


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _optional_string(value: object) -> bool:
    return value is None or isinstance(value, str)


def _mod_valid(value: object) -> bool:
    return (
        isinstance(value, dict)
        and {"package_id", "name", "author", "is_base_content"} <= value.keys()
        and isinstance(value["package_id"], str)
        and isinstance(value["name"], str)
        and _optional_string(value["author"])
        and isinstance(value["is_base_content"], bool)
    )


def _mechanism_valid(value: object) -> bool:
    if not isinstance(value, dict) or len(value) != 1:
        return False
    kind, body = next(iter(value.items()))
    if not isinstance(body, dict):
        return False
    if kind == "direct_replacement":
        return _strings(body.get("divergent_fields"))
    if kind == "x_path_overlap":
        return (
            isinstance(body.get("xpath_a"), str)
            and isinstance(body.get("xpath_b"), str)
            and isinstance(body.get("wildcard"), bool)
        )
    if kind == "x_path_on_replaced_def":
        return isinstance(body.get("xpath"), str) and isinstance(
            body.get("replaced_by"), str
        )
    if kind == "xpath_same_def_non_overlap":
        pairs = body.get("xpath_pairs")
        return isinstance(pairs, list) and all(
            isinstance(pair, list) and len(pair) == 2 and _strings(pair)
            for pair in pairs
        )
    return False


def _patch_valid(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    priority = value.get("priority")
    return (
        _mod_valid(value.get("mod_summary"))
        and isinstance(value.get("dll_name"), str)
        and value.get("patch_kind") in ("prefix", "postfix", "transpiler", "finalizer")
        and type(priority) is int
        and -(2**31) <= priority < 2**31
        and _strings(value.get("before"))
        and _strings(value.get("after"))
        and isinstance(value.get("returns_bool"), bool)
    )


def _conflict_valid(value: object) -> bool:
    if not isinstance(value, dict) or value.get("severity") not in (
        "error",
        "warning",
        "info",
    ):
        return False
    target = value.get("target")
    if not isinstance(target, dict):
        return False
    if value.get("type") == "def":
        mods = value.get("mods")
        return (
            isinstance(target.get("def_type"), str)
            and isinstance(target.get("def_name"), str)
            and isinstance(mods, list)
            and all(_mod_valid(mod) for mod in mods)
            and _mechanism_valid(value.get("mechanism"))
            and "winner" in value
            and _optional_string(value["winner"])
            and "condition" in value
            and _optional_string(value["condition"])
        )
    if value.get("type") == "harmony":
        patches = value.get("patches")
        parameters = target.get("parameter_types")
        order = value.get("execution_order")
        return (
            isinstance(target.get("type_name"), str)
            and isinstance(target.get("method_name"), str)
            and "parameter_types" in target
            and (parameters is None or _strings(parameters))
            and isinstance(patches, list)
            and all(_patch_valid(patch) for patch in patches)
            and isinstance(value.get("short_circuit_risk"), bool)
            and "execution_order" in value
            and (order is None or _strings(order))
        )
    return False


def _diagnostic_valid(value: object) -> bool:
    return (
        isinstance(value, dict)
        and "affected_mod" in value
        and _optional_string(value["affected_mod"])
        and value.get("severity") in ("error", "warning", "info")
        and isinstance(value.get("message"), str)
        and value.get("source")
        in (
            "xml_parsing",
            "dll_parsing",
            "metadata_resolution",
            "folder_resolution",
            "mods_config",
        )
        and isinstance(value.get("analysis_incomplete"), bool)
        and _optional_string(value.get("code"))
        and isinstance(value.get("params", {}), dict)
        and all(
            isinstance(key, str) and isinstance(param, str)
            for key, param in value.get("params", {}).items()
        )
    )


def _validate_report(value: object) -> dict[str, object]:
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value.get("schema_version") != 3
    ):
        raise ValueError("Invalid or unsupported conflict report schema")
    metadata = value.get("metadata")
    summary = value.get("summary")
    conflicts = value.get("conflicts")
    diagnostics = value.get("diagnostics")
    if (
        not isinstance(metadata, dict)
        or not {"timestamp", "game_version", "order_aware", "mods_scanned"}
        <= metadata.keys()
    ):
        raise ValueError("Invalid conflict report metadata")
    if (
        not isinstance(summary, dict)
        or not {"total_mods", "mods_with_conflicts", "conflicts_by_severity"}
        <= summary.keys()
    ):
        raise ValueError("Invalid conflict report summary")
    if (
        not isinstance(metadata["timestamp"], str)
        or not isinstance(metadata["game_version"], (str, type(None)))
        or not isinstance(metadata["order_aware"], bool)
        or not isinstance(metadata["mods_scanned"], list)
    ):
        raise TypeError("Invalid conflict report metadata types")
    if not all(_mod_valid(mod) for mod in metadata["mods_scanned"]):
        raise ValueError("Invalid scanned mod")
    if any(
        type(summary[key]) is not int or summary[key] < 0
        for key in ("total_mods", "mods_with_conflicts")
    ):
        raise ValueError("Invalid conflict summary counts")
    counts = summary["conflicts_by_severity"]
    if not isinstance(counts, dict) or not all(
        type(counts.get(severity)) is int and counts[severity] >= 0
        for severity in ("error", "warning", "info")
    ):
        raise ValueError("Invalid conflict severity counts")
    if not isinstance(conflicts, list) or not isinstance(diagnostics, list):
        raise TypeError("Invalid conflict report lists")
    if not all(_conflict_valid(conflict) for conflict in conflicts):
        raise ValueError("Invalid conflict")
    if not all(_diagnostic_valid(diagnostic) for diagnostic in diagnostics):
        raise ValueError("Invalid conflict diagnostic")
    return value


def analyze(
    config: dict[str, object], on_progress: Callable[[int, int, str], None]
) -> dict[str, object]:
    config = config.copy()
    if config.get("game_version") is None or (
        isinstance(config.get("game_version"), str)
        and str(config["game_version"]).lower() == "unknown"
    ):
        config.pop("game_version", None)
    paths = config.get("mod_paths")
    if (
        not isinstance(paths, list)
        or not all(isinstance(p, str) and Path(p).is_absolute() for p in paths)
        or config.get("ordered") is not True
    ):
        raise ValueError("Expected absolute mod_paths and ordered=true")
    library = load_library()
    library.rcd_analyze.argtypes = [ctypes.c_char_p, ProgressCallback]
    library.rcd_analyze.restype = ctypes.c_void_p
    library.rcd_free.argtypes = [ctypes.c_void_p]
    library.rcd_free.restype = None
    callback_errors: list[Exception] = []

    def on_native_progress(current: int, total: int, phase: bytes | None) -> None:
        try:
            on_progress(current, total, (phase or b"").decode("utf-8"))
        except Exception as exc:
            callback_errors.append(exc)

    callback = ProgressCallback(on_native_progress)
    pointer = library.rcd_analyze(
        json.dumps(config, ensure_ascii=False).encode("utf-8"), callback
    )
    if not pointer:
        raise RuntimeError("Conflict detector returned a null pointer")
    try:
        raw = ctypes.string_at(pointer)
    finally:
        library.rcd_free(pointer)
    if callback_errors:
        raise callback_errors[0]
    value = json.loads(raw)
    if isinstance(value, dict) and "error" in value:
        raise RuntimeError(json.dumps(value, ensure_ascii=False))
    return _validate_report(value)


def main() -> int:
    request_id = ""
    lock = threading.Lock()

    def emit(kind: str, **fields: object) -> None:
        frame = {"protocol": 1, "id": request_id, "kind": kind, **fields}
        with lock:
            sys.stdout.buffer.write(
                (json.dumps(frame, ensure_ascii=False) + "\n").encode("utf-8")
            )
            sys.stdout.buffer.flush()

    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if (
            not isinstance(request, dict)
            or request.get("protocol") != 1
            or not isinstance(request.get("id"), str)
            or not isinstance(request.get("config"), dict)
        ):
            raise ValueError("Invalid worker request")
        request_id = request["id"]
        report = analyze(
            request["config"],
            lambda current, total, phase: emit(
                "progress", current=current, total=total, phase=phase
            ),
        )
        emit("report", report=report)
        return 0
    except Exception as exc:
        emit("error", error=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
