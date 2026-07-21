# FleetFlow — Data Integrity Model (DI-01)

**Phase:** Data Integrity and Financial Correctness
**Workstream:** DI-01 — Canonical records and invariants
**Status:** Repository controls implemented and tested. Production reconciliation not performed.

> This document defines the authoritative source of truth for every major
> FleetFlow business event and the invariants the backend enforces on it. It is
> the reference the later workstreams build on: DI-02 (atomicity/idempotency),
> DI-03 (reconciliation), DI-04 (data-quality scanning) and DI-CLOSEOUT.

---

## 1. Principles

1. **One canonical record per business event.** Each economic or operational
   event is a single document in one collection. Everything else — dashboards,
   reports, exports, per-vehicle and per-trip totals — is *derived* from those
   records and must be recomputable from them (DI-03).
2. **The server owns identity, ownership, audit and derived fields.** A client
   supplies only the descriptive fields of an event. `org_id`, `id`,
   `created_at/by`, workflow state and all calculated values are set by the
   backend and rejected from request bodies (TEN-01 + DI-01).
3. **Money is validated as decimal.** Amounts are checked and quantised through
   `decimal.Decimal` (`ROUND_HALF_UP`, 2 places) before storage, so no sub-paisa
   float noise can enter a total.
4. **Reject, never silently coerce.** A bad amount, quantity, odometer, ordering
   or reference is an HTTP 400/409 that names the field — not a clamped or
   dropped value.
5. **Preserve history.** Disposed/exited/closed records are terminal, not
   deleted. New operational activity against them is refused; historical records
   remain readable.

---

## 2. Enforcement modules

| Module | Responsibility |
| --- | --- |
| `backend/invariants.py` | Pure, DB-free numeric & ordering invariants: `money`, `quantity`, `odometer`, `require_order`, `require_date_order`, `enforce_record_invariants(collection, doc)`. Unit-tested in `tests/test_invariants.py`. |
| `backend/references.py` | DB-aware referential integrity: `validate_references(collection, doc)` — foreign keys resolve **in the caller's organisation** and (for new operational activity) point at in-service entities. |
| `backend/tenant_policy.py` | Protected-field policy (TEN-01), extended by DI-01 with the derived fields `distance`, `mileage`, `fuel_cost_per_km`, `days`. |
| `backend/workflow.py` | Status lifecycle & transitions (WF-01), reused by DI-01's repair cost-lock. |
| `backend/helpers.py` `make_crud` | Runs `enforce_record_invariants` + `validate_references` on create, and invariants + the repair cost-lock on generic update. |
| `backend/server.py` `_ensure_integrity_indexes` | Organisation-scoped uniqueness indexes, built safely (best-effort, logged). |

The create path is: **validate model → `enforce_record_invariants` → `validate_references` → assign server fields → domain `on_create` (derived values) → insert.** Invariants run *before* derived computation so a bad amount can never reach a mileage or balance calculation.

---

## 3. Canonical record catalogue

For each event: the collection, its natural/duplicate key, required ownership &
timestamps, the money/derived fields, the status lifecycle and the
reversal/cancellation method.

Common to **every** tenant record: `id` (UUID, stable identifier), `org_id`
(session-derived, immutable), `created_at`, `created_by`, `is_test_data`.
Ownership and audit fields are rejected from request bodies (TEN-01).

### 3.1 Vehicles — `vehicles`
- **Canonical event:** a vehicle master record.
- **Natural key / uniqueness:** `(org_id, vehicle_number)` — unique index `uniq_org_vehicle_number`.
- **Money:** `purchase_price`, `sale_value` (≥ 0, 2dp).
- **Status lifecycle (WF-01):** `active|inactive|maintenance|idle` ⇄, terminal `sold|scrapped` (disposal is management/admin only, and irreversible).
- **Reversal/cancellation:** disposal is terminal; there is no un-dispose. Delete is blocked when history exists — archival/disposal is used instead.
- **Derived (not stored authoritative):** `current_odometer` is forwarded upward only, never decreased silently; `fastag_balance` is recomputed from FASTag transactions (DI-03).

### 3.2 Drivers — `drivers`
- **Canonical event:** a driver master record.
- **References:** `assigned_vehicle_id` → a real, in-service vehicle in the org.
- **Status lifecycle (WF-01):** `active|on_leave` ⇄, terminal `resigned|terminated` (exit is management/admin only).
- **Reversal/cancellation:** exit is terminal; delete blocked when trips/fuel/accidents exist.

