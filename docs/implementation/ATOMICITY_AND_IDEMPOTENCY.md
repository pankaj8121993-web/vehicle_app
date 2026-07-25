# FleetFlow — Atomicity and Idempotency (DI-02)

**Phase:** Data Integrity and Financial Correctness
**Workstream:** DI-02 — Atomic operations and idempotency
**Status:** Repository controls implemented, tested and mutation-tested. Production reconciliation not performed.

> Builds on DI-01 ([DATA_INTEGRITY_MODEL.md](DATA_INTEGRITY_MODEL.md)). Prevents
> duplicate transactions and partial business operations.

---

## 1. The two problems

1. **Duplicate transactions.** A retried `POST` (flaky mobile network, an
   impatient double-tap on "Approve") created a second record — a duplicate fuel
   fill, toll, or repair ticket. Nothing let the server tell a retry from a
   genuine second event.
2. **Partial operations.** Several endpoints write more than one document
   (transaction + balance; tyre event + tyre status; disposal + downtime close +
   driver unassign). A crash between writes left the data half-applied.

---

## 2. Why not database transactions here

The textbook fix for (2) is a multi-document transaction. **This deployment
cannot use one.** Its MongoDB runs as a **standalone**, and a standalone rejects
transactions outright:

```
Transaction numbers are only allowed on a replica set member or mongos
```

`atomicity.probe_transactions()` confirms this at startup and logs it.
`transactions_supported()` reports `False`, so DI-02 uses the two mechanisms a
standalone *does* provide safely. On a future replica-set deployment the probe
would report `True` and the code can opt into real sessions without changing the
call sites.

---

## 3. Mechanism 1 — Idempotency keys (`backend/idempotency.py`)

Stripe-style, opt-in via an `Idempotency-Key` request header.

- **Claim.** The first request inserts an `idempotency_keys` row keyed
  `(org_id, scope, key)`. That collection has a **unique index** on those three
  fields, so the insert *is* the atomic claim — the first caller wins; a
  concurrent duplicate hits `DuplicateKeyError` and is routed to the
  replay/there's-one-in-flight path. No lock, no transaction, no race window
  (the one atomic op a standalone guarantees is a single-document write, and a
  unique-index insert is exactly that).
- **Replay.** A later request with the **same key and same payload** returns the
  stored response verbatim — no second record.
- **Mismatch.** The **same key with a different payload** → `409` (the key was
  reused for a different operation).
- **In flight.** Same key while the first is still processing → `409`.
- **Failure releases the key.** If the operation errors before completing, the
  claim is deleted so a genuine retry can proceed rather than being stuck as
  "in progress" until the TTL.
- **Bounded.** A 24-hour TTL index reaps old keys. Only the request *hash* and
  the endpoint's own JSON response are stored — never secrets.

Validation and referential checks (DI-01) run **before** the claim, so a request
that would `400` never consumes a key.

### Endpoints with idempotency support

| Endpoint | Scope |
| --- | --- |
| Every generic create (`make_crud`): trips, fuel, services, greasings, repairs, tyres, tyre-events, accidents, fastag, downtime, expenses, documents, vendors, calendar, compliance | `create:<collection>` |
| `POST /vehicles`, `POST /drivers` | `create:vehicles` / `create:drivers` |
| `PATCH /repairs/{id}/status` (approve/advance) | `repair-transition:<id>` |
| `POST /fastag/sync/{id}` (demo simulation) | pre-existing `sim_batch` key (FASTAG-01) |

No header → **exactly the old behaviour** (non-breaking).

---

## 4. Mechanism 2 — Compare-and-swap for state transitions

A status transition is written with the **expected current state in the filter**:

```python
update_one({"id": id, "status": "under_review"}, {"$set": {...approved...}})
```

MongoDB applies a single-document update atomically, so of two concurrent
"approve" requests exactly one matches `under_review` and wins; the loser's
`matched_count` is `0` and it is rejected with `409`. This is real protection —
no transaction required — against:

- **Double approval** — `advance_repair` swaps on the ticket's stored status.
- **Double close** — `close_trip` swaps on `"ongoing"`; a second close returns
  the completed trip idempotently rather than re-applying the odometer bump.
