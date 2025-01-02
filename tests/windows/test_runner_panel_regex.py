import re
import pytest


@pytest.mark.parametrize(
    "test_string",
    [
        "IPublishedFileService/QueryFiles page [40/100]",
        "IPublishedFileService/GetDetails chunk [40/100]",
    ],
)
def test_dbbuilder_progress_regex(test_string: str) -> None:
    """
    Verify that lines related to IPublishedFileService/QueryFiles and
    IPublishedFileService/GetDetails in the DB Builder runner panel output
    can be parsed by a consistent regular expression.

    This ensures lines of the form:
        "IPublishedFileService/<Method> <Label> [<Current>/<Total>]"
    can be properly recognized and captured.

    Example:
        "IPublishedFileService/QueryFiles page [40/100]"
        "IPublishedFileService/GetDetails chunk [40/100]"

    The regex will capture:
      - <Method>: 'QueryFiles' or 'GetDetails'
      - <Label>: 'page' or 'chunk'
      - <Current>: '40'
      - <Total>: '100'
    """
    pattern = re.compile(
        r"^IPublishedFileService/(QueryFiles|GetDetails)\s+(page|chunk)\s+\[(\d+)/(\d+)\]$"
    )

    match = pattern.search(test_string)
    assert match is not None, f"Regex did not match the expected format: '{test_string}'"

    method, label, current, total = match.group(1), match.group(2), match.group(3), match.group(4)

    # Validate the captured subgroups
    assert method in ("QueryFiles", "GetDetails"), f"Invalid method: {method}"
    assert label in ("page", "chunk"), f"Invalid label: {label}"
    assert current.isdigit(), f"'current' not a digit: {current}"
    assert total.isdigit(), f"'total' not a digit: {total}"

