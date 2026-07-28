# FleetFlow Performance Evidence

> **UX-R1 recovery note:** authenticated dashboard, vehicle-profile and 10-user
> HTTP measurements remain unmeasured. The direct MongoDB results below are not
> API timings and do not satisfy the UX-R1 release gate.

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

## Unmeasured gates

| Gate | Result |
| --- | --- |
| High-volume API p95 ≤ 750 ms | Not measured (database query p95 ≤ 2 ms only) |
| Vehicle-profile critical API p95 ≤ 1,000 ms | Not measured |
| Dashboard critical API p95 ≤ 1,500 ms | Not measured |
| Authenticated 10-user error rate | Not measured |
| Lighthouse accessibility/performance/CLS | Not measured |
