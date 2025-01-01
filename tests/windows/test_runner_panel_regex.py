import re
import pytest

@pytest.mark.parametrize(
    "test_string",
    [
        "IPublishedFileService/QueryFiles page [40/100]",
        "IPublishedFileService/GetDetails chunk [40/100]",
    ]
)
def test_dbbuilder_progress_regex(test_string: str) -> None:
    """
    Verify that the runner panel lines for IPublishedFileService can be parsed
    by a regular expression. The pattern should match:
      - A service name: 'IPublishedFileService/(QueryFiles|GetDetails)'
      - A label: 'page' or 'chunk'
      - A bracketed fraction like '[40/100]'

    This ensures lines of the form:
      "IPublishedFileService/<Method> <Label> [<Current>/<Total>]"
    can be properly recognized and captured.
    """

    pattern = re.compile(
        r"^IPublishedFileService/(QueryFiles|GetDetails)\s+(page|chunk)\s+\[(\d+)/(\d+)\]$"
    )

    match = pattern.search(test_string)
    assert match, f"Regex did not match the expected format in: '{test_string}'"

    # Optionally, confirm the expected groups
    # match.group(1) => 'QueryFiles' or 'GetDetails'
    # match.group(2) => 'page' or 'chunk'
    # match.group(3) => '40'
    # match.group(4) => '100'
    method = match.group(1)
    label = match.group(2)
    current = match.group(3)
    total = match.group(4)

    # Example: You might want to ensure '40' < '100', or that 'page' is not 'chunk'
    # We'll just confirm they're not empty for demonstration:
    assert method in ("QueryFiles", "GetDetails")
    assert label in ("page", "chunk")
    assert current.isdigit() and total.isdigit()
