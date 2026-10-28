from abc import ABC, abstractmethod
from collections.abc import Collection

from .models import Profile


class Filter(ABC):
    """A single screening rule and the profile data it needs."""

    @property
    @abstractmethod
    def requires(self) -> frozenset[str]:
        """Return the profile fields required to evaluate this filter."""

    @abstractmethod
    def matches(self, profile: Profile) -> bool:
        """Return whether the profile satisfies this filter."""


def matches_all(profile: Profile, filters: Collection[Filter]) -> bool:
    return all(current_filter.matches(profile) for current_filter in filters)
