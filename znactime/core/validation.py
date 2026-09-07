from __future__ import annotations

import unicodedata


MAX_SPECIAL_DAY_LENGTH = 256


def special_day_text_problem(value: object) -> str | None:
    """Return a user-facing problem for text stored in ``special_day``."""
    if not isinstance(value, str):
        return "Special day text must be text."
    if not value.strip():
        return "Special day text cannot be empty."
    if len(value) > MAX_SPECIAL_DAY_LENGTH:
        return (
            "Special day text cannot exceed "
            f"{MAX_SPECIAL_DAY_LENGTH} characters."
        )
    if any(unicodedata.category(character) == "Cc" for character in value):
        return "Special day text cannot contain control characters."
    return None
