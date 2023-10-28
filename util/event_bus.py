from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    """
    Singleton event bus to manage application-wide signals using Qt's signal-slot mechanism.

    The `EventBus` class is designed to facilitate decoupled communication between different parts
    of an application. It provides application-scope signals that can be emitted from one part of
    an application and connected slots in another, allowing for loose coupling between components.

    Examples:
        >>> event_bus = EventBus()
        >>> event_bus.settings_have_changed.connect(some_slot_function)
        >>> event_bus.settings_have_changed.emit()

    Notes:
        Since this is a singleton class, multiple instantiations will return the same object.
    """

    _instance = None

    # Application-scope signals
    settings_have_changed = Signal()

    def __new__(cls) -> "EventBus":
        """
        Create a new instance or return the existing singleton instance of the `EventBus` class.

        Returns:
            EventBus: The singleton instance of the `EventBus` class.
        """
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the `EventBus` instance.
        """
        if hasattr(self, "_is_initialized") and self._is_initialized:
            return
        super().__init__()
        self._is_initialized: bool = True
