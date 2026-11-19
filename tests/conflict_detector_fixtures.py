import copy
import shutil
import subprocess
import xml.etree.ElementTree as ET
from itertools import count
from pathlib import Path
from typing import Any

import pytest


def _make_mod(package_id: str, name: str) -> dict[str, Any]:
    return {
        "package_id": package_id,
        "name": name,
        "author": None,
        "is_base_content": False,
    }


def make_report(severity: str, diagnostic_incomplete: bool) -> dict[str, Any]:
    mod = _make_mod("example.a", "A")
    return {
        "schema_version": 3,
        "metadata": {
            "timestamp": "2026-01-01T00:00:00Z",
            "game_version": None,
            "order_aware": True,
            "mods_scanned": [mod],
        },
        "conflicts": [
            {
                "type": "def",
                "severity": severity,
                "target": {"def_type": "ThingDef", "def_name": "A"},
                "mods": [mod],
                "mechanism": (
                    {"direct_replacement": {"divergent_fields": []}}
                    if severity == "error"
                    else {
                        "x_path_overlap": {
                            "xpath_a": "a",
                            "xpath_b": "b",
                            "wildcard": severity == "info",
                        }
                    }
                ),
                "winner": None,
                "condition": None,
            }
        ],
        "diagnostics": [
            {
                "affected_mod": None,
                "severity": "info",
                "message": "fixture",
                "source": "xml_parsing",
                "analysis_incomplete": diagnostic_incomplete,
            }
        ],
        "summary": {
            "total_mods": 1,
            "mods_with_conflicts": 1,
            "conflicts_by_severity": {
                name: int(name == severity) for name in ("error", "warning", "info")
            },
        },
    }


def make_notes_diagnostics() -> list[dict[str, Any]]:
    return [
        {
            "source": "xml_parsing",
            "severity": severity,
            "analysis_incomplete": incomplete,
            "message": message,
            "affected_mod": None,
        }
        for severity, incomplete, message in (
            ("info", True, "incomplete"),
            ("warning", False, "warning"),
            ("error", False, "error"),
            ("info", False, "ordinary"),
        )
    ]


def force_one_row_per_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models import conflict_report

    moments = count()
    monkeypatch.setattr(
        conflict_report.time,
        "monotonic",
        lambda: next(moments) * 0.009,
    )


def make_triage_report_with_counts(
    error_count: int, warning_count: int, info_count: int
) -> dict[str, Any]:
    report = copy.deepcopy(make_triage_report())
    remaining = {"error": error_count, "warning": warning_count, "info": info_count}
    conflicts = []
    for finding in report["conflicts"]:
        severity = finding["severity"]
        if remaining[severity] > 0:
            conflicts.append(finding)
            remaining[severity] -= 1
    report["conflicts"] = conflicts
    report["summary"]["conflicts_by_severity"] = {
        "error": error_count,
        "warning": warning_count,
        "info": info_count,
    }
    affected_mods: set[str] = set()
    for finding in conflicts:
        if finding["type"] == "def":
            affected_mods.update(mod["package_id"] for mod in finding["mods"])
        else:
            affected_mods.update(
                patch["mod_summary"]["package_id"] for patch in finding["patches"]
            )
    report["summary"]["mods_with_conflicts"] = len(affected_mods)
    return report


def make_triage_report_with_moved_selection() -> dict[str, Any]:
    report = make_triage_report()
    report["conflicts"].extend(
        [
            copy.deepcopy(report["conflicts"][2]),
            copy.deepcopy(report["conflicts"][0]),
            copy.deepcopy(report["conflicts"][0]),
        ]
    )
    report["summary"]["conflicts_by_severity"] = {
        "error": 2,
        "warning": 2,
        "info": 3,
    }
    return report


def make_large_triage_report(reference_count: int) -> dict[str, Any]:
    if reference_count % 4 != 0:
        raise ValueError("reference_count must be divisible by 4")
    report = make_triage_report()
    base_conflicts = report["conflicts"]
    groups = reference_count // len(base_conflicts)
    report["conflicts"] = [
        base_conflicts[index % len(base_conflicts)] for index in range(reference_count)
    ]
    report["summary"] = {
        "total_mods": 4,
        "mods_with_conflicts": 3,
        "conflicts_by_severity": {
            "error": groups * 2,
            "warning": groups,
            "info": groups,
        },
    }
    return report


