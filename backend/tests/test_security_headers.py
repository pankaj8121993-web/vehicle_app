"""
SEC-CLOSEOUT — baseline security headers on every API response.

Added at closeout to fill a gap the release gate surfaced: before this, only the
file-download endpoints set security headers; ordinary API responses had none.
"""
import pytest
from httpx import ASGITransport, AsyncClient

import server  # noqa: E402
from conftest import realhttp_run as _run  # shared loop (see conftest)


def _get(path="/api/"):
    async def go():
        t = ASGITransport(app=server.app)
        async with AsyncClient(transport=t, base_url="http://sec") as c:
            return await c.get(path)
    return _run(go())


@pytest.mark.parametrize("header,value", [
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "no-referrer"),
])
def test_baseline_headers_present(header, value):
    r = _get()
    assert r.headers.get(header) == value


def test_hsts_absent_in_development(monkeypatch):
    """HSTS must not be emitted over the plain-HTTP preview — it would pin
    browsers to HTTPS for a host that doesn't serve it."""
    monkeypatch.setenv("APP_ENV", "development")
    r = _get()
    assert "strict-transport-security" not in {k.lower() for k in r.headers}


def test_headers_on_error_responses_too():
    """A 404 still carries the headers (middleware runs on every response)."""
    r = _get("/api/does-not-exist")
    assert r.headers.get("x-content-type-options") == "nosniff"
