import json
import types
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.generation.llm import _parse_stream, stream


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_ndjson_lines(tokens: list[str]) -> list[bytes]:
    """Produce byte lines matching Ollama's NDJSON stream format."""
    lines = []
    for i, token in enumerate(tokens):
        is_last = i == len(tokens) - 1
        lines.append(json.dumps({"response": token, "done": is_last}).encode())
    return lines


def _mock_response(tokens: list[str]) -> MagicMock:
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.raise_for_status = MagicMock()
    mock.iter_lines.return_value = _make_ndjson_lines(tokens)
    return mock


# ── _parse_stream unit tests ──────────────────────────────────────────────────

def test_parse_stream_yields_tokens():
    lines = _make_ndjson_lines(["Hello", " world", "!"])
    assert list(_parse_stream(iter(lines))) == ["Hello", " world", "!"]


def test_parse_stream_stops_at_done():
    # done=True on "tok2"; anything appended after must not appear
    lines = _make_ndjson_lines(["tok1", "tok2"])
    lines.append(json.dumps({"response": "extra", "done": False}).encode())
    result = list(_parse_stream(iter(lines)))
    assert "extra" not in result
    assert result == ["tok1", "tok2"]


def test_parse_stream_skips_empty_byte_lines():
    lines = [b"", b"   ", json.dumps({"response": "hi", "done": True}).encode()]
    assert list(_parse_stream(iter(lines))) == ["hi"]


def test_parse_stream_skips_invalid_json():
    lines = [b"not-json!!!", json.dumps({"response": "ok", "done": True}).encode()]
    assert list(_parse_stream(iter(lines))) == ["ok"]


def test_parse_stream_skips_empty_response_field():
    lines = [
        json.dumps({"response": "", "done": False}).encode(),
        json.dumps({"response": "tok", "done": True}).encode(),
    ]
    assert list(_parse_stream(iter(lines))) == ["tok"]


def test_parse_stream_handles_string_lines():
    lines = ['{"response": "str_line", "done": true}']
    assert list(_parse_stream(iter(lines))) == ["str_line"]


def test_parse_stream_single_token():
    lines = _make_ndjson_lines(["only"])
    assert list(_parse_stream(iter(lines))) == ["only"]


def test_parse_stream_empty_input():
    assert list(_parse_stream(iter([]))) == []


# ── stream integration tests (patched requests) ───────────────────────────────

def test_stream_is_generator():
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock_post.return_value = _mock_response(["hi"])
        result = stream("test prompt")
        assert isinstance(result, types.GeneratorType)


def test_stream_yields_correct_tokens():
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock_post.return_value = _mock_response(["Hello", " world"])
        assert list(stream("test prompt")) == ["Hello", " world"]


def test_stream_calls_generate_endpoint():
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock_post.return_value = _mock_response(["x"])
        list(stream("q", base_url="http://localhost:11434"))
        url = mock_post.call_args[0][0]
        assert url == "http://localhost:11434/api/generate"


def test_stream_strips_trailing_slash_from_base_url():
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock_post.return_value = _mock_response(["x"])
        list(stream("q", base_url="http://localhost:11434/"))
        url = mock_post.call_args[0][0]
        assert url == "http://localhost:11434/api/generate"


def test_stream_sends_model_in_payload():
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock_post.return_value = _mock_response(["x"])
        list(stream("q", model="llama3.2:8b"))
        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == "llama3.2:8b"


def test_stream_sets_stream_true_in_payload():
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock_post.return_value = _mock_response(["x"])
        list(stream("q"))
        payload = mock_post.call_args[1]["json"]
        assert payload["stream"] is True


def test_stream_sends_prompt_in_payload():
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock_post.return_value = _mock_response(["x"])
        list(stream("my question"))
        payload = mock_post.call_args[1]["json"]
        assert payload["prompt"] == "my question"


def test_stream_custom_base_url():
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock_post.return_value = _mock_response(["x"])
        list(stream("q", base_url="http://myhost:9999"))
        url = mock_post.call_args[0][0]
        assert "myhost:9999" in url


def test_stream_raises_on_http_error():
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock = MagicMock()
        mock.__enter__ = lambda s: s
        mock.__exit__ = MagicMock(return_value=False)
        mock.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock.iter_lines.return_value = iter([])
        mock_post.return_value = mock
        with pytest.raises(requests.HTTPError):
            list(stream("q"))


def test_stream_multi_token_concatenated():
    tokens = ["The ", "answer ", "is ", "42."]
    with patch("backend.generation.llm.requests.post") as mock_post:
        mock_post.return_value = _mock_response(tokens)
        result = "".join(stream("q"))
        assert result == "The answer is 42."
