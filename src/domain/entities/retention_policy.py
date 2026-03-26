"""Retention policy entity — defines rules for automatic image expiry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass
class RetentionPolicy:
    """A rule that determines how long images are kept based on matching tags."""

    name: str
    max_age: timedelta
    apply_to_tags: list[str]

    def matches(self, tags: list[str]) -> bool:
        if not self.apply_to_tags:
            return True  # empty filter matches everything
        return bool(set(self.apply_to_tags) & set(tags))