- **Repeated transition** — re-entering the current state is treated as an
  idempotent no-op (returns the record; emits no second audit), so a retried or
  serialised double action cannot double-apply a side effect.

`atomicity.swap_status(coll, id, expected_status, updates)` centralises the
pattern and returns whether this caller won.

---

## 5. Mechanism 3 — Write-source-first with derivable state

Where a derived value accompanies a record, the authoritative **event** is
written first and the derived value updated **after**, via a new `after_create`
hook on `make_crud`:

| Operation | Source (written first) | Derived (after) | Compensation if the derived step fails |
| --- | --- | --- | --- |
| FASTag transaction | `fastag_transactions` row | vehicle `fastag_balance` (`$inc`) | balance is a cache DI-03 recomputes from the transaction set; the event stands |
| Tyre replacement | `tyre_events` row | tyre `status="removed"`, `removal_km` | tyre status is rebuildable from its events; the event stands |

Previously these ran the derived write *first* (e.g. the balance `$inc` inside a
pre-insert hook), so a failed insert could leave a balance moved for a
transaction that never existed. Now the worst case is a **stale** derived value
that the next recompute heals — never a lost event, never a double count on a
keyed retry.

Vehicle disposal (`update_vehicle`) applies its authoritative status transition
via the WF-01 path and its side effects (close downtimes, unassign drivers)
around it; disposal is terminal and idempotent, so a retry is a no-op.

---

## 6. "Never mark complete before all writes succeed"

The generic create wraps id assignment, `on_create`, the insert and
`after_create` in a single `try`; any failure **releases the idempotency claim**
and re-raises, so the endpoint never returns success — and never stores a
replayable "completed" response — for a create that did not fully land.

---

## 7. Specific duplicate-protection guarantees

| Requirement | How |
| --- | --- |
| Prevent double approval | compare-and-swap on ticket status + idempotent no-op |
| Prevent double payment | no payment collection exists; the money-state action is repair approval (above) and accident settlement (DI-01 cap) |
| Prevent duplicate FASTag import | idempotency key on `POST /fastag`; demo sync already idempotent by `sim_batch` |
| Prevent duplicate fuel entry | idempotency key on `POST /fuel` |
| Prevent duplicate repair/tyre event | idempotency key on `POST /repairs`, `POST /tyre-events` |
| Prevent repeated cancellation/reversal | compare-and-swap + terminal-state rules (WF-01); re-entering a state is a no-op |
| Safe retries | idempotency replay returns the original record |
| Optimistic version checks | `repairs` carry `_version`; `advance_repair` honours `expected_version` (WF-01) alongside the swap |

---

## 8. Tests and mutation evidence

| Test | Coverage |
| --- | --- |
| `tests/test_idempotency.py` (7) | Fingerprint stability, header validation. |
| `tests/test_di02_atomicity.py` (11) | Real-HTTP: retried create writes one record; same-key/different-payload 409; no-key allows two; failed request does not consume the key; concurrent approval applies exactly once (audit ground-truth); **`swap_status` compare-and-swap primitive**; concurrent close applies once; tyre-replacement and FASTag side effects land. |

**Mutation testing** (both reverted after):
1. *Duplicate protection* — patched `idempotency.replay_or_claim` to never replay
   → `test_retried_create_with_same_key_writes_one_record` **fails** (a duplicate
   fuel row is written). Detector works.
2. *Atomicity* — patched `atomicity.swap_status` to drop the expected-status
   filter (`{"id": id}` only) → `test_swap_status_is_compare_and_swap` **fails**
   (the second swap wins when it must lose). Detector works.

Full backend suite after DI-02: **682 passed, 3 skipped**. Ruff clean; frontend
build OK; gitleaks clean. Security/tenant tests unchanged.

---

## 9. Non-goals / future work

- **Real multi-document transactions** — available only on a replica set; the
  code is ready to opt in when deployed on one.
- A **standalone payment ledger** with its own idempotent settle/reverse actions
  (no payment collection exists today).
- Making idempotency **mandatory** on the highest-risk endpoints (currently
  opt-in to stay non-breaking) — a frontend change, recorded as future work.
- Optimistic `_version` on **every** collection's generic update (today wired to
  the repair transition) — recorded as future work.
