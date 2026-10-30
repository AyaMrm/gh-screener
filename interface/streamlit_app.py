"""Streamlit interface for gh-screener.

Run from inside the interface folder (so the dark theme in .streamlit/ loads):

    pip install "streamlit>=1.40"
    cd interface
    streamlit run streamlit_app.py

Layout: one bar (Profiles | AI toggle + input), one split-style button
(Screen profiles / Upload file), filters stacked underneath, results below.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Make the project root importable (gh_screener lives one level above interface/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from gh_screener.application.screen_profiles import screen_profiles
from gh_screener.cli.parser import parse_username
from gh_screener.domain.criteria import (
    COMMIT_OPTIONS,
    PUBLIC_REPOSITORY_OPTIONS,
    build_criteria,
)
from gh_screener.domain.exceptions import (
    InvalidProfileError,
    UnknownCriteriaOptionError,
)
from gh_screener.domain.models import ScreeningError

LANGUAGES = ["Python", "Go", "Rust", "TypeScript", "JavaScript", "Java", "C++"]
COMMIT_LIST = list(COMMIT_OPTIONS)
REPO_LIST = list(PUBLIC_REPOSITORY_OPTIONS)

st.set_page_config(page_title="GH Screener", page_icon=None, layout="centered")

st.markdown(
    """
    <style>
      header[data-testid="stHeader"] {display: none;}
      footer {display: none;}
      .block-container {padding-top: 3rem; max-width: 960px;}
      [data-testid="stForm"] {border: 0; padding: 0;}
      h1 {font-size: 1.4rem !important; font-weight: 600 !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
defaults = {
    "pool": [],  # every profile string ever added (options of the chip list)
    "users": [],  # currently selected profiles
    "commit": None,
    "langs": [],
    "repos": None,
    "env": False,
    "note": "",
    "result": None,
    "run_requested": False,
    "processed_upload": None,
}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def add_profiles(text: str) -> int:
    """Add whitespace/comma separated usernames or URLs; return how many are new."""
    pool = list(st.session_state.pool)
    users = list(st.session_state.users)
    added = 0
    for token in filter(None, re.split(r"[\s,;]+", text or "")):
        if token not in pool:
            pool.append(token)
            added += 1
        if token not in users:
            users.append(token)
    # Assign new lists: Streamlit only registers a change on assignment,
    # not when a list is modified in place.
    st.session_state.pool = pool
    st.session_state.users = users
    return added


def _best_match(options: list[str], text: str) -> str | None:
    """Pick the option the text refers to (full name wins over its first word)."""
    best, best_score = None, 0
    for option in options:
        name = option.lower()
        first = name.split("-")[0]
        if name in text:
            score = 100 + len(name)
        elif len(first) >= 3 and first in text:
            score = len(first)
        else:
            continue
        if score > best_score:
            best, best_score = option, score
    return best


def apply_ai(text: str) -> None:
    """Turn a plain-language description into filter values (keyword based)."""
    t = (text or "").lower()
    langs = []
    for lang in LANGUAGES:
        key = lang.lower()
        if key == "go":
            hit = re.search(r"\bgo(lang)?\b", t)
        elif key == "c++":
            hit = "c++" in t
        else:
            hit = key in t
        if hit:
            langs.append(lang)
    commit = _best_match(COMMIT_LIST, t)
    repos = _best_match(REPO_LIST, t)
    env = bool(re.search(r"\.env|env file|secrets?", t))

    found = []
    if commit:
        found.append(f"commits: {commit}")
    if langs:
        found.append("languages: " + ", ".join(langs))
    if repos:
        found.append(f"repos: {repos}")
    if env:
        found.append("exclude .env committers")

    if not found:
        st.session_state.note = "No filters recognised."
        return
    st.session_state.commit = commit
    st.session_state.langs = langs
    st.session_state.repos = repos
    st.session_state.env = env
    st.session_state.note = "Filters set: " + " · ".join(found)


def reset_filters() -> None:
    st.session_state.commit = None
    st.session_state.langs = []
    st.session_state.repos = None
    st.session_state.env = False
    st.session_state.note = ""


def request_run() -> None:
    st.session_state.run_requested = True


def make_repository():
    """Build the GitHub adapter only when a screening is requested."""
    from gh_screener.config import get_github_token
    from gh_screener.infra.github_client import GitHubClient

    return GitHubClient(get_github_token())


def run_screening() -> None:
    selected = list(st.session_state.users)
    usernames: list[str] = []
    input_errors: list[ScreeningError] = []
    for raw in selected:
        try:
            usernames.append(parse_username(raw))
        except InvalidProfileError as exc:
            input_errors.append(ScreeningError(username=raw, message=str(exc)))

    if not usernames:
        st.session_state.result = None
        st.error("Add at least one valid profile first.")
        return

    try:
        criteria = build_criteria(
            commit_contributions=st.session_state.commit,
            languages=list(st.session_state.langs),
            public_repositories=st.session_state.repos,
            exclude_env_committers=bool(st.session_state.env),
        )
    except UnknownCriteriaOptionError as exc:
        st.error(f"Error: {exc}")
        return

    try:
        repository = make_repository()
    except RuntimeError as exc:
        st.error(f"Configuration error: {exc}")
        return

    with st.spinner(f"Screening {len(usernames)} profile(s)..."):
        try:
            result = screen_profiles(usernames, criteria, repository)
        finally:
            repository.close()
    result.errors[:0] = input_errors
    st.session_state.result = result


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.title("GH Screener")

# --------------------------------------------------------------------------- #
# Bar: mode toggle + input + split button (Screen / Upload)
# --------------------------------------------------------------------------- #
c_mode, c_bar, c_go = st.columns([1.5, 5, 1.7], vertical_alignment="center")

with c_mode:
    st.segmented_control(
        "Input mode",
        ["Profiles", "AI"],
        default="Profiles",
        key="mode",
        label_visibility="collapsed",
    )
mode = st.session_state.get("mode") or "Profiles"
is_ai = mode == "AI"

with c_bar:
    with st.form("bar", clear_on_submit=True):
        f_input, f_submit = st.columns([5, 1.2], vertical_alignment="center")
        text = f_input.text_input(
            "Search",
            placeholder=(
                "Describe who you need, e.g. active senior Python dev"
                if is_ai
                else "Usernames or GitHub URLs"
            ),
            label_visibility="collapsed",
        )
        submitted = f_submit.form_submit_button(
            "Apply" if is_ai else "Add", use_container_width=True
        )
    if submitted and text.strip():
        if is_ai:
            apply_ai(text)
        else:
            add_profiles(text)

with c_go, st.popover("Screen profiles ▾", use_container_width=True):
    st.button(
        "Screen profiles",
        type="primary",
        on_click=request_run,
        use_container_width=True,
    )
    st.divider()
    st.file_uploader(
        "Upload file (.txt or .csv, one profile per line)",
        type=["txt", "csv"],
        key="upload",
    )

# File upload: add its entries once per uploaded file.
upload = st.session_state.get("upload")
if upload is not None and st.session_state.processed_upload != upload.file_id:
    added = add_profiles(upload.getvalue().decode("utf-8", errors="ignore"))
    st.session_state.processed_upload = upload.file_id
    st.session_state.note = f"{upload.name}: {added} added"
elif upload is None:
    st.session_state.processed_upload = None

# --------------------------------------------------------------------------- #
# Filters (stacked)
# --------------------------------------------------------------------------- #
st.segmented_control(
    "Commits (last 365 days)", COMMIT_LIST, key="commit", selection_mode="single"
)
st.pills("Languages", LANGUAGES, key="langs", selection_mode="multi")
st.segmented_control(
    "Public repositories", REPO_LIST, key="repos", selection_mode="single"
)
st.checkbox("Exclude .env committers", key="env")
st.button("Reset filters", on_click=reset_filters, type="tertiary")

# --------------------------------------------------------------------------- #
# Added profiles (remove with the x) + notes
# --------------------------------------------------------------------------- #
st.multiselect(
    "Profiles",
    options=st.session_state.pool,
    key="users",
    placeholder="No profiles added",
    label_visibility="collapsed",
)
if st.session_state.note:
    st.caption(st.session_state.note)

# --------------------------------------------------------------------------- #
# Run + results
# --------------------------------------------------------------------------- #
if st.session_state.run_requested:
    st.session_state.run_requested = False
    run_screening()

result = st.session_state.result
if result is not None:
    st.divider()
    col_ok, col_no, col_err = st.columns(3)
    with col_ok:
        st.markdown(f"**Matched ({len(result.matched_profiles)})**")
        for profile in result.matched_profiles:
            st.write(profile.username)
        if not result.matched_profiles:
            st.caption("(none)")
    with col_no:
        st.markdown(f"**Rejected ({len(result.rejected_profiles)})**")
        for profile in result.rejected_profiles:
            st.write(profile.username)
        if not result.rejected_profiles:
            st.caption("(none)")
    with col_err:
        st.markdown(f"**Errors ({len(result.errors)})**")
        for error in result.errors:
            st.write(error.username)
            st.caption(error.message)
        if not result.errors:
            st.caption("(none)")