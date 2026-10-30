from __future__ import annotations

import csv
from pathlib import Path
from typing import TextIO


class InputFileError(ValueError):
    """Raised when an input file is unsupported or cannot be parsed."""


def read_profile_inputs(path: Path) -> list[str]:
    suffix = path.suffix.casefold()
    if suffix not in {".txt", ".csv"}:
        raise InputFileError("Supported input file formats are .txt and .csv.")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as input_stream:
            if suffix == ".txt":
                usernames: list[str] = []
                for raw_line in input_stream:
                    line = raw_line.strip()
                    if line and not line.startswith("#"):
                        usernames.extend(line.split())
                return usernames
            return _read_csv(input_stream)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise InputFileError(f"Could not read {path}: {exc}") from exc


def _read_csv(input_stream: TextIO) -> list[str]:
    sample = input_stream.read(4096)
    input_stream.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(input_stream, dialect=dialect)
    if not reader.fieldnames:
        raise InputFileError("The CSV file is empty or has no header row.")

    username_column = next(
        (field for field in reader.fieldnames if field.strip().casefold() == "username"),
        None,
    )
    if username_column is None:
        raise InputFileError("The CSV file must contain a 'username' column.")

    values: list[str] = []
    for row in reader:
        value = row.get(username_column)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values
