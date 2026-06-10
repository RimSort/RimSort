from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class FilterState:
    """
    Immutable snapshot of all active filters in a mod list's filter panel.

    :param sources: Set of enabled mod sources (workshop, local, expansion, steamcmd, git_repo)
    :param mod_type: Mod type filter ("all", "csharp", or "xml")
    :param tags: Set of selected tags to filter by
    :param include_no_tags: Whether to include mods with no tags assigned
    """

    sources: set[str] = field(default_factory=lambda: set(FilterState.ALL_SOURCES))
    mod_type: str = "all"
    tags: set[str] = field(default_factory=set)
    include_no_tags: bool = False

    ALL_SOURCES: ClassVar[frozenset[str]] = frozenset(
        {"workshop", "local", "expansion", "steamcmd", "git_repo"}
    )

    @classmethod
    def default(cls) -> FilterState:
        """
        Create a FilterState with no active filters.

        :return: FilterState with all sources enabled and no type/tag filters
        """
        return cls()

    def has_active_filters(self) -> bool:
        """
        Check if any filters are currently active.

        :return: True if any category is filtered (not default state)
        """
        if self.sources != self.ALL_SOURCES:
            return True
        if self.mod_type != "all":
            return True
        if self.tags or self.include_no_tags:
            return True
        return False

    def active_category_count(self) -> int:
        """
        Count how many filter categories have active (non-default) filters.

        :return: Number of active filter categories (0-3)
        """
        count = 0
        if self.sources != self.ALL_SOURCES:
            count += 1
        if self.mod_type != "all":
            count += 1
        if self.tags or self.include_no_tags:
            count += 1
        return count
