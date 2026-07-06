"""Guards against regressions in pyside6-lupdate's ability to extract
translatable strings from app/ source.

`pyside6-lupdate` recognizes two distinct call shapes:
- `obj.tr(sourceText, disambiguation=None, n=-1)`
- `QCoreApplication.translate(context, sourceText, disambiguation=None, n=-1)`

It dispatches on the literal call syntax, not on what the callee actually
resolves to. A module-level alias like `tr = QCoreApplication.translate`
followed by `tr("SomeContext", "Some text")` is silently misread as the
first shape: lupdate records "SomeContext" as the translatable *source*
text and "Some text" as a disambiguation comment, so the real string is
never extracted into any .ts file. See app/services/instance_service.py
history for a real instance of this.
"""

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Matches `tr = QCoreApplication.translate` (with any amount of whitespace
# around `=`), which is the pattern that breaks lupdate's static extraction.
_ALIAS_PATTERN = re.compile(r"^\s*tr\s*=\s*QCoreApplication\.translate\s*$")


def test_no_module_level_tr_alias_of_qcoreapplication_translate() -> None:
    offending: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if _ALIAS_PATTERN.match(line):
                offending.append(f"{path.relative_to(APP_DIR.parent)}:{lineno}")

    assert not offending, (
        "Found `tr = QCoreApplication.translate` module-level alias(es), which "
        "pyside6-lupdate cannot statically extract correctly (it misreads "
        "`tr(context, text)` as `obj.tr(sourceText, disambiguation)`, swapping "
        "them). Call `QCoreApplication.translate(context, text)` directly "
        f"instead. Offending location(s): {offending}"
    )
