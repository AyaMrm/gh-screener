from collections.abc import Iterable
from typing import Protocol

from .models import Profile


class ProfileRepository(Protocol):
    def get_profile(self, username: str) -> Profile:
        """Load and normalize one GitHub profile."""

    def get_profiles(self, usernames: Iterable[str]) -> list[Profile]:
        """Load and normalize multiple GitHub profiles."""