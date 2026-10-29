from collections.abc import Iterable
from typing import Protocol

from .models import EnvCommitScanResult, Profile


class ProfileRepository(Protocol):
    def get_profile(self, username: str) -> Profile:
        """Load and normalize one GitHub profile."""

    def get_profiles(self, usernames: Iterable[str]) -> list[Profile]:
        """Load and normalize multiple GitHub profiles."""

    def scan_env_commits(self, username: str) -> EnvCommitScanResult:
        """Check a bounded sample of commits attributed to a user for .env files."""
