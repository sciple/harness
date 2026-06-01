"""Tests for session.py — save/load/list, atomic writes, _msg_to_dict."""

import json
import os
import re
import pytest
from unittest.mock import MagicMock


@pytest.fixture()
def session_dir(tmp_path, monkeypatch):
    """Point SESSIONS_DIR at a fresh temp directory."""
    import session as sess
    import config
    sdir = tmp_path / "sessions"
    sdir.mkdir()
    monkeypatch.setattr(config, "SESSIONS_DIR", str(sdir))
    monkeypatch.setattr(sess, "SESSIONS_DIR", str(sdir))  # module-level copy
    return sdir


# ---------------------------------------------------------------------------
# new_id
# ---------------------------------------------------------------------------

def test_new_id_format():
    import session
    sid = session.new_id()
    assert re.match(r"^\d{8}T\d{6}$", sid), f"Unexpected format: {sid}"


def test_new_id_unique():
    import session, time
    id1 = session.new_id()
    time.sleep(1.1)
    id2 = session.new_id()
    assert id1 != id2


# ---------------------------------------------------------------------------
# save / load roundtrip
# ---------------------------------------------------------------------------

def test_save_and_load_roundtrip(session_dir):
    import session
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    state = {"session_id": "test001", "messages": messages}
    session.save(state)
    loaded = session.load("test001")
    assert loaded is not None
    assert len(loaded) == 3
    assert loaded[1]["content"] == "Hello"


def test_load_missing_session(session_dir):
    import session
    result = session.load("no_such_session")
    assert result is None


def test_load_skips_corrupt_lines(session_dir):
    import session
    path = session_dir / "corrupt.jsonl"
    path.write_text(
        '{"role": "user", "content": "good line"}\n'
        'NOT VALID JSON\n'
        '{"role": "assistant", "content": "also good"}\n',
        encoding="utf-8",
    )
    loaded = session.load("corrupt")
    assert loaded is not None
    assert len(loaded) == 2


def test_save_silent_on_garbage_messages(session_dir):
    """save() must not raise even with un-serialisable messages."""
    import session

    class Unserializable:
        pass

    state = {"session_id": "bad", "messages": [Unserializable()]}
    # Should not raise
    session.save(state)


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

def test_list_sessions_sorted(session_dir):
    import session
    for sid in ["20260101T000000", "20260103T000000", "20260102T000000"]:
        (session_dir / f"{sid}.jsonl").write_text(
            '{"role": "user", "content": "x"}\n', encoding="utf-8"
        )
    results = session.list_sessions()
    ids = [r[0] for r in results]
    assert ids == sorted(ids, reverse=True)


def test_list_sessions_empty_dir(session_dir):
    import session
    results = session.list_sessions()
    assert results == []


def test_list_sessions_message_count(session_dir):
    import session
    (session_dir / "cnt.jsonl").write_text(
        '{"role": "user", "content": "a"}\n'
        '{"role": "assistant", "content": "b"}\n',
        encoding="utf-8",
    )
    results = session.list_sessions()
    assert results[0][1] == 2


# ---------------------------------------------------------------------------
# Atomic write — no .tmp files left on disk
# ---------------------------------------------------------------------------

def test_atomic_write_no_tmp_left(session_dir):
    import session
    state = {"session_id": "atomic", "messages": [{"role": "user", "content": "x"}]}
    session.save(state)
    tmp_files = list(session_dir.glob("*.tmp"))
    assert len(tmp_files) == 0


# ---------------------------------------------------------------------------
# _msg_to_dict
# ---------------------------------------------------------------------------

def test_msg_to_dict_plain_dict():
    from session import _msg_to_dict
    msg = {"role": "user", "content": "hello"}
    assert _msg_to_dict(msg) is msg  # same object returned


def test_msg_to_dict_sdk_object_with_model_dump():
    from session import _msg_to_dict
    obj = MagicMock()
    obj.model_dump.return_value = {"role": "assistant", "content": "hi"}
    # Make isinstance(obj, dict) return False
    obj.__class__ = object.__class__
    result = _msg_to_dict(obj)
    assert result["role"] == "assistant"


def test_msg_to_dict_fallback_reconstruction():
    from session import _msg_to_dict

    class FakeMsg:
        role = "assistant"
        content = "response"
        tool_calls = None
        tool_call_id = None
        # No model_dump method

    result = _msg_to_dict(FakeMsg())
    assert result["role"] == "assistant"
    assert result["content"] == "response"
