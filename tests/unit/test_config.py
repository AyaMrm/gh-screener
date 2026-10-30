from __future__ import annotations

import pytest

from gh_screener.config import get_github_token


def test_get_github_token_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    assert get_github_token() == "test-token"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_get_github_token_requires_a_nonblank_token(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    else:
        monkeypatch.setenv("GITHUB_TOKEN", value)

    with pytest.raises(RuntimeError, match="GITHUB_TOKEN is not set"):
        get_github_token()