def make_triage_report_with_duplicate_participant_names(
    finding_type: str,
) -> dict[str, Any]:
    report = copy.deepcopy(make_triage_report())
    if finding_type == "def":
        first_mod = copy.deepcopy(report["conflicts"][0]["mods"][0])
        second_mod = copy.deepcopy(first_mod)
        first_mod["name"] = "Alpha Root"
        second_mod["name"] = "Alias Bloom"
        report["conflicts"][0]["mods"] = [first_mod, second_mod]
        return report
    if finding_type == "harmony":
        first_patch = report["conflicts"][3]["patches"][0]
        second_patch = report["conflicts"][3]["patches"][1]
        first_patch["mod_summary"] = copy.deepcopy(first_patch["mod_summary"])
        second_patch["mod_summary"] = copy.deepcopy(second_patch["mod_summary"])
        first_patch["mod_summary"]["name"] = "Alpha Root"
        second_patch["mod_summary"]["name"] = "Alias Bloom"
        return report
    raise ValueError(f"unsupported finding type: {finding_type}")


def extract_context_sources(
    tmp_path: Path,
    source: Path | list[Path] | tuple[Path, ...],
    catalog_name: str,
    context_name: str,
) -> set[str]:
    lupdate = shutil.which("pyside6-lupdate")
    assert lupdate is not None
    catalog = tmp_path / catalog_name
    sources = [source] if isinstance(source, Path) else list(source)
    subprocess.run(
        [lupdate, *(str(path) for path in sources), "-ts", str(catalog)],
        check=True,
        capture_output=True,
        timeout=20,
    )
    contexts = ET.parse(catalog).findall("context")
    context = next(c for c in contexts if c.findtext("name") == context_name)
    return {
        message.text
        for message in context.findall("message/source")
        if message.text is not None
    }


def make_triage_report() -> dict[str, Any]:
    mod_a = _make_mod("example.a", "A")
    mod_b = _make_mod("example.b", "B")
    mod_c = _make_mod("example.c", "C")
    mod_d = _make_mod("example.d", "D")
    return {
        "schema_version": 3,
        "metadata": {
            "timestamp": "2026-01-01T00:00:00Z",
            "game_version": "1.6.1234",
            "order_aware": True,
            "mods_scanned": [mod_a, mod_b, mod_c, mod_d],
        },
        "conflicts": [
            {
                "type": "def",
                "severity": "info",
                "target": {"def_type": "ThingDef", "def_name": "Shared"},
                "mods": [mod_a, mod_b],
                "mechanism": {
                    "x_path_overlap": {
                        "xpath_a": '/Defs/ThingDef[defName="Shared"]/*',
                        "xpath_b": '/Defs/ThingDef[defName="Shared"]/label',
                        "wildcard": True,
                    }
                },
                "winner": None,
                "condition": None,
            },
            {
                "type": "def",
                "severity": "error",
                "target": {"def_type": "ThingDef", "def_name": "Shared"},
                "mods": [mod_a, mod_b],
                "mechanism": {"direct_replacement": {"divergent_fields": ["label"]}},
                "winner": "example.b",
                "condition": None,
            },
            {
                "type": "def",
                "severity": "warning",
                "target": {"def_type": "ThingDef", "def_name": "Other"},
                "mods": [mod_b, mod_c],
                "mechanism": {
                    "x_path_overlap": {
                        "xpath_a": '/Defs/ThingDef[defName="Other"]/description',
                        "xpath_b": '/Defs/ThingDef[defName="Other"]/statBases/MarketValue',
                        "wildcard": False,
                    }
                },
                "winner": None,
                "condition": None,
            },
            {
                "type": "harmony",
                "severity": "error",
                "target": {
                    "type_name": "Verse.Pawn",
                    "method_name": "Tick",
                    "parameter_types": [],
                },
                "patches": [
                    {
                        "mod_summary": mod_a,
                        "dll_name": "a-main.dll",
                        "patch_kind": "prefix",
                        "priority": 400,
                        "before": [],
                        "after": [],
                        "returns_bool": True,
                    },
                    {
                        "mod_summary": mod_a,
                        "dll_name": "a-extra.dll",
                        "patch_kind": "prefix",
                        "priority": 300,
                        "before": [],
                        "after": [],
                        "returns_bool": True,
                    },
                    {
                        "mod_summary": mod_c,
                        "dll_name": "c.dll",
                        "patch_kind": "prefix",
                        "priority": 200,
                        "before": [],
                        "after": [],
                        "returns_bool": True,
                    },
                ],
                "short_circuit_risk": True,
                "execution_order": ["example.a", "example.c"],
            },
        ],
        "diagnostics": [
            {
                "affected_mod": None,
                "severity": "info",
                "message": "fixture",
                "source": "xml_parsing",
                "analysis_incomplete": False,
            }
        ],
        "summary": {
            "total_mods": 4,
            "mods_with_conflicts": 3,
            "conflicts_by_severity": {"error": 2, "warning": 1, "info": 1},
        },
    }
