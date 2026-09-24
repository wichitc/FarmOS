import httpx

from app.config import settings
from app.core import email


class _FakeResponse:
    def __init__(self, status_code=202):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


def _with_api_key(monkeypatch, key="test-sendgrid-key"):
    monkeypatch.setattr(settings, "sendgrid_api_key", key)


def test_send_email_skips_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "sendgrid_api_key", "")
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: calls.append((a, kw)) or _FakeResponse())

    result = email.send_email(to="customer@example.com", subject="Hi", body="Body")
    assert result is False
    assert calls == []


def test_send_email_calls_sendgrid_with_correct_payload(monkeypatch):
    _with_api_key(monkeypatch)
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeResponse(202)

    monkeypatch.setattr(httpx, "post", fake_post)

    result = email.send_email(to="customer@example.com", subject="Hi", body="Body text")
    assert result is True
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == email.SENDGRID_API_URL
    assert call["json"]["personalizations"] == [{"to": [{"email": "customer@example.com"}]}]
    assert call["json"]["subject"] == "Hi"
    assert call["json"]["content"] == [{"type": "text/plain", "value": "Body text"}]
    assert call["headers"]["Authorization"] == "Bearer test-sendgrid-key"


def test_send_email_raises_on_sendgrid_error(monkeypatch):
    _with_api_key(monkeypatch)
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse(400))

    try:
        email.send_email(to="customer@example.com", subject="Hi", body="Body")
        assert False, "expected EmailSendError"
    except email.EmailSendError:
        pass
