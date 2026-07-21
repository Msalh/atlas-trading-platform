"""
Production-hardening: analyze_with_claude() must bound every real Anthropic
request with an explicit timeout - previously it relied entirely on the SDK's
own (much longer) default. Every caller already runs this in a background
thread off the order-relay critical path (see atlas/services/claude.py's own
module docstring and atlas/ai.py) - this test proves the timeout is actually
wired into the request, and that a timeout still degrades gracefully via the
existing (None, str(error)) contract rather than raising, with no retry.
"""
import anthropic

from atlas.config import settings
from atlas.services.claude import CLAUDE_REQUEST_TIMEOUT_SECONDS, analyze_with_claude


class _FakeMessages:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.create_calls: list[dict] = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class _FakeAnthropicClient:
    last_init_kwargs: dict = {}

    def __init__(self, **kwargs):
        _FakeAnthropicClient.last_init_kwargs = kwargs
        self.messages = _FakeAnthropicClient._messages_to_use

    # test-controlled: set by each test before constructing analyze_with_claude's client
    _messages_to_use = None


class _FakeContentBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeResponse:
    def __init__(self, text: str):
        self.content = [_FakeContentBlock(text)]


def _install_fake_client(monkeypatch, messages: _FakeMessages):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-anthropic-key")
    _FakeAnthropicClient._messages_to_use = messages
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropicClient)


def test_request_carries_the_explicit_timeout(monkeypatch):
    messages = _FakeMessages(response=_FakeResponse("ok"))
    _install_fake_client(monkeypatch, messages)

    text, error = analyze_with_claude("a prompt")

    assert (text, error) == ("ok", None)
    # Both the client construction and the individual request are bounded -
    # belt and suspenders, since either one alone is enough to fix the bug,
    # but the request-level one is the one that actually matters if a future
    # change ever constructs the client once and reuses it across calls.
    assert _FakeAnthropicClient.last_init_kwargs.get("timeout") == CLAUDE_REQUEST_TIMEOUT_SECONDS
    assert messages.create_calls[0].get("timeout") == CLAUDE_REQUEST_TIMEOUT_SECONDS


def test_a_timeout_degrades_gracefully_with_no_retry(monkeypatch):
    timeout_error = anthropic.APITimeoutError(request=object())
    messages = _FakeMessages(error=timeout_error)
    _install_fake_client(monkeypatch, messages)

    text, error = analyze_with_claude("a prompt")

    assert text is None
    assert error == str(timeout_error)
    assert len(messages.create_calls) == 1  # exactly one attempt - no retry loop


def test_no_api_key_still_returns_the_existing_not_configured_tuple(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    text, error = analyze_with_claude("a prompt")
    assert (text, error) == (None, "ANTHROPIC_API_KEY not configured")
