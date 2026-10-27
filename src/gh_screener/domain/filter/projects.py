from gh_screener.domain.models import Profile,ScreeningCriteria

def filter_projects(
        profile:Profile,
        criteria:ScreeningCriteria,
        
)->bool:
    open_source_projects=profile.open_source_projects

    if  open_source_projects is None:
        raise ValueError(
            f"Missing open source projects data for: {profile.username}"
        )

    minimum_open_source_projects=criteria.minimum_open_source_projects

    if minimum_open_source_projects is not None and open_source_projects < minimum_open_source_projects:
        return False
   
    return True
    
        