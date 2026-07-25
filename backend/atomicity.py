"""
DI-02 — Atomic operations and compensating behaviour.

Several FleetFlow endpoints write more than one document: creating a FASTag
transaction *and* adjusting the vehicle balance; recording a tyre replacement
event *and* flipping the tyre's status; disposing a vehicle *and* closing its
downtimes *and* unassigning its drivers. If the process dies between those
writes the data is left half-applied.

The textbook fix is a multi-document transaction. **This deployment cannot use
one:** its MongoDB runs as a standalone, and standalone servers reject
transactions ("Transaction numbers are only allowed on a replica set member or
mongos"). So DI-02 uses the two mechanisms a standalone *does* provide safely:

1. **Single-document atomic updates as compare-and-swap.** A status transition
   is written with the expected current state in the *filter*
   (``update_one({"id": id, "status": "under_review"}, ...)``). MongoDB applies a
   single-document update atomically, so of two concurrent "approve" requests
   exactly one matches and wins; the loser's ``matched_count`` is 0 and it is
   rejected. This is real protection against double approval / double close /
   repeated cancellation, with no transaction required.

2. **Write-the-source-of-truth-first, derive-after.** Where a derived value
   accompanies a record (the FASTag balance, a tyre's status), the authoritative
   *event* is written first; the derived value is (re)computed from the full set
   of events afterwards. If the second step fails, the event still stands and the
   derived value is simply stale until the next recompute — never a lost event
   and never a double count on retry (DI-03 rebuilds derived values from source).

``transactions_supported()`` is probed once so that, on a deployment that *is* a
replica set, a future change can opt into real sessions; today it reports False
and the compensating paths above are used.
"""
import logging

from database import client

logger = logging.getLogger(__name__)

_txn_supported = None


async def probe_transactions() -> bool:
    """Detect multi-document transaction support once, at startup. Cached."""
    global _txn_supported
    if _txn_supported is not None:
        return _txn_supported
    try:
        hello = await client.admin.command("hello")
        # Transactions require a replica set (setName present) or a mongos.
        _txn_supported = bool(hello.get("setName")) or hello.get("msg") == "isdbgrid"
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("DI-02: could not probe transaction support: %s", e)
        _txn_supported = False
    if not _txn_supported:
        logger.info(
            "DI-02: MongoDB does not support multi-document transactions "
            "(standalone). Using compare-and-swap + compensating writes."
        )
    return _txn_supported


def transactions_supported() -> bool:
    return bool(_txn_supported)


async def swap_status(coll, item_id, expected_status, updates):
    """Atomic compare-and-swap on a single record's status.

    Writes ``updates`` only if the record is still in ``expected_status``.
    Returns True if this caller won the transition, False if another writer had
    already moved it (concurrent double action). One atomic single-document
    update — safe on a standalone.
    """
    from database import db

    res = await db[coll].update_one(
        {"id": item_id, "status": expected_status},
        {"$set": updates},
    )
    return res.matched_count == 1
