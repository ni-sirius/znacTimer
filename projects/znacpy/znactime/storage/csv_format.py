from __future__ import annotations


CSV_VERSION_MARKER = "#znacTime-csv"
CSV_SCHEMA_VERSION = 3

_FORMULA_PREFIXES = frozenset(("=", "+", "-", "@", "\t", "\r", "\n"))
_SPREADSHEET_ESCAPE = "'"


def spreadsheet_safe_text(value: object) -> str:
    """Encode free text so spreadsheet programs do not evaluate it.

    CSV schema v3 reserves a leading apostrophe as an escape marker. Existing
    apostrophes are doubled, making the transform reversible during import.
    Leading whitespace is escaped as well because spreadsheet applications may
    ignore it before interpreting a formula marker.
    """
    text = str(value)
    first = text[:1]
    if (
        first == _SPREADSHEET_ESCAPE
        or first in _FORMULA_PREFIXES
        or (first and first.isspace())
    ):
        return _SPREADSHEET_ESCAPE + text
    return text


def decode_spreadsheet_safe_text(value: object, schema_version: int | None) -> str:
    """Decode the v3 escape without changing legacy v1/v2 values."""
    text = str(value)
    if schema_version == CSV_SCHEMA_VERSION and text.startswith(
        _SPREADSHEET_ESCAPE
    ):
        return text[1:]
    return text
