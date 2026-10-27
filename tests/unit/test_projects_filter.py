import pytest
from gh_screener.domain.filter.projects import filter_projects
from gh_screener.domain.models import Profile
from gh_screener.domain.criteria import build_criteria


@pytest.mark.parametrize(
        ("level","count","expected"),
        [
            ("senior-dev", 0, False),
            ("senior-dev", 19, False),
            ("senior-dev",20,True),
            ("senior-dev",3,False),
            ("senior-dev", 30, True),
            ("github-ceo",120,True),
            ("github-ceo",30,False),
            ("senior-dev",5,False),
            ("github-ceo", 49, False),
            ("github-ceo",50,True),
        ]
)
def test_filter_projects(level,count,expected):
    profile=Profile(username="test_user",open_source_projects=count)
    criteria=build_criteria(open_source_projects=level)
    assert filter_projects(profile,criteria) is expected

def test_no_level_selected_always_passes():
    profile=Profile(username="test_user",open_source_projects=0)
    assert filter_projects(profile,build_criteria()) is True


def test_missing_projects_data_raises_error():
    profile=Profile(username="test_user",open_source_projects=None)
    criteria=build_criteria(open_source_projects="senior-dev")
    with pytest.raises(ValueError,match="Missing open source projects data"):
        filter_projects(profile,criteria)