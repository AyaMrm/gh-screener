from gh_screener.domain.models import Profile, ScreeningCriteria


def filter_projects(
    profile: Profile,
    criteria: ScreeningCriteria,
) -> bool:
    minimum = criteria.minimum_open_source_projects
    if minimum is None:
        return True

    projects = profile.open_source_projects
    if projects is None:
        raise ValueError(
            f"Missing open source projects data for: {profile.username}"
        )

    return projects >= minimum
