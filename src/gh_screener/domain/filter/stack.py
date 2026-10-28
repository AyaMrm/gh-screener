
from collections.abc import Iterable

from gh_screener.domain.models import Profile, Repo, ScreeningCriteria


def filter_stack(
    repos: Iterable[Repo],
    profile: Profile,
    criteria: ScreeningCriteria,
) -> bool:
    repo_languages = set()

    #collect non forked languages
    for repo in repos:
        if repo.is_fork:
            continue

        if repo.language:
            repo_languages.add(repo.language.lower())

    #check the lang
    for language in criteria.preferred_languages:
        if language.lower() not in repo_languages:
            return False

    return True
