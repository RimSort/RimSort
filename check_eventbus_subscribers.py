"""Lint guard: fail on EventBus subscribers that are not retained.

`EventBus` (`app/utils/event_bus.py`) is a QObject singleton and Qt keeps a
strong reference to QObject/QWidget receivers, but it does **not** keep one for
a bound method of a plain Python object. When such an object connects its slots
in ``__init__`` and nobody retains it, CPython collects it the moment the
constructor returns and every slot silently stops running -- no log line, no
exception. That is how the instance actions (backup/restore/clone/create/
delete) became dead no-ops in every release from v1.6.0 onwards (#2539).

This guard flags any class that connects `EventBus` signals while not being a
QObject/QWidget descendant, unless it is listed in ALLOWED with a note saying
who retains it. For flagged classes the fix is normally one line in the
constructing code: keep the reference (``self.foo = Foo(...)``).

Usage:
    uv run python check_eventbus_subscribers.py
"""

import ast
import sys
from pathlib import Path

# Classes rooted in these Qt types are kept alive by Qt itself, so connecting
# bound methods of them is safe regardless of Python references.
QT_ROOTS: frozenset[str] = frozenset(
    {
        "QAbstractItemModel",
        "QDialog",
        "QFrame",
        "QMainWindow",
        "QObject",
        "QRunnable",
        "QSortFilterProxyModel",
        "QThread",
        "QWidget",
    }
)

# Receivers that are not Qt types but are kept alive by their owner. Each entry
# must name the owner so a future reviewer can verify the reference still
# exists -- if it is deleted, delete the entry too.
ALLOWED: dict[str, str] = {
    # Retained by AppController.instance_service. Guarded by
    # tests/services/test_instance_service_lifetime.py, which fails if the
    # reference is dropped again (see #2539).
    "app/services/instance_service.py:InstanceService": (
        "held as AppController.instance_service"
    ),
    # Retained by SettingsController._tab_controllers registry
    "app/controllers/settings_tabs/sorting_tab_controller.py:SortingTabController": (
        "held in SettingsController._tab_controllers"
    ),
    # Class-level singleton cache (_instance)
    "app/utils/steam/steamcmd/wrapper.py:SteamcmdInterface": (
        "SteamcmdInterface._instance singleton"
    ),
    # Retained as MainContent.mod_info_panel
    "app/views/mod_info_panel.py:ModInfoPanel": "held as MainContent.mod_info_panel",
}

PROJECT_ROOT = Path(__file__).resolve().parent
_APP_DIR = PROJECT_ROOT / "app"

# Any receiver expression naming these is treated as an EventBus subscription.
_EVENTBUS_TOKENS = ("EventBus", "event_bus")


def _is_eventbus_connect(node: ast.Call) -> bool:
    """Report whether this call is ``<event bus>.some_signal.connect(...)``."""
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "connect":
        return False
    return any(token in ast.unparse(node.func.value) for token in _EVENTBUS_TOKENS)


def _collect_classes(
    tree: ast.Module, rel: str
) -> tuple[dict[str, set[str]], dict[str, int]]:
    """Map every class name to its base names and list EventBus subscriptions.

    :param tree: Parsed module.
    :param rel: Repo-relative path of the module, used in subscription keys.
    :return: Tuple of (class name -> base names, "<rel>:<class>" -> first line).
    """
    bases_by_name: dict[str, set[str]] = {}
    first_line: dict[str, int] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases_by_name.setdefault(node.name, set()).update(
            base.id for base in node.bases if isinstance(base, ast.Name)
        )
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and _is_eventbus_connect(child):
                first_line.setdefault(f"{rel}:{node.name}", child.lineno)

    return bases_by_name, first_line


def _is_qt_derived(class_name: str, bases_by_name: dict[str, set[str]]) -> bool:
    """Resolve ancestry through repo-internal classes to a Qt root.

    :param class_name: Class to test.
    :param bases_by_name: Known class name -> base names mapping.
    :return: True when the class inherits from a Qt type, transitively.
    """
    seen: set[str] = set()
    pending = [class_name]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if current in QT_ROOTS:
            return True
        pending.extend(bases_by_name.get(current, set()))
    return False


def main() -> int:
    all_errors: list[str] = []
    bases_by_name: dict[str, set[str]] = {}
    subscribers: dict[str, int] = {}

    for path in sorted(_APP_DIR.rglob("*.py")):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            print(f"Error parsing {rel}: {exc}", file=sys.stderr)
            return 1
        try:
            file_bases, file_subs = _collect_classes(tree, rel)
        except Exception as exc:
            print(f"Error scanning {rel}: {exc}", file=sys.stderr)
            return 1
        bases_by_name.update(file_bases)
        subscribers.update(file_subs)

    for key, lineno in subscribers.items():
        class_name = key.split(":")[-1]
        if key in ALLOWED or _is_qt_derived(class_name, bases_by_name):
            continue
        all_errors.append(f"{key} subscribes to EventBus (line {lineno})")

    if all_errors:
        print(
            "ERROR: EventBus subscribers that are not Qt objects and are not"
            " proven to be retained:",
            file=sys.stderr,
        )
        for err in sorted(all_errors):
            print(f"  {err}", file=sys.stderr)
        print(file=sys.stderr)
        print(
            "PySide6 does not keep bound-method receivers alive, so a plain"
            " class that is not retained",
            file=sys.stderr,
        )
        print(
            "  is garbage collected and its slots silently stop running (see"
            " #2539). Either:",
            file=sys.stderr,
        )
        print(
            "  - make it a QObject subclass, or retain it in the constructing"
            " code (self.foo = Foo()),",
            file=sys.stderr,
        )
        print(
            "  - or, if it genuinely is retained elsewhere, add it to ALLOWED in",
            file=sys.stderr,
        )
        print(
            "  check_eventbus_subscribers.py with a note naming the owner.",
            file=sys.stderr,
        )
        return 1

    print("OK: all EventBus subscribers are Qt objects or explicitly retained")
    return 0


if __name__ == "__main__":
    sys.exit(main())
