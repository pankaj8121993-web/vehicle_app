# Backend test isolation

**Workstream:** UX-R1  
**MongoDB:** 7.0.37 local disposable service  
**Production accessed:** No

## Root cause

The complete suite used the constant database `fleetflow_automated_tests`.
Real-HTTP modules drop and reseed that shared name. Interrupted, concurrent or
overlapping runs could therefore inherit or destroy one another's state. Motor
also binds operations to an event loop; the suite created a shared loop but did
not install it as the process default before application imports.

## Resolution

- Every pytest process now receives
  `fleetflow_automated_tests_<random-run-id>`.
- `FLEETFLOW_TEST_RUN_ID` permits a deterministic CI name when required.
- A session fixture drops the run database before and after execution.
- The shared Motor loop is installed before importing application modules.
- pytest-xdist execution fails closed; database-backed modules remain serial.
- Tenant context is reset during teardown.
- Regression tests cover the explicit disposable name, interrupted-state
  cleanup, context reset and parallel-execution guard.
- File HTTP tests use a deterministic in-process object-store adapter while
  retaining real MongoDB metadata, authentication and tenant scoping. No
  external or production storage is contacted.

The suite continues to use real MongoDB operations and real ASGI HTTP routes;
meaningful database calls were not mocked. Demo and UAT fixtures share only the
current isolated process database and retain module-level drop/reseed boundaries.
Index creation remains idempotent through MongoDB `create_index`.

Run:

```bash
MONGO_URL=mongodb://127.0.0.1:27017 \
JWT_SECRET=phase3-test-secret \
CORS_ORIGINS=http://127.0.0.1:3000 \
PYTHONPATH=backend \
python -m pytest backend/tests -q
```

First complete green run: **827 passed, 3 skipped in 103.97 seconds**.
Second consecutive green run: **827 passed, 3 skipped in 92.59 seconds**.
