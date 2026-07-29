# UX-R1 high-risk domain-form regression evidence

## Coverage

The domain action inventory is exercised by the real-HTTP suites below. These
tests use disposable MongoDB data, real permissions, same-tenant references and
the production workflow state machines:

| Domain actions | Primary automated evidence |
| --- | --- |
| Trip planning, assignment, reassignment, dispatch, completion, settlement | `test_trip_operations.py`, `test_expense_settlement.py` |
| Expense submission, approval, rejection, payment, reversal | `test_expense_settlement.py` |
| Advance creation and recovery | `test_expense_settlement.py` |
| Repair transition and approval, downtime closure, tyre transfer/scrap | `test_maintenance_operations.py` |
| Accident reporting; claim progression, approval, rejection, settlement | `test_compliance_claims.py` |
| Document upload | `test_file_security.py`, `test_compliance_claims.py` |
| User administration and organisation settings | `test_authz_enforcement.py`, `test_bootstrap.py`, `test_fleet_backend.py` |

The suites cover required and numeric fields, date/odometer ordering,
same-tenant references, permissions, invalid transitions, conflicts,
idempotency, and safe 4xx responses without weakening backend rules.

## Frontend and browser evidence

`DomainActions.test.jsx` adds focused interaction coverage for the actual Trip
and Expense workflow components:

- closing odometer ordering;
- retained values and open dialogs after 403/422-style failure;
- disabled state and duplicate-click suppression while pending;
- successful-close behavior;
- approval and payment numeric boundaries.

`domain-actions.spec.js` uses the real role fixture and cookie sessions to
complete a seeded trip and approve a seeded expense in Chromium. It verifies
keyboard-fillable labelled controls, record-specific actions, pending disabled
state, retained invalid values, real workflow persistence, and no uncaught
browser error.

Shared CRUD tests continue to cover required fields, 403/409/422 explanations,
retention after failure, unsaved-change warnings, dialog focus behavior from
Radix primitives, record-specific destructive confirmation, and clearing the
warning after success. Ticket, downtime, tyre and claim components retain their
dialogs on failure and only close after successful API completion.
