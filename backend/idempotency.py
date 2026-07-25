"""
DI-02 — Idempotency for high-risk create/action endpoints.

A fleet client on a flaky mobile connection retries. Before DI-02 a retried
``POST /api/fuel`` (or a double-tapped "Approve" button) created a second
record: a duplicate fuel fill, a duplicate toll, a second repair ticket. There
was no way for the server to tell a retry apart from a genuine second event.

This module gives those endpoints Stripe-style idempotency: the client sends an
``Idempotency-Key`` header; the first request with a given key executes and its
response is stored; any later request with the **same key and same payload**
returns that stored response *without re-executing*, so no second record is
written. The same key with a **different payload** is a client error (409) — the
key has been reused for a different operation.

Why this works without database transactions
---------------------------------------------
The deployment's MongoDB is a standalone (no multi-document transactions — see
ATOMICITY_AND_IDEMPOTENCY.md). The key claim therefore rides on a **single**
atomic operation that a standalone *does* provide: a unique-index insert. The
first caller inserts the ``(org_id, scope, key)`` row and wins; a concurrent
duplicate hits ``DuplicateKeyError`` and is routed to the stored/there's-one-in-
flight path. No lock, no transaction, no race window.

Design rules
------------
* **Opt-in, non-breaking.** No header → old behaviour exactly. The safety is
  available to every high-risk endpoint and mandatory for none, so existing
  clients keep working while new/retrying clients get protection.
* **Org-scoped.** Keys are namespaced by organisation and endpoint ``scope``, so
  two tenants (or two endpoints) reusing the same key string never collide.
* **Fail closed on mismatch.** Same key, different request body → 409, never a
  silent second execution against a stale response.
* **Never stores secrets.** Only the request *hash* is kept, plus the endpoint's
  own JSON response (which the client already has).
"""
import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from database import db, current_org_id

HEADER = "Idempotency-Key"
COLLECTION = "idempotency_keys"

# A supplied key must be non-trivial (a client sending "1" gains nothing and
# risks colliding with its own unrelated calls). Bounded to keep the index small.
_MIN_LEN = 8
_MAX_LEN = 200


def request_fingerprint(payload) -> str:
    """Stable SHA-256 of a request payload, order-independent for dict keys."""
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def key_from_headers(headers) -> str | None:
    """Extract and validate the Idempotency-Key header, or None if absent.

    Raises 400 for a present-but-malformed key so a client is told rather than
    silently losing its retry protection.
    """
    raw = headers.get(HEADER)
    if raw is None:
        raw = headers.get(HEADER.lower())
    if raw is None:
        return None
    key = raw.strip()
    if not (_MIN_LEN <= len(key) <= _MAX_LEN):
        raise HTTPException(
            status_code=400,
            detail=f"{HEADER} must be {_MIN_LEN}-{_MAX_LEN} characters",
        )
    return key


async def replay_or_claim(scope: str, key: str, payload):
    """Claim ``key`` for ``scope``, or return a prior response to replay.

    Returns ``(None, fingerprint)`` when the caller now owns the key and must
    execute the operation, then call :func:`store_result`. Returns
    ``(stored_response, fingerprint)`` when an identical earlier request already
    completed — the caller returns it verbatim and does no work. Raises 409 on a
    payload mismatch or an in-flight duplicate.
    """
    fingerprint = request_fingerprint(payload)
    org_id = current_org_id.get()
    now = datetime.now(timezone.utc)
    doc = {
        "org_id": org_id,
        "scope": scope,
        "key": key,
        "request_hash": fingerprint,
        "status": "in_progress",
        "response": None,
        "created_at": now.isoformat(),
        # BSON datetime for the TTL index (a string would never expire).
        "created_at_dt": now,
    }
    try:
        # Unique (org_id, scope, key) index makes this the atomic claim.
        await db[COLLECTION].insert_one(doc)
        return None, fingerprint
    except DuplicateKeyError:
        pass

    existing = await db[COLLECTION].find_one(
        {"org_id": org_id, "scope": scope, "key": key}, {"_id": 0}
    )
    if not existing:
        # Row vanished between insert and read (TTL expiry at the exact instant).
        # Safest response is "retry", not a second execution.
        raise HTTPException(status_code=409, detail="Idempotency conflict; retry.")
    if existing.get("request_hash") != fingerprint:
        raise HTTPException(
            status_code=409,
            detail=f"{HEADER} was already used with a different request payload.",
        )
    if existing.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail="A request with this Idempotency-Key is still being processed.",
        )
    return existing.get("response"), fingerprint


async def store_result(scope: str, key: str, response):
    """Persist the endpoint's response so a later identical request can replay it."""
    org_id = current_org_id.get()
    await db[COLLECTION].update_one(
        {"org_id": org_id, "scope": scope, "key": key},
        {"$set": {"status": "completed", "response": response, "completed_at": _now_iso()}},
    )


async def release(scope: str, key: str):
    """Drop an in-progress claim after the operation failed before completing.

    Only deletes a still-``in_progress`` row, so it can never erase a completed
    result (which a concurrent request may already be replaying).
    """
    org_id = current_org_id.get()
    await db[COLLECTION].delete_one(
        {"org_id": org_id, "scope": scope, "key": key, "status": "in_progress"}
    )


def _now_iso():
    return datetime.now(timezone.utc).isoformat()
