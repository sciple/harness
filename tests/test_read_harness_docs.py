"""Tests for tools/read_harness_docs.py — file reading and missing-file handling."""

import os
from unittest.mock import patch

from tools.read_harness_docs import read_harness_docs


def test_returns_string():
    result = read_harness_docs()
    assert isinstance(result, str)


def test_contains_expected_sections():
    result = read_harness_docs()
    assert "## Tools" in result
    assert "## Commands" in result
    assert "## Skills" in result


def test_not_empty():
    result = read_harness_docs()
    assert len(result) > 100


def test_missing_file_returns_error(tmp_path):
    fake_path = str(tmp_path / "nonexistent.md")
    with patch("tools.read_harness_docs.os.path.realpath", return_value=fake_path):
        result = read_harness_docs()
    assert result.startswith("Error")
    assert "not found" in result.lower()
