"""Tests for filename sanitization."""

from __future__ import annotations

import pytest

from src.presentation.sanitize import sanitize_filename


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("photo.png", "photo.png"),
        ("my photo.png", "my_photo.png"),
        ("../../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\cmd.exe", "cmd.exe"),
        ("/absolute/path/to/image.jpg", "image.jpg"),
        ("normal_file-name.jpeg", "normal_file-name.jpeg"),
    ],
)
def test_basic_cases(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_null_bytes_stripped() -> None:
    assert "\x00" not in sanitize_filename("photo\x00.png")


def test_hidden_files_stripped() -> None:
    result = sanitize_filename(".htaccess")
    assert not result.startswith(".")


def test_empty_string_falls_back() -> None:
    assert sanitize_filename("") == "unnamed"


def test_only_dots_falls_back() -> None:
    assert sanitize_filename("...") == "unnamed"


def test_only_path_separators_falls_back() -> None:
    assert sanitize_filename("../../../") == "unnamed"


def test_unicode_normalized() -> None:
    # Fullwidth A -> A, non-ascii stripped
    result = sanitize_filename("\uff21\uff22\uff23.png")
    assert result == "ABC.png"


def test_consecutive_dots_collapsed() -> None:
    result = sanitize_filename("file..name...png")
    assert ".." not in result


def test_consecutive_underscores_collapsed() -> None:
    result = sanitize_filename("file___name.png")
    assert "___" not in result
    assert "__" not in result


def test_long_filename_truncated() -> None:
    long_name = "a" * 300 + ".png"
    result = sanitize_filename(long_name)
    assert len(result) <= 255


def test_control_characters_replaced() -> None:
    result = sanitize_filename("file\x01\x02name.png")
    assert "\x01" not in result
    assert "\x02" not in result


def test_windows_path_traversal() -> None:
    result = sanitize_filename("C:\\Users\\evil\\..\\..\\secret.png")
    assert result == "secret.png"


def test_mixed_traversal() -> None:
    result = sanitize_filename("../../../../tmp/../../root/image.jpg")
    assert result == "image.jpg"
    assert "/" not in result
    assert ".." not in result
