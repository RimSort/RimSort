"""Lint guard: fail on new function-local imports from app/ outside an allowlist.

Scans every .py file under app/ for `from app.` / `import app.` statements
that appear inside function bodies (deferred imports).  Any import NOT in
ALLOWED is reported as an error, preventing regression of circular-import
cleanup (Phase 2).

Usage:
    uv run python check_deferred_imports.py
"""

import ast
import sys
from pathlib import Path

ALLOWED: set[str] = {
    # __main__ cli entry point — intentionally deferred
    "app/__main__.py: from app.cli.main import cli",
    # Genuine circular: worker → updater (noted in code comment)
    "app/utils/github/worker.py: from app.utils.github.updater import check_for_updates",
    # Startup-performance: installer hot path
    "app/utils/github/installer.py: from app.utils import http",
    "app/utils/github/installer.py: from app.utils import git_utils",
    "app/utils/github/installer.py: from app.utils.git_utils import GitOperationConfig",
    # Window import is heavy; TYPE_CHECKING also covers the type
    "app/controllers/main_content_controller.py: from app.windows.github_mods_panel import GitHubModsPanel",
    # Genuine circular: settings_dialog ↔ language_controller
    "app/views/settings_dialog.py: from app.controllers.language_controller import LanguageController",
    # Platform-guarded: find_steam_folder only defined on win32
    "app/controllers/settings_controller.py: from app.utils.win_find_steam import find_steam_folder",
    "app/utils/steam/availability.py: from app.utils.win_find_steam import find_steam_folder",
}

PROJECT_ROOT = Path(__file__).resolve().parent


def _normalise(line: str) -> str:
    return line.strip().rstrip(",").strip()


def _import_key(file_rel: str, node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        names = [a.name for a in node.names]
        app_names = [n for n in names if n.startswith("app") or n.startswith("app.")]
        if not app_names:
            return None
        return f"{file_rel}: import {', '.join(sorted(app_names))}"
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if not module.startswith("app"):
            return None
        names = sorted(a.name for a in node.names)
        return f"{file_rel}: from {module} import {', '.join(names)}"
    return None


def check_file(path: Path) -> list[str]:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    errors: list[str] = []

    for node in ast.walk(tree):
        # Only look inside function / method bodies
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue  # skip nested functions (their own deferred imports are handled separately)
            key = _import_key(rel, child)
            if key and key not in ALLOWED:
                errors.append(key)

    return errors


def main() -> int:
    all_errors: list[str] = []
    app_dir = PROJECT_ROOT / "app"
    for path in sorted(app_dir.rglob("*.py")):
        try:
            errors = check_file(path)
            all_errors.extend(errors)
        except Exception as exc:
            print(f"Error scanning {path}: {exc}", file=sys.stderr)
            return 1

    if all_errors:
        print(
            "ERROR: Unauthorised deferred imports found (add to ALLOWED or hoist):",
            file=sys.stderr,
        )
        for err in sorted(all_errors):
            print(f"  {err}", file=sys.stderr)
        print(file=sys.stderr)
        print(
            "If this is a genuine circular dependency, add it to the ALLOWED set in",
            file=sys.stderr,
        )
        print("  check_deferred_imports.py", file=sys.stderr)
        return 1

    print("OK: no unauthorised deferred imports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
