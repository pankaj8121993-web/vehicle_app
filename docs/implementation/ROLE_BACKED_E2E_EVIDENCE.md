# UX-R1 role-backed E2E evidence

The matrix uses `scripts/role_e2e_fixture.py` to create a uniquely named,
disposable MongoDB database and eight synthetic non-demo users. A random
password is generated for each run, written only to a mode-0600 ignored state
file, and removed with the database during global teardown. Production
environments, suspicious database names, and non-local MongoDB hosts are
rejected.

No `/auth/me` response is mocked. Every scenario logs in through
`POST /api/auth/login`, validates the real cookie-backed `GET /api/auth/me`
identity, actual role, organisation and permitted modules, exercises permitted
UI routes and a real read, proves a cross-tenant or unauthorised mutation is
refused, reloads, logs out, rejects replay of the old session, and logs in
again. Browser exceptions and unexpected API 5xx responses fail the test.

Required execution:

```bash
FLEETFLOW_ROLE_E2E_RUN_ID="$(openssl rand -hex 6)" \
  npm --prefix frontend run test:e2e -- frontend/e2e/role-matrix.spec.js
```

Chromium desktop covers all eight roles. Mobile Chromium covers `org_admin`,
`operations`, `driver`, and `viewer`. Firefox covers `org_admin`, `driver`, and
`viewer`.

The mobile project retains the Pixel 5 mobile user agent, touch capability,
mobile layout and device scale factor, but overrides both browser viewport and
screen to the required exact **360 × 800** dimensions.

## Execution evidence

Executed 2026-07-28 against the isolated local backend and MongoDB:

| Profile | Required roles | Result |
| --- | --- | --- |
| Chromium desktop | all eight roles | 8 passed |
| Mobile Chromium | org_admin, operations, driver, viewer | 4 passed |
| Firefox desktop | org_admin, driver, viewer | 3 passed |

The combined mobile/additional-browser run reported `7 passed, 9 skipped`;
skips are the roles deliberately outside those profile requirements. The
production build was used for browser execution. No production service or
database was accessed.

The run exposed and fixed two real browser defects: the shared record-label
helper dereferenced a null delete target on domain pages, and Fleet Status left
a rejected in-flight request unhandled during logout/navigation. Both now fail
safe without uncaught browser errors.
## Acceptance completion — 2026-07-29

- The mobile project uses a measured browser viewport and screen of exactly
  `360 × 800`, while retaining the Pixel 5 mobile user agent, touch, mobile
  layout and device scale factor.
- The guarded fixture creates two organisations, all eight Organisation A roles,
  a second-tenant administrator, and own/foreign records for vehicles, drivers,
  trips, expenses, fuel, FASTag, repairs, tyres, downtime, documents, accidents
  (including claim lifecycle), vendors, exceptions and users.
- The fixture requires `FLEETFLOW_ROLE_E2E_ALLOW=true`, rejects unsafe database
  names, production mode, and non-local MongoDB hosts. It never prints its
  generated password or password hashes.
- Dedicated fixture tests passed: `2 passed` (unique naming, all guard cases,
  hashed credentials, two tenants, representative records, interrupted rerun,
  teardown and secret-free output).
- Browser rerun: Chromium desktop 8/8, exact-mobile Chromium 4/4, Firefox 3/3;
  combined result `15 passed, 9 intentionally skipped` in 1.2 minutes.
