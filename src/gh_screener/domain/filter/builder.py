from gh_screener.domain.models import Profile, ScreeningCriteria,Repo
from gh_screener.domain.filters import Filter
from gh_screener.domain.filter.projects import filter_projects
from gh_screener.domain.filter.commits import filter_commits
from gh_screener.domain.filter.stack import filter_stack
from collections.abc import Callable
from collections.abc import Iterable

class CriteriaFilter(Filter):
    def __init__(
            self,
            criteria: ScreeningCriteria,
            evaluator: Callable[[Profile, ScreeningCriteria], bool],
            required_fields: frozenset[str],
    )-> None:
        self.criteria = criteria
        self.evaluator = evaluator
        self._required_fields = required_fields


    @property
    def requires(self) -> frozenset[str]:
        return self._required_fields

    def matches(self, profile: Profile) -> bool:
        return self.evaluator(profile, self.criteria)
    
class StackFilter(Filter):
    def __init__(
                self,
                criteria: ScreeningCriteria,
                repos:Iterable[Repo]
        )-> None:
            self.criteria = criteria
            self.repos=tuple(repos)

    @property
    def requires(self) -> frozenset[str]:
        return frozenset({"repos"})
    def matches(self, profile:Profile)->bool:
        return filter_stack(self.repos,profile,self.criteria)
    
def build_filters(criteria: ScreeningCriteria,repos:Iterable[Repo]=())-> list[Filter]:
    filters:list[Filter]=[]

    if (
        criteria.maximum_commits_last_12_months is  not None
        or criteria.minimum_commits_last_12_months is not None

    ):
        filters.append(
            CriteriaFilter(
                criteria,
                filter_commits,
                frozenset({"commits_last_12_months"}),
            )
        )
    if(criteria.minimum_open_source_projects is not None):
        filters.append(
            CriteriaFilter(
                criteria,
                filter_projects,
                frozenset({"open_source_projects"}),
            )
        )
    if criteria.preferred_languages:
        filters.append(StackFilter(criteria,repos))

    return filters

