class InvalidModsConfigFormat(Exception):
    """
    Raised when trying to get information from
    an incorrectly formatted ModsConfig.xml
    """
    pass

class InvalidWorkshopModAboutFormat(Exception):
    """
    Raised when trying to get information from
    an incorrectly formatted About.xml (workshop mod)
    """
    pass

class UnexpectedModMetaData(Exception):
    pass