### 3.3 Trips — `trips`
- **Canonical event:** one vehicle movement.
- **References:** `vehicle_id` (in-service), optional `driver_id` (not exited).
- **Numeric invariants:** `opening_km`, `closing_km` ≥ 0 and finite; **`closing_km` ≥ `opening_km`** on create *and* close.
- **Money:** `toll_expense`, `parking_expense`, `misc_expense`.
- **Derived:** `distance = closing_km − opening_km` (server-computed, client-rejected). `status` `ongoing → completed`.
- **Reversal/cancellation:** completion is terminal (re-close is an idempotent no-op; distance/odometer are not recomputed).

### 3.4 Fuel transactions — `fuel_entries`
- **Canonical event:** one fuel fill.
- **References:** `vehicle_id` (in-service), optional `driver_id`.
- **Numeric invariants:** `quantity` > 0, finite, bounded; `odometer` ≥ 0, finite, bounded.
- **Money:** `amount`.
- **Derived:** `mileage`, `fuel_cost_per_km` (computed from the previous fill; client-rejected).
- **Reversal:** correction via a new/edited entry; DI-03 covers recomputation of downstream mileage.

### 3.5 FASTag transactions — `fastag_transactions`
- **Canonical event:** one toll or recharge.
- **References:** `vehicle_id`.
- **Money:** `amount` (≥ 0). `txn_type` ∈ `toll|recharge`.
- **Derived:** vehicle `fastag_balance` is adjusted from the transaction and is fully recomputable from the transaction set (DI-03). Simulated rows carry `source="demo_simulation"` and a `sim_batch` idempotency key (FASTAG-01).
- **Duplicate strategy:** demo simulation is idempotent by `sim_batch`; DI-02 adds import idempotency; DI-04 detects duplicates.

### 3.6 Repairs / service tickets — `repairs`
- **Canonical event:** a maintenance/repair ticket.
- **Natural key:** `(org_id, ticket_number)` — unique index `uniq_org_ticket_number` (`TKT-YYYY-NNNN`).
- **Money:** `cost`. **Locked once approved** — from `approved` onward the cost cannot be changed through a generic `PUT`; the ticket action carries authorised cost changes.
- **Status lifecycle (WF-01):** `open → under_review → approved → sent_for_repair → in_repair → repaired → closed`, with `under_review → open` rejection. Optimistic `_version` guards concurrent advances.
- **Reversal:** rejection path back to `open`; terminal `closed`.

### 3.7 Services & greasing — `services`, `greasings`
- **Canonical event:** a scheduled maintenance/greasing record.
- **References:** `vehicle_id` (in-service). **Money:** `cost`. **Odometer:** validated.

### 3.8 Tyres & tyre events — `tyres`, `tyre_events`
- **Canonical event:** a tyre master and its lifecycle events.
- **Natural key:** `(org_id, tyre_number)` — unique index `uniq_org_tyre_number`.
- **References:** tyre events → a real `tyre_id` (+ derived `vehicle_id`). **Money:** `cost`. **Odometer:** `installation_km`, `removal_km`, event `odometer`.

### 3.9 Accidents — `accidents`
- **Canonical event:** an accident/insurance record.
- **Money:** `repair_cost`, `claim_amount`, `settlement_amount` — **`settlement_amount` ≤ `claim_amount`** (the "paid cannot exceed eligible" rule the schema expresses).

### 3.10 Downtime — `downtimes`
- **Canonical event:** a period a vehicle is out of service.
- **Ordering:** `end_date` ≥ `start_date`. **Derived:** `days`, `status` `open → closed` (closed on disposal too).

### 3.11 Expenses — `expenses`
- **Canonical event:** a manual expense line, part of the unified ledger.
- **References:** `vehicle_id`. **Money:** `amount`.
- **Note:** the *authoritative expense ledger* is the union of source-module rows (fuel, repairs, tyres, FASTag toll, trip toll/parking/misc, accidents, services/greasing, manual expenses) assembled by `helpers.gather_expenses`. DI-03 formalises this as the single reconciliation service.

### 3.12 Documents — `documents`
- **Canonical event:** a compliance document tied to a vehicle (affects operational/compliance status via expiry).
- **References:** `vehicle_id`.

### 3.13 Budgets — `budgets`
- **Canonical event:** a per-category monthly budget. **Money:** `amount` > 0. Unique per `(category, month)` within org (enforced in the route).

