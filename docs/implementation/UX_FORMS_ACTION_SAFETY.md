# UX-02 — Forms, Validation and Action Safety

**Starting develop commit:** `59e06d21bc5844844a89eeab742859e0b9c1f28f`  
**Production accessed:** No

## Inventory and shared contract

The repository's principal create/edit surface is `CrudModule`, configured for
vehicles, drivers, trips, expenses, fuel, FASTag, repairs, tyres, downtime,
accidents, documents, services, greasing, and vendor-backed fields. Organisation,
user, calendar, ticket workflow, and onboarding forms remain page-specific.

The shared CRUD surface now provides:

- field-associated required, numeric, positive-quantity, non-negative, date
  ordering, and odometer-order validation;
- native form submission for predictable Enter behaviour;
- accessible labels, invalid state, descriptions, inline field messages, and a
  form-level error summary;
- synchronous duplicate-submit locking in addition to disabled submit controls;
- retained input and an open form after backend/network failure;
- safe explanations for 403, 409, 422, offline, and unexpected failures;
- unsaved-change protection on form close, in-app link navigation, and browser
  unload, disabled after a successful save;
- record-specific destructive confirmation;
- retained destructive dialog after failure and duplicate-delete protection.

Backend validation, permissions, tenant reference checks, workflow state
machines, and idempotency remain authoritative and unchanged.

## Validation mapping

| Rule | Client behaviour | Backend authority |
| --- | --- | --- |
| Required fields | Inline field error | Pydantic/domain validation |
| Quantity/litres | Must be greater than zero | DI invariants |
| Monetary/numeric/odometer | Must be finite and non-negative | DI invariants |
| Issue/expiry, start/end, purchase/disposal | End cannot precede start | Domain validation |
| Closing/opening kilometre | Closing cannot be lower | Trip invariants |
| Same-tenant references | Only server-returned options; 403/422 handled | Tenant policy |
| Duplicate identifiers | 409 explained without clearing form | Unique indexes/invariants |
| Workflow actions | Existing server-authorised actions only | Workflow state machines |

## Destructive action wording

The generic delete dialog identifies the record using its operational label
(vehicle number, name, title, employee/document number, then ID) and states that
removal is permanent. Existing cancel, close, scrap, reject, settlement, and
ticket terminal actions retain their domain dialogs; broad replacement is not
performed where doing so could alter workflow semantics.

## Evidence

- Form-safety unit tests cover required fields, positive/non-negative values,
  date ordering, odometer ordering, 403/409/422 mapping, exception redaction, and
  destructive record identity.
- Existing UX-01 route suite remains part of `npm run test:ci`.
- Production build and Playwright route smoke are rerun for regression.

## Known limitation

React Router 7 with the current `BrowserRouter` does not expose a stable
data-router blocker hook. In-app link navigation is protected with a scoped
capture handler while a meaningful shared CRUD form is dirty; browser
back/forward navigation receives the standard browser unload warning. A future
router migration should replace this compatibility layer with the router's
native blocker.

