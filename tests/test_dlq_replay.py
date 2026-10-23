"""Tests for DLQ replay helper parsing and message reconstruction."""

from __future__ import annotations

import json

import pytest

from src.dlq_replay import ReplayMessage, _build_replay_message, _parse_dlq_payload


class TestParseDlqPayload:
    def test_parse_json_object(self) -> None:
        payload = _parse_dlq_payload(b'{"reason":"retries_exhausted","payload":{"image_id":"abc"}}')
        assert payload["reason"] == "retries_exhausted"

    def test_reject_non_object(self) -> None:
        with pytest.raises(ValueError, match="JSON object"):
            _parse_dlq_payload(b"[]")


class TestBuildReplayMessage:
    def test_build_from_embedded_payload(self) -> None:
        dlq_payload = {
            "original_key": "image-key-1",
            "payload": {"image_id": "5c3c2adb-9d90-472f-bef8-d0f8f1c8f4b9", "attempt": 3},
        }
        replay = _build_replay_message(dlq_payload)

        assert replay == ReplayMessage(
            key="image-key-1",
            value=json.dumps(
                {"image_id": "5c3c2adb-9d90-472f-bef8-d0f8f1c8f4b9", "attempt": 0}
            ).encode(),
        )

    def test_build_from_original_value_fallback(self) -> None:
        dlq_payload = {
            "original_key": "",
            "original_value": '{"image_id":"442f5914-f5ca-4366-a88b-e8e16d697f45","attempt":2}',
        }
        replay = _build_replay_message(dlq_payload)

        assert replay == ReplayMessage(
            key="442f5914-f5ca-4366-a88b-e8e16d697f45",
            value=json.dumps(
                {"image_id": "442f5914-f5ca-4366-a88b-e8e16d697f45", "attempt": 0}
            ).encode(),
        )

    def test_reject_non_replayable_payload(self) -> None:
        with pytest.raises(ValueError, match="missing both"):
            _build_replay_message({"reason": "malformed"})
