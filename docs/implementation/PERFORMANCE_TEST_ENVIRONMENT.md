# Authenticated Performance Test Environment

- Local-only guarded target: `http://127.0.0.1:8201`
- Disposable database naming: `fleetflow_performance_<random hex>`
- Production guard: local HTTP host, safe database prefix and non-production
  `APP_ENV` are all mandatory.
- Runtime: Python 3.11.15, Node 20.20.2, MongoDB 7.0.37.
- Dataset and exact measurements: `PERFORMANCE_EVIDENCE.md`.
- Authentication: synthetic users created with bcrypt hashes; benchmark and
  load use normal `/api/auth/login` and opaque cookies.
- Warm state: three warm-up requests per endpoint, followed by 20 measured
  requests. Cold process startup is excluded and explicitly not represented.
- Load: ten independently authenticated sessions across two organisations; no
  cookie is shared.
- Teardown: drop only the exact generated database. Credentials are generated
  at runtime, excluded from output and never committed.
