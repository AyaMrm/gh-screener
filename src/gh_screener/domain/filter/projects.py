from gh_screener.domain.models import Profile, ScreeningCriteria


def filter_projects(
    profile: Profile,
    criteria: ScreeningCriteria,
) -> bool:
    minimum = criteria.minimum_public_repositories
    if minimum is None:
        return True

    repositories = profile.public_repositories
    if repositories is None:
        raise ValueError(f"Missing public repository data for: {profile.username}")

    return repositories >= minimum
