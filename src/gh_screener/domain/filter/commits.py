from gh_screener.domain.models import Profile, ScreeningCriteria


def filter_commits(
        profile: Profile,
        criteria: ScreeningCriteria,
)-> bool:
    commits = profile.commits_last_12_months
    #no commits
    if commits is None:
        raise ValueError(
            f"Missing commits data for {profile.username}"
        )

    minimum_commits = criteria.minimum_commits_last_12_months
    maximum_commits = criteria.maximum_commits_last_12_months


    if minimum_commits is not None and commits < minimum_commits:
        return False

    return not (maximum_commits is not None and commits > maximum_commits)