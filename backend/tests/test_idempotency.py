"""
DI-02 — Unit tests for the idempotency helpers (no DB).

The replay/claim flow is proven end-to-end in ``test_di02_atomicity``; these
cover the pure pieces: fingerprint stability and header validation.
"""
import pytest
from fastapi import HTTPException

import idempotency


def test_fingerprint_is_key_order_independent():
    a = idempotency.request_fingerprint({"a": 1, "b": 2})
    b = idempotency.request_fingerprint({"b": 2, "a": 1})
    assert a == b


def test_fingerprint_changes_with_value():
    a = idempotency.request_fingerprint({"amount": 100})
    b = idempotency.request_fingerprint({"amount": 101})
    assert a != b


def test_key_absent_returns_none():
    assert idempotency.key_from_headers({}) is None


def test_key_valid_returned_stripped():
    assert idempotency.key_from_headers({"Idempotency-Key": "  abcdefgh  "}) == "abcdefgh"


def test_key_case_insensitive_header():
    assert idempotency.key_from_headers({"idempotency-key": "abcdefghij"}) == "abcdefghij"


@pytest.mark.parametrize("bad", ["", "short", "x" * 5])
def test_key_too_short_rejected(bad):
    with pytest.raises(HTTPException) as e:
        idempotency.key_from_headers({"Idempotency-Key": bad})
    assert e.value.status_code == 400


def test_key_too_long_rejected():
    with pytest.raises(HTTPException):
        idempotency.key_from_headers({"Idempotency-Key": "x" * 201})
