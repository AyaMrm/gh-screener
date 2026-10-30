from collections.abc import Iterable
from typing import Final, TypeVar

from .exceptions import UnknownCriteriaOptionError
from .models import ScreeningCriteria

COMMIT_OPTIONS: Final[dict[str, dict[str, int]]] = {
    "low": {"maximum": 49},
    "active": {"minimum": 50},
    "highly-active": {"minimum": 200},
    "very-active": {"minimum": 500},
    "legendary": {"minimum": 2_000},
}

PUBLIC_REPOSITORY_OPTIONS: Final[dict[str, int]] = {
    "senior-dev": 20,
    "github-ceo": 50,
}

OptionValue = TypeVar("OptionValue")


def build_criteria(
    *,
    commit_contributions: str | None = None,
    languages: Iterable[str] = (),
    public_repositories: str | None = None,
    exclude_env_committers: bool = False,
) -> ScreeningCriteria:
    commit_values = _get_option(
        COMMIT_OPTIONS, commit_contributions, "commit contributions"
    )
    repository_minimum = _get_option(
        PUBLIC_REPOSITORY_OPTIONS,
        public_repositories,
        "public repositories",
    )
    selected_languages = frozenset(
        language.strip() for language in languages if language.strip()
    )

    return ScreeningCriteria(
        minimum_commit_contributions_last_12_months=(
            commit_values.get("minimum") if commit_values is not None else None
        ),
        maximum_commit_contributions_last_12_months=(
            commit_values.get("maximum") if commit_values is not None else None
        ),
        preferred_languages=selected_languages,
        minimum_public_repositories=repository_minimum,
        exclude_env_committers=exclude_env_committers,
    )


def _get_option(
    options: dict[str, OptionValue],
    selected: str | None,
    criterion_name: str,
) -> OptionValue | None:
    if selected is None:
        return None
    try:
        return options[selected]
    except KeyError as error:
        available = ", ".join(options)
        raise UnknownCriteriaOptionError(
            f"Unknown {criterion_name} option {selected!r}. Choose one of: {available}."
        ) from error


__all__ = [
    "COMMIT_OPTIONS",
    "PUBLIC_REPOSITORY_OPTIONS",
    "ScreeningCriteria",
    "build_criteria",
]
