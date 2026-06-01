"""Tests for tools/fetch_url.py — URL fetching, HTML stripping, truncation, error handling."""

import urllib.error
from unittest.mock import MagicMock, patch
from io import BytesIO

from tools.fetch_url import fetch_url


def _mock_response(body: str, charset: str = "utf-8", content_type: str = "text/html"):
    """Build a mock urllib response that returns body encoded as charset."""
    resp = MagicMock()
    resp.read.return_value = body.encode(charset, errors="replace")
    resp.headers.get_content_type.return_value = content_type
    resp.headers.get.return_value = f"{content_type}; charset={charset}"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def test_rejects_non_http_url():
    result = fetch_url("ftp://example.com/file")
    assert result.startswith("Error")
    assert "http" in result.lower()


def test_rejects_bare_domain():
    result = fetch_url("example.com")
    assert result.startswith("Error")


# ---------------------------------------------------------------------------
# Happy path — plain text stripping
# ---------------------------------------------------------------------------

def test_strips_html_tags():
    html = "<html><body><p>Hello world</p></body></html>"
    with patch("urllib.request.urlopen", return_value=_mock_response(html)):
        result = fetch_url("https://example.com")
    assert "Hello world" in result
    assert "<p>" not in result
    assert "<html>" not in result


def test_strips_script_blocks():
    html = "<html><script>alert('xss')</script><p>Safe content</p></html>"
    with patch("urllib.request.urlopen", return_value=_mock_response(html)):
        result = fetch_url("https://example.com")
    assert "Safe content" in result
    assert "alert" not in result


def test_strips_style_blocks():
    html = "<html><style>body { color: red; }</style><p>Visible</p></html>"
    with patch("urllib.request.urlopen", return_value=_mock_response(html)):
        result = fetch_url("https://example.com")
    assert "Visible" in result
    assert "color" not in result


def test_plain_text_false_preserves_tags():
    html = "<p>Hello</p>"
    with patch("urllib.request.urlopen", return_value=_mock_response(html)):
        result = fetch_url("https://example.com", plain_text=False)
    assert "<p>" in result


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------

def test_truncates_at_max_chars():
    body = "A" * 500
    with patch("urllib.request.urlopen", return_value=_mock_response(body)):
        result = fetch_url("https://example.com", max_chars=100)
    assert len(result) > 100          # includes truncation notice
    assert "Truncated" in result
    assert result.startswith("A" * 100)


def test_no_truncation_when_under_limit():
    body = "Short content"
    with patch("urllib.request.urlopen", return_value=_mock_response(body)):
        result = fetch_url("https://example.com", max_chars=16000)
    assert "Truncated" not in result
    assert "Short content" in result


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_http_error_returns_error_string():
    with patch("urllib.request.urlopen",
               side_effect=urllib.error.HTTPError("https://example.com", 404, "Not Found", {}, None)):
        result = fetch_url("https://example.com")
    assert result.startswith("Error")
    assert "404" in result


def test_url_error_returns_error_string():
    with patch("urllib.request.urlopen",
               side_effect=urllib.error.URLError("Name or service not known")):
        result = fetch_url("https://unreachable.invalid")
    assert result.startswith("Error")


def test_generic_exception_returns_error_string():
    with patch("urllib.request.urlopen", side_effect=Exception("unexpected")):
        result = fetch_url("https://example.com")
    assert result.startswith("Error")
