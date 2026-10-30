from __future__ import annotations

import pytest

from gh_screener.cli.input_files import InputFileError, read_profile_inputs


def test_reads_nonblank_txt_lines_and_skips_comments(tmp_path) -> None:  # type: ignore[no-untyped-def]
    input_file = tmp_path / "profiles.txt"
    input_file.write_text(
        "# candidates\n\noctocat https://github.com/AyaMrm/\n  # another comment\n",
        encoding="utf-8",
    )

    assert read_profile_inputs(input_file) == [
        "octocat",
        "https://github.com/AyaMrm/",
    ]


@pytest.mark.parametrize(
    ("delimiter", "suffix"),
    [(",", ".csv"), (";", ".CSV")],
)
def test_reads_username_column_from_csv(
    tmp_path, delimiter: str, suffix: str
) -> None:  # type: ignore[no-untyped-def]
    input_file = tmp_path / f"profiles{suffix}"
    input_file.write_text(
        f"username{delimiter}note\noctocat{delimiter}first\n{delimiter}blank\n",
        encoding="utf-8",
    )

    assert read_profile_inputs(input_file) == ["octocat"]


def test_csv_requires_a_username_column(tmp_path) -> None:  # type: ignore[no-untyped-def]
    input_file = tmp_path / "profiles.csv"
    input_file.write_text("login\noctocat\n", encoding="utf-8")

    with pytest.raises(InputFileError, match="'username' column"):
        read_profile_inputs(input_file)


def test_rejects_unsupported_input_file_format(tmp_path) -> None:  # type: ignore[no-untyped-def]
    input_file = tmp_path / "profiles.xlsx"

    with pytest.raises(InputFileError, match=".txt and .csv"):
        read_profile_inputs(input_file)
