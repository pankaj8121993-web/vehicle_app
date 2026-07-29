# Authenticated Ten-User Load Evidence

Date: 29 July 2026. Commit under test: `541c7c36da56de79176d869aa90d449783a6af9a`.

The guarded local runner authenticated ten separate owner accounts (five in
each of two synthetic organisations) through `/api/auth/login`. After warm-up,
the users made 200 requests across dashboard, vehicle list/search/profile,
trips, expenses, exceptions and reports.

| Metric | Result |
| --- | ---: |
| Users / distinct sessions | 10 / 10 |
| Organisations | 2 |
| Measurement duration | 9.30 s |
| Requests / throughput | 200 / 21.50 rps |
| Minimum / median | 3.16 / 182.62 ms |
| p95 / maximum | 1,368.28 / 1,431.94 ms |
| HTTP status | 200 × 200 |
| Errors / timeouts | 0 / 0 |
| Tenant leakage | 0 |
| Session collision | 0 |

Ten explicit cross-tenant profile probes returned tenant-safe 404, while every
own-tenant request succeeded. `/api/auth/me` returned ten distinct identities,
proving the runner did not share a cookie. Failed requests are included in the
calculation (there were none).
