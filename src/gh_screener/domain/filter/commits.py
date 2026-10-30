from gh_screener.domain.models import Profile, ScreeningCriteria


def filter_commits(
    profile: Profile,
    criteria: ScreeningCriteria,
) -> bool:
    commits = profile.commit_contributions_last_12_months

    if commits is None:
        raise ValueError(
            f"Missing commit contribution data for {profile.username}"
        )

    minimum_commits = criteria.minimum_commit_contributions_last_12_months
    maximum_commits = criteria.maximum_commit_contributions_last_12_months

    if minimum_commits is not None and commits < minimum_commits:
        return False

    return not (maximum_commits is not None and commits > maximum_commits)
