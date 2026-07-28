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
