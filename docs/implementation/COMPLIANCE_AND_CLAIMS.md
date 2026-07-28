# FleetFlow — Compliance, Documents, Accidents and Claims (OPS-04)

**Status:** Implemented on `feature/ops-04-compliance-claims`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. Starting point

Document/licence expiry alerting already existed (`routes_compliance.compliance_overview`,
"latest per (vehicle, doc_type)"), and accidents carried free-text `claim_status`
plus `claim_amount`/`settlement_amount` with a DI-01 `settlement ≤ claim` rule.
OPS-04 adds document *validity + history* and a real, controlled *insurance-claim
lifecycle*.

## 2. Documents

* **Validity.** `invariants.enforce_record_invariants` now applies to `documents`:
  `expiry_date` cannot precede `issue_date` (400).
* **Supersede, don't overwrite.** A new document of the same `(vehicle_id,
  doc_type)` is filed `is_current = True`; the previous current record is marked
  `is_current = False` with `superseded_by`/`superseded_at` (`after_document_create`).
  Old evidence is preserved, and current vs superseded is explicit.
* The compliance overview continues to surface expiring/expired documents and
  licences per tenant (org-scoped, disposed vehicles / exited drivers excluded).

## 3. Accident insurance-claim lifecycle

Keyed on the accident's `claim_status` via `workflow.ACCIDENT_CLAIM_WORKFLOW`:

```
reported → evidence_collected → claim_submitted → under_survey → approved → settled → closed
                                                              └→ rejected → closed
```

`PATCH /accidents/{id}/claim` drives it:

* **Transition validity.** Any jump not in the graph is a 409 (e.g. reported →
  settled).
* **Authority.** `approved`/`rejected`/`settled` are management/admin only
  (role-gated in the workflow); data-entry is refused (403).
* **Ceilings.** `approved_amount ≤ claim_amount`; `settlement_amount ≤ approved`
  (or the claim when approval is unset). Both validated through `invariants.money`.
* **Idempotent settlement.** A repeated `settled` is a no-op — the settlement is
  not re-applied, so the payment effect never duplicates.
* **Closed is terminal & locked.** A closed claim cannot transition, and a
  generic `PUT /accidents/{id}` that touches `claim_amount`/`approved_amount`/
  `settlement_amount` on a closed claim is refused (409).
* **No generic bypass.** A generic `PUT` may not set `claim_status` at all — the
  dedicated action is the only path.
* **References.** Accident `vehicle_id`/`driver_id`/`trip_id` are validated
  same-tenant (`references.validate_references`, now covering `trip_id`); a
  cross-tenant reference is a 400.
* **Audit.** Every transition writes `accident.claim` (from/to).

New accident fields: `approved_amount`, `trip_id`, `third_party_involved`,
`police_reference`, `estimated_loss`. Settlement still feeds
`reconciliation.payment_reconciliation` (claim vs settlement outstanding).

## 4. Permissions / frontend

Claim transitions use the existing `accidents:update` permission with in-workflow
role gating for the financial steps — AUTHZ-01 unchanged. The Accident Register
gains contextual claim-action buttons (Collect Evidence → Submit → Survey →
Approve/Reject → Settle → Close), with amount dialogs for approve/settle.

## 5. Verification

`backend/tests/test_compliance_claims.py` — **11 real-HTTP tests**: document
expiry-before-issue refused; supersede preserves history; cross-tenant vehicle
and trip on an accident refused; accident created `reported`; invalid claim
transition refused; full flow with approval/settlement ceilings; double
settlement idempotent; data-entry cannot approve; closed claim locked (dedicated
+ generic); generic claim-status write refused.

| Check | Result |
| --- | --- |
| Full backend suite | **787 passed, 3 skipped** |
| OPS-04 additions | 11 |
| Mutation test | Removing the settlement ceiling fails `test_full_claim_flow_and_ceilings` |
| Ruff (changed files) | F/E clean · Gitleaks clean · Frontend build green |

## 6. Remaining limitations (non-blocking)

* **Mandatory-document blocking on dispatch.** Expired mandatory documents are
  surfaced by the compliance overview and (OPS-05) the exceptions feed; hard
  *blocking* dispatch on an expired document is left as a policy toggle rather
  than enforced unconditionally, to avoid stranding vehicles on a data gap.
* **Document supersede is per (vehicle, doc_type).** Driver-document supersede
  follows the same pattern only where driver documents are modelled as
  `documents`; licence validity remains on the driver record as today.
