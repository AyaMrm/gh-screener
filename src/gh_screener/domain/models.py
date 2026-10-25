from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    username: str
    public_repositories: int = 0
    followers: int = 0
    following: int = 0
    repository_languages: frozenset[str] = field(default_factory=frozenset)
    commit_count: int = 0


@dataclass(frozen=True)
class ScreeningCriteria:
    minimum_commits: int | None = None
    preferred_languages: frozenset[str] = field(default_factory=frozenset)
    minimum_public_repositories: int | None = None


@dataclass(frozen=True)
class ScreeningError:
    username: str
    message: str


@dataclass
class ScreeningResult:
    matched_profiles: list[Profile] = field(default_factory=list)
    rejected_profiles: list[Profile] = field(default_factory=list)
    errors: list[ScreeningError] = field(default_factory=list)