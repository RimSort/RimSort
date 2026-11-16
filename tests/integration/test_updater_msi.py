"""Exercise the packaged updater through its MSI handoff on disposable Windows CI."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from tests.integration.msi_helpers import require_windows_ci
from tests.integration.test_packaged_upgrade import (
    configure,
    digest,
    environment,
    manifest,
    serve,
    stop_all,
    update,
    wait_for,
)
from tests.integration.test_windows_msi import (
    LAUNCHER,
    UPGRADE_CODE,
    configure_profile,
    database,
    inspect_package,
    install,
    print_diagnostics,
    run_msi,
    state,
    stop_owned_apps,
    verify_gui,
)


def test_native_msi_updater_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot: QtBot
) -> None:
    candidate_arg = os.environ.get("RIMSORT_MSI_CANDIDATE")
    if sys.platform != "win32" or not candidate_arg:
        pytest.skip("Requires native Windows CI and explicit MSI inputs")
    require_windows_ci(tmp_path)
    root = tmp_path / "MSI updater path 'test'"
    root.mkdir()
    baseline = inspect_package(Path(candidate_arg))
    next_package = root / "next-build.msi"
    database("Clone", MsiPath=str(baseline.path), CopyPath=str(next_package))
    candidate = inspect_package(next_package)
    assert baseline.code != candidate.code
    assert baseline.package_code != candidate.package_code
    assert (
        baseline.files == candidate.files and baseline.component == candidate.component
    )
    assert state(baseline)[0] == -1 and state(candidate)[0] == -1
    assert database("Related", UpgradeCode=UPGRADE_CODE) == []
    target = root / "install/RimSort.exe"
    cleanup_ok = False
    try:
        with environment(root, target, "msi") as env:
            configure_profile(root, monkeypatch)
            install(root, "baseline", baseline, qtbot)
            configure(root, target, env)
            sentinel = root / "profile/data/keep.txt"
            sentinel.write_text("preserve user data")
            original = manifest(root / "install")
            transform_arguments = (
                subprocess.list2cmdline(["-I", str(LAUNCHER), str(root), "upgrade"])
                + ' "[RIMSORTTARGET]"'
            )
            database(
                "Transform",
                MsiPath=str(candidate.path),
                TransformPath=str(root / "upgrade.mst"),
                PythonPath=sys.executable,
                LaunchArguments=transform_arguments,
            )
            payload = root / "candidate.msi"
            shutil.copy2(candidate.path, payload)
            with serve(root, payload.name) as (url, requests):
                update(root, target, env, url, "", kind="msi")
                wait_for(
                    (root / "events/installer-exit.json").exists,
                    "native updater MSI completion",
                )
            assert f"GET /{payload.name} 200" in requests
            handoff = json.loads((root / "events/msi-handoff.json").read_text())[
                "command"
            ]
            assert digest(Path(handoff[2])) == digest(candidate.path)
            assert (
                json.loads((root / "events/installer-exit.json").read_text())["code"]
                == 0
            )
            assert state(baseline)[0] == -1
            installed_state, location = state(candidate)
            assert installed_state == 5 and Path(location).resolve() == target.resolve()
            verify_gui(root, "upgrade", qtbot)
            expected = manifest(Path(os.environ["RIMSORT_MSI_EXPECTED_DIR"]))
            assert manifest(root / "install") == expected
            configured = json.loads((root / "events/configured.json").read_text())
            backups = list(Path(configured["backups"]).glob("RimSort_Backup_*.zip"))
            assert len(backups) == 1
            with zipfile.ZipFile(backups[0]) as backup:
                actual = {
                    item.filename: hashlib.sha256(backup.read(item)).hexdigest()
                    for item in backup.infolist()
                    if not item.is_dir()
                }
            assert actual == original
            assert sentinel.read_text() == "preserve user data"
    finally:
        try:
            stop_all(root)
            stop_owned_apps(root)
            failures = []
            for package in (candidate, baseline):
                try:
                    if state(package)[0] != -1:
                        assert (
                            run_msi(
                                root, f"uninstall-{package.code}", ["/x", package.code]
                            )
                            == 0
                        )
                    assert state(package)[0] == -1
                except Exception as error:
                    failures.append(str(error))
            assert not failures, failures
            assert database("Related", UpgradeCode=UPGRADE_CODE) == []
            cleanup_ok = True
        finally:
            print_diagnostics(root)
            if cleanup_ok:
                shutil.rmtree(root)
