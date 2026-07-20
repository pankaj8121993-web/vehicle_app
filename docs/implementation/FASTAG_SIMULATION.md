# FleetFlow — Demo-Only FASTag Simulation (FASTAG-01)

**Status:** Implemented on `feature/fastag-01-demo-simulation`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. Threat addressed (P0)

`POST /fastag/sync/{vehicle_id}` fabricates FASTag toll/recharge activity because
no public NPCI/bank FASTag API exists. Before FASTAG-01 it was `require_user` and
available to **every organisation**. Any authenticated user could, against a real
vehicle:

* generate **4–8 random toll transactions** plus a random recharge, and
* **overwrite `fastag_balance` with `random.uniform(250, 2800)`** — a number
  invented on each call.

That is fabricated financial activity and silent balance corruption in a real
tenant. It was also non-idempotent: every click added more fake transactions and
re-randomised the balance.

## 2. Three separated paths

FASTAG-01 draws an explicit line between three things that were blurred:

| Path | What it is | Where |
| --- | --- | --- |
| **Demo simulation** | Synthetic data, demo org only, fail-closed elsewhere | `fastag_simulation.py` + `POST /fastag/sync` |
| **Manual import** | A user entering a real transaction they hold a receipt for | `POST /fastag` (generic create), tenant-scoped, unchanged |
| **Live provider** | A real bank/NPCI feed | Does not exist. `PROVIDER_INTEGRATION_AVAILABLE = False` so any provider path fails closed rather than silently no-op |

Simulated rows carry `source = "demo_simulation"` — distinct from a manual entry
(no source) and from the old `"auto_sync"` marker — so simulated data is always
identifiable and can never be mistaken for real activity.

## 3. Controls

* **Fail closed off the demo org.** `simulation_allowed(user)` requires **both**
  `is_demo` **and** membership of the canonical `DEMO_ORG_ID`. A real user cannot
  satisfy it; a stray `is_demo` flag on a real org cannot either. The endpoint
  calls `assert_simulation_allowed` before any read or write, so a non-demo
  caller gets 403 and **nothing is ever written**.
* **Defence in depth.** The endpoint also requires the `fastag:simulate`
  permission (AUTHZ-01), so a demo viewer is refused too. Permission *and* demo
  membership are both necessary.
* **Idempotent / safe replay.** A run carries a batch key (from a caller-supplied
  `idempotency_key` or a fresh one). Replaying the same key returns the original
  result with `replayed: true` and **writes nothing new**, so a double-click or
  retry cannot double the fabricated activity. Generation is seeded by the batch
  key, so a replay reproduces the same run.
* **No random balance.** The balance is **computed** from the vehicle's FASTag
  transactions (recharges − tolls), never invented, so it is stable across
  replays and reflects the actual rows.
* **Bounded values.** Amounts come from fixed toll/recharge sets; dates fall
  within a bounded look-back; run size is capped. No free-form value is generated.
* **Same-tenant vehicle.** `db.vehicles` is tenant-scoped, so a cross-tenant
  vehicle id simply 404s — the simulation can only ever touch a demo vehicle.
* **Audited.** Each run writes a `fastag.simulate` event to `security_audit`
  (vehicle id, count, batch key — no secrets).

## 4. Verification

`backend/tests/test_fastag_simulation.py` — **21 tests**: unit tests over the
guard (both markers must agree; every non-demo shape refused), batch determinism,
bounded amounts/size, source marker, computed (not random) balance, and the
no-live-provider invariant; plus real-HTTP tests proving a **real onboarded org
is refused (403) and writes nothing**, the demo org can run it, replay under a
key adds no transactions, and the returned balance equals the computed one.

The central `test_tenant_isolation_matrix` also asserts a real org cannot sync
its own or another org's vehicle.

| Check | Result |
| --- | --- |
| Full backend suite | **566 passed, 3 skipped** (544 pre-FASTAG still green) |
| FASTAG-01 additions | 21 (+1 in the matrix) |
| Mutation test | Disabling the demo guard fails both the unit and real-HTTP tests |
| Ruff / Gitleaks | Clean |
| Live smoke | demo sync 200 + `replayed:true` on retry; **real-org sync 403** |

## 5. Remaining limitations

* **Balance can go negative** when a simulated batch has more tolls than
  recharges. This is deterministic and reflects the generated rows; it is a demo
  realism nicety, not a correctness or security issue. A real feed would not have
  this shape.
* **The `fastag:simulate` permission** is held by all acting roles (from
  AUTHZ-01); the demo-org check is what actually restricts it. The permission is
  retained as defence in depth and as the hook if simulation is ever narrowed to
  specific roles.
* **Live-provider integration** is deliberately absent (`PROVIDER_INTEGRATION_AVAILABLE
  = False`). When a real feed is added it must have its own authentication,
  reconciliation and idempotency — it must not reuse the simulation path.