### 3.14 Payments / approvals
FleetFlow has **no standalone payment or generic-approval collection** today
(consistent with WF-01's findings). The realised money-state controls are:
repair approval (WF-01 lifecycle + DI-01 cost-lock) and accident
`settlement ≤ claim`. A future dedicated payment ledger is out of scope and
recorded as future work.

---

## 4. Invariant summary (what the backend rejects)

| Rule | Where enforced | Result |
| --- | --- | --- |
| Monetary values use safe decimal handling (2dp, `ROUND_HALF_UP`) | `invariants.money` | quantised or 400 |
| Negative amounts rejected (unless documented reversal) | `invariants.money` | 400 |
| Non-finite / out-of-range amounts rejected | `invariants.money` | 400 |
| Fuel quantity > 0, finite, bounded | `invariants.quantity` | 400 |
| Odometer ≥ 0, finite, bounded | `invariants.odometer` | 400 |
| `closing_km` ≥ `opening_km` (create + close) | `invariants.require_order` / `close_trip` | 400 |
| Downtime `end_date` ≥ `start_date` | `invariants.require_date_order` | 400 |
| Accident `settlement_amount` ≤ `claim_amount` | `invariants.enforce_record_invariants` | 400 |
| Referenced vehicle/driver/tyre/vendor exists **in the same org** | `references.validate_references` | 400 |
| No new operational activity on a sold/scrapped vehicle | `references.validate_references` | 400 |
| No trip assigned to a resigned/terminated driver | `references.validate_references` | 400 |
| Approved repair cost not editable via generic `PUT` | `helpers.make_crud` | 409 |
| System-calculated fields (`distance`, `mileage`, `fuel_cost_per_km`, `days`, `total`, `balance`) not client-supplied | `tenant_policy` protected fields | 400 |
| Ownership / identity / audit / workflow fields not client-supplied | `tenant_policy` (TEN-01) | 400 |
| Every record has a stable `id` (UUID) | create paths | — |

---

## 5. Uniqueness indexes

Built at startup by `_ensure_integrity_indexes` as compound `(org_id, key)`
unique indexes with a partial filter (so records missing an optional key do not
collide on null). The same natural key may exist in different organisations, never
twice within one.

| Collection | Key | Index |
| --- | --- | --- |
| vehicles | `vehicle_number` | `uniq_org_vehicle_number` |
| tyres | `tyre_number` | `uniq_org_tyre_number` |
| repairs | `ticket_number` | `uniq_org_ticket_number` |

**Safety:** each index is built independently and best-effort. On a database that
already holds a duplicate, the build logs a warning and startup continues rather
than crashing; the DI-04 scanner reports those duplicates so an operator can
resolve them, after which the build succeeds. **No index build deletes or
rewrites data.** DI-02 adds an idempotency-key unique index for replay safety.

---

## 6. Audit expectations

- Terminal/side-effecting transitions (vehicle disposal, driver exit, trip close,
  repair transition, FASTag simulation) write non-secret `security_audit` entries
  (ids + action + from/to only) via `record_security_event` — unchanged from
  WF-01/AUTHZ-01 and reused here.
- DI-04 adds a non-secret evidence log for integrity scans/repairs.

---

## 7. Tests

| Test | Coverage |
| --- | --- |
| `tests/test_invariants.py` (38) | Pure money/quantity/odometer/ordering + `enforce_record_invariants` per collection. |
| `tests/test_di01_enforcement.py` (16) | Real-HTTP: negative/quantised money, zero quantity, negative odometer, km ordering, settlement≤claim, referential integrity (non-existent + cross-tenant vehicle/driver, disposed vehicle), calculated-field injection blocked, approved-repair cost lock. |

Full backend suite after DI-01: **664 passed, 3 skipped** (610 pre-existing + 54 new). Existing security and tenant-isolation tests are unchanged and still pass.

---

## 8. Explicit non-goals / future work

- A standalone **payment ledger** with partial payments, TDS/GST and reconciliation (documented; not built).
- **Decimal128 storage** — validation is exact decimal; storage remains float in MongoDB for this schema. A future migration to `decimal128` is recorded as future work.
- **Odometer continuity across a vehicle's full history** (out-of-sequence backdated readings) is detected by the DI-04 scanner rather than blocked at write time.
- Global uniqueness beyond the three natural keys above (e.g. chassis/engine numbers) — recorded as future work.
