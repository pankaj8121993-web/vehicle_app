# Backend Regression Repair

## Failure signature

The mixed full-suite run reported `339 passed, 3 skipped, 97 failed, 15
errors`. Older real-HTTP modules lost authentication and cascaded into 401
responses, while focused runs from `backend/` could pass.

## Root cause

Pytest collection imported application modules before the suite established its
test environment. Two path-dependent effects followed:

1. repository-root invocation did not reliably place `backend/` on `sys.path`;
2. `backend/.env` could enable Secure/SameSite=None cross-site cookies before
   real-HTTP tests configured their local HTTP server. `httpx` correctly refused
   to resend a Secure cookie over plain local HTTP, so subsequent authenticated
   calls became 401s.

This was an import-order and cookie-transport failure, not an authorization-rule
failure. The role browser fixture uses its own process/database and did not leak
into ordinary pytest. The suite-wide unique database continues to be selected
before `database` is imported, so Motor, application objects and HTTP servers
bind to the same disposable database.

## Fix

`backend/tests/conftest.py` now establishes `APP_ENV=test`,
`FLEETFLOW_CROSS_SITE_COOKIES=false`, the backend import path and the unique
suite database before test-module collection can import the application.
Authentication, tenant scoping and permission checks remain fully enabled.

## Why focused tests passed

Running from `backend/` supplied the missing import path, and focused fixture
orders frequently set local-cookie configuration before application import.
The repository-root full suite exercised the opposite import order.

## Regression coverage and evidence

- Real permission/auth HTTP reproduction:
  `test_authz_enforcement.py -x -vv` — `18 passed`.
- Complete suite run 1 after the fix and new fixture tests:
  `871 passed, 3 skipped` in `96.77s`.
- Complete suite run 2: `871 passed, 3 skipped` in `97.58s`.

No tests were skipped, mocked, weakened or marked xfail to obtain this result.
The remaining limitation is that the legacy live-credential module remains
intentionally skipped unless its documented external credentials are supplied.
