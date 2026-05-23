from re import search


def test_dbbuilder_progress_regex() -> None:
    """Test regular expression for IPublishedFileService/QueryFiles and
    IPublishedFileService/GetDetails output.

    Tests that the regular expression can correctly parse the lines of both
    IPublishedFileService/QueryFiles and IPublishedFileService/GetDetails
    in the DB Builder runner panel output.
    """
    ipublishedfileservice_regex = (
        r"IPublishedFileService/(QueryFiles|GetDetails) (page|chunk) \[(\d+)\/(\d+)\]"
    )
    # Test IPublishedFileService/QueryFiles output
    ipublishedfileservice_queryfiles_test = (
        "IPublishedFileService/QueryFiles page [40/100]"
    )
    ipublishedfileservice_getdetails_test = (
        "IPublishedFileService/GetDetails chunk [40/100]"
    )
    assert search(ipublishedfileservice_regex, ipublishedfileservice_queryfiles_test)
    assert search(ipublishedfileservice_regex, ipublishedfileservice_getdetails_test)
