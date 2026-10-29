from collections.abc import Callable

from gh_screener.domain.filter.commits import filter_commits
from gh_screener.domain.filter.projects import filter_projects
from gh_screener.domain.filter.secrets import filter_secrets
from gh_screener.domain.filter.stack import filter_stack
from gh_screener.domain.filters import Filter
from gh_screener.domain.models import Profile, ScreeningCriteria


class CriteriaFilter(Filter):
    def __init__(
        self,
        criteria: ScreeningCriteria,
        evaluator: Callable[[Profile, ScreeningCriteria], bool],
        required_fields: frozenset[str],
    ) -> None:
        self.criteria = criteria
        self.evaluator = evaluator
        self._required_fields = required_fields

    @property
    def requires(self) -> frozenset[str]:
        return self._required_fields

    def matches(self, profile: Profile) -> bool:
        return self.evaluator(profile, self.criteria)


def build_filters(criteria: ScreeningCriteria) -> list[Filter]:
    """Build the active profile filters from the selected criteria."""
    filters: list[Filter] = []

    if criteria.exclude_env_committers:
        filters.append(
            CriteriaFilter(
                criteria,
                filter_secrets,
                frozenset({"has_committed_env_files"}),
            )
        )

    if (
        criteria.maximum_commits_last_12_months is not None
        or criteria.minimum_commits_last_12_months is not None
    ):
        filters.append(
            CriteriaFilter(
                criteria,
                filter_commits,
                frozenset({"commits_last_12_months"}),
            )
        )

    if criteria.minimum_open_source_projects is not None:
        filters.append(
            CriteriaFilter(
                criteria,
                filter_projects,
                frozenset({"open_source_projects"}),
            )
        )

    if criteria.preferred_languages:
        filters.append(
            CriteriaFilter(
                criteria,
                filter_stack,
                frozenset({"repository_languages"}),
            )
        )

    return filters
