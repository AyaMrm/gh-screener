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

OPEN_SOURCE_PROJECT_OPTIONS: Final[dict[str, int]] = {
    "senior-dev": 20,
    "github-ceo": 50,
}

OptionValue = TypeVar("OptionValue")


def build_criteria(
    *,
    commits: str | None = None,
    languages: Iterable[str] = (),
    open_source_projects: str | None = None,
) -> ScreeningCriteria:
    commit_values = _get_option(COMMIT_OPTIONS, commits, "commits")
    project_minimum = _get_option(
        OPEN_SOURCE_PROJECT_OPTIONS,
        open_source_projects,
        "open source projects",
    )
    selected_languages = frozenset(
        language.strip() for language in languages if language.strip()
    )

    return ScreeningCriteria(
        minimum_commits_last_12_months=(
            commit_values.get("minimum") if commit_values is not None else None
        ),
        maximum_commits_last_12_months=(
            commit_values.get("maximum") if commit_values is not None else None
        ),
        preferred_languages=selected_languages,
        minimum_open_source_projects=project_minimum,
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
            f"Unknown {criterion_name} option {selected!r}. "
            f"Choose one of: {available}."
        ) from error


__all__ = [
    "COMMIT_OPTIONS",
    "OPEN_SOURCE_PROJECT_OPTIONS",
    "ScreeningCriteria",
    "build_criteria",
]