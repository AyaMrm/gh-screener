from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    username: str
    open_source_projects: int = 0
    followers: int = 0
    following: int = 0
    repository_languages: frozenset[str] = field(default_factory=frozenset)
    commits_last_12_months: int = 0
    has_committed_env_files: bool = False


@dataclass(frozen=True)
class ScreeningCriteria:
    minimum_commits_last_12_months: int | None = None
    maximum_commits_last_12_months: int | None = None
    preferred_languages: frozenset[str] = field(default_factory=frozenset)
    minimum_open_source_projects: int | None = None
    exclude_env_committers: bool = False

    @property
    def is_empty(self) -> bool:
        return (
            self.minimum_commits_last_12_months is None
            and self.maximum_commits_last_12_months is None
            and not self.preferred_languages
            and self.minimum_open_source_projects is None
            and not self.exclude_env_committers
        )


@dataclass(frozen=True)
class ScreeningError:
    username: str
    message: str


@dataclass(frozen=True)
class EnvCommitScanResult:
    found: bool
    complete: bool


@dataclass
class ScreeningResult:
    matched_profiles: list[Profile] = field(default_factory=list)
    rejected_profiles: list[Profile] = field(default_factory=list)
    errors: list[ScreeningError] = field(default_factory=list)



@dataclass(frozen=True)
class Repo:
    name: str
    language: str | None
    is_fork: bool
