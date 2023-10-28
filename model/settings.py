from PySide6.QtCore import QObject, Signal


class Settings(QObject):
    def __init__(self) -> None:
        super().__init__()

        self._check_for_updates_on_startup = False

    @property
    def check_for_updates_on_startup(self) -> bool:
        return self._check_for_updates_on_startup

    @check_for_updates_on_startup.setter
    def check_for_updates_on_startup(self, value: bool) -> None:
        self._check_for_updates_on_startup = value
