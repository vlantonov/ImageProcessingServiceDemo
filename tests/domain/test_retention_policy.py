"""Tests for the RetentionPolicy domain entity."""

from __future__ import annotations

from datetime import timedelta

from src.domain.entities.retention_policy import RetentionPolicy


class TestRetentionPolicy:
    def test_matches_empty_filter(self):
        policy = RetentionPolicy(name="catch-all", max_age=timedelta(days=30), apply_to_tags=[])
        assert policy.matches(["anything"]) is True
        assert policy.matches([]) is True

    def test_matches_specific_tag(self):
        policy = RetentionPolicy(
            name="temp", max_age=timedelta(hours=24), apply_to_tags=["temporary"]
        )
        assert policy.matches(["temporary", "other"]) is True
        assert policy.matches(["permanent"]) is False

    def test_matches_overlap(self):
        policy = RetentionPolicy(
            name="dev", max_age=timedelta(days=7), apply_to_tags=["dev", "staging"]
        )
        assert policy.matches(["staging"]) is True
        assert policy.matches(["production"]) is False
