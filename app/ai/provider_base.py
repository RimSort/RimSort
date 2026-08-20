from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return assistant text for the given chat messages."""
