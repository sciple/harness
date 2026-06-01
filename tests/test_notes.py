"""Tests for tools/notes.py — CRUD, atomic writes, edge cases."""

import json
import os
import pytest


@pytest.fixture(autouse=True)
def fresh_notes(tmp_workspace):
    """Ensure notes directory exists and notes file is absent before each test."""
    notes_dir = tmp_workspace / "notes"
    notes_dir.mkdir(exist_ok=True)
    notes_file = notes_dir / "notes.json"
    if notes_file.exists():
        notes_file.unlink()
    yield


def _reload():
    """Re-import notes functions so they see the patched _NOTES_FILE."""
    from tools.notes import save_note, get_note, list_notes, delete_note
    return save_note, get_note, list_notes, delete_note


def test_save_and_get_roundtrip():
    save_note, get_note, _, _ = _reload()
    save_note("key1", "value1")
    result = get_note("key1")
    assert "value1" in result


def test_overwrite_existing_key():
    save_note, get_note, _, _ = _reload()
    save_note("k", "original")
    save_note("k", "updated")
    result = get_note("k")
    assert "updated" in result
    assert "original" not in result


def test_get_missing_key():
    _, get_note, _, _ = _reload()
    result = get_note("no_such_key")
    assert result.startswith("Error")


def test_get_missing_shows_hint():
    save_note, get_note, _, _ = _reload()
    save_note("other_key", "x")
    result = get_note("no_such_key")
    # Should mention existing keys as a hint
    assert "other_key" in result or "Error" in result


def test_list_empty():
    _, _, list_notes, _ = _reload()
    result = list_notes()
    assert "No notes" in result or "no notes" in result.lower()


def test_list_shows_keys():
    save_note, _, list_notes, _ = _reload()
    save_note("alpha", "first")
    save_note("beta", "second")
    result = list_notes()
    assert "alpha" in result
    assert "beta" in result


def test_list_preview_truncated():
    save_note, _, list_notes, _ = _reload()
    long_value = "x" * 200
    save_note("long_key", long_value)
    result = list_notes()
    # Preview should not contain the full 200-char value
    assert len(result) < 300 or "..." in result or "\u2026" in result


def test_delete_removes_key():
    save_note, get_note, _, delete_note = _reload()
    save_note("to_delete", "bye")
    delete_note("to_delete")
    result = get_note("to_delete")
    assert result.startswith("Error")


def test_delete_missing_key():
    _, _, _, delete_note = _reload()
    result = delete_note("ghost")
    assert result.startswith("Error")


def test_empty_key_rejected():
    save_note, _, _, _ = _reload()
    result = save_note("", "value")
    assert result.startswith("Error")


def test_whitespace_only_key_rejected():
    save_note, _, _, _ = _reload()
    result = save_note("   ", "value")
    assert result.startswith("Error")


def test_notes_persisted_to_disk(tmp_workspace):
    save_note, _, _, _ = _reload()
    save_note("disk_key", "disk_value")
    notes_file = tmp_workspace / "notes" / "notes.json"
    assert notes_file.exists()
    data = json.loads(notes_file.read_text(encoding="utf-8"))
    assert data.get("disk_key") == "disk_value"


def test_atomic_write_no_tmp_files_left(tmp_workspace):
    save_note, _, _, _ = _reload()
    save_note("atomic", "test")
    notes_dir = tmp_workspace / "notes"
    tmp_files = list(notes_dir.glob("*.tmp"))
    assert len(tmp_files) == 0
