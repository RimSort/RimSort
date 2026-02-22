from typing import Any
from uuid import uuid4

DIVIDER_UUID_PREFIX = "__divider__"


def is_divider_uuid(uuid: str) -> bool:
    return uuid.startswith(DIVIDER_UUID_PREFIX)


def generate_divider_uuid() -> str:
    return f"{DIVIDER_UUID_PREFIX}{uuid4().hex}"


class DividerData:
    """Metadata for a divider item in the active mod list."""

    is_divider = True

    def __init__(self, uuid: str, name: str, collapsed: bool = False) -> None:
        self.uuid = uuid
        self.name = name
        self.collapsed = collapsed

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "collapsed": self.collapsed,
        }

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)
