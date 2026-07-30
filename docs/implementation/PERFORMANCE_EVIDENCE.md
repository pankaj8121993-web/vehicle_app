# FleetFlow Performance Evidence

> **UX-R1 authenticated rerun:** the real HTTP and ten-user gates below supersede
> the earlier database-only caveat.

**Date:** 28 July 2026  
**Database:** local isolated `fleetflow_performance` (never production)  
**Runs per query:** 30; page size 25; warm local MongoDB  
**Dataset:** 2 organisations; 500 vehicles; 500 drivers; 20,000 trips; 40,000
expenses; 20,000 fuel entries; 20,000 FASTag transactions; 2,500 repairs; 2,500
downtimes; 5,000 documents.

## Database list-query measurements

| Query | Before median/p95/max ms | Before docs | After median/p95/max ms | After docs | After stage |
| --- | ---: | ---: | ---: | ---: | --- |
| Vehicles active | 1 / 2 / 8 | 500 | 1 / 2 / 3 | 25 | FETCH via index |
| Trips completed/date | 9 / 10 / 10 | 20,000 | 1 / 1 / 2 | 25 | FETCH via index |
| Expenses submitted/date | 17 / 18 / 28 | 40,000 | 1 / 1 / 1 | 25 | FETCH via index |
| Fuel/date | 8 / 9 / 9 | 20,000 | 1 / 1 / 1 | 25 | FETCH via index |
| FASTag/date | 8 / 9 / 9 | 20,000 | 1 / 1 / 2 | 25 | FETCH via index |
| Repairs open/date | 2 / 2 / 2 | 2,500 | 1 / 1 / 1 | 25 | FETCH via index |
| Downtime open/start | 2 / 2 / 3 | 2,500 | 1 / 1 / 1 | 25 | FETCH via index |
| Documents/expiry | 3 / 3 / 4 | 5,000 | 1 / 1 / 2 | 25 | FETCH via index |

Before plans were `COLLSCAN`; after plans used the new compound indexes. These
numbers measure database execution on this machine, not network/API latency.

## Frontend bundle

| Build | Initial JS gzip | Change |
| --- | ---: | ---: |
| UX-03 baseline | 371.17 kB | — |
| UX-04 route splitting | 217.02 kB | -154.15 kB (-41.53%) |

Largest asynchronous chunk is 104.53 kB gzip; authenticated page chunks range
from 386 bytes to 11.06 kB gzip. The initial bundle is below 500 kB and the
reduction exceeds the conditional 20% target.

## Commands

```text
PERF_DB=fleetflow_performance mongosh mongodb://127.0.0.1:27017/fleetflow_performance scripts/performance_seed.js
PERF_DB=fleetflow_performance mongosh mongodb://127.0.0.1:27017/fleetflow_performance scripts/performance_benchmark.js
PERF_DB=fleetflow_performance PERF_INSTALL_INDEXES=true mongosh mongodb://127.0.0.1:27017/fleetflow_performance scripts/performance_benchmark.js
PERF_DB=fleetflow_performance PERF_TEARDOWN=true mongosh mongodb://127.0.0.1:27017/fleetflow_performance scripts/performance_seed.js
```

## Authenticated real-HTTP measurements — 29 July 2026

Commit `541c7c36da56de79176d869aa90d449783a6af9a`; local MongoDB 7.0.37;
Python 3.11.15. The guarded database was
`fleetflow_performance_70c8c53ef604`, with two synthetic organisations, 500
vehicles, 500 drivers, 20,000 trips, 80,000 expenses/payments/advances, 20,000
fuel records, 20,000 FASTag records, 5,000 repairs/downtimes and 5,000
documents. Each endpoint used a real owner login/cookie, three warm-ups and 20
measured warm requests.

| Endpoint | Median ms | p95 ms | Max ms | Errors | Median bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dashboard | 49.1 | 51.72 | 54.0 | 0 | 849 |
| Vehicles / search | 2.8 / 2.8 | 3.24 / 3.01 | 3.4 / 3.2 | 0 | 4,867 / 256 |
| Vehicle summary / statistics | 83.7 / 144.8 | 85.72 / 148.00 | 87.2 / 149.3 | 0 | 510 / 2,042 |
| Drivers | 3.6 | 4.36 | 4.5 | 0 | 4,218 |
| Trips / search | 24.5 / 34.6 | 24.85 / 35.19 | 25.2 / 35.4 | 0 | 8,762 / 405 |
| Expenses / search | 43.9 / 58.3 | 44.61 / 59.39 | 45.0 / 60.1 | 0 | 5,748 / 5,923 |
| Fuel / FASTag / repairs | 13.8 / 14.8 / 7.0 | 14.29 / 15.23 / 7.59 | 14.6 / 15.5 / 7.8 | 0 | 5,122 / 6,063 / 6,485 |
| Exceptions / reports | 495 / 0.9 | 516.64 / 0.96 | 526 / 1.2 | 0 | 6,221,362 / 811 |

The exceptions response is deliberately derived from all unresolved canonical
records and is large under this worst-case synthetic state; it remains under
the 750 ms gate but is the primary payload-size follow-up.

## Ten-user authenticated load

Ten distinct real sessions (five users in each organisation) made 200 requests
across the critical endpoint mix: 9.30 seconds, 21.50 requests/second, 182.62 ms
median, 1,368.28 ms p95, 1,431.94 ms maximum, `200: 200`, zero errors/timeouts.
All ten cross-tenant vehicle probes returned the intended tenant-safe 404 and
all `/auth/me` identities remained distinct: zero leakage and zero collision.

## Gates

| Gate | Result |
| --- | --- |
| High-volume API p95 ≤ 750 ms | PASS (worst 516.64 ms) |
| Vehicle-profile critical API p95 ≤ 1,000 ms | PASS (148.00 ms) |
| Dashboard critical API p95 ≤ 1,500 ms | PASS (51.72 ms) |
| Authenticated 10-user error rate | PASS (0/200) |
| Lighthouse accessibility/performance/CLS | Measured — see [LIGHTHOUSE_EVIDENCE.md](LIGHTHOUSE_EVIDENCE.md). Accessibility 100 (all pages), desktop perf 91–96, CLS ≤ 0.006 (representative config): PASS. Mobile perf partial (vehicle list 71 pass; login/vehicle-profile/dashboard completed in UX-05). |
