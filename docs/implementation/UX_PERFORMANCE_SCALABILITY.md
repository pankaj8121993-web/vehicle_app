# UX-04 — Performance and Scalability

**Starting develop commit:** `288a1385b4d19949496ef1620be03edf73eeb62e`  
**Environment:** local ARM64 container, Node 20.20.2, MongoDB 7.0.8 standalone  
**Production accessed:** No

## Changes

- Added a rerunnable, teardown-capable synthetic generator guarded to databases
  whose explicit `PERF_DB` name contains `perf`.
- Added a guarded critical-endpoint load-test client requiring an authenticated
  non-production cookie and refusing non-local/non-preview/non-staging hosts.
- Added tenant-leading compound indexes for normal vehicle, driver, trip,
  expense, fuel, FASTag, repair, downtime, and document query shapes.
- Added a repeatable direct-query benchmark with execution statistics.
- Lazy-loaded every authenticated route, including the dashboard/chart and
  vehicle-profile graphs. Guest entry routes remain eager.

Index creation is best-effort and non-destructive at normal application startup.
No data is rewritten. The index definitions match the scoped filters and sorts
introduced in UX-03.

## Results

See `PERFORMANCE_EVIDENCE.md` for exact before/after values. In summary:

- Worst representative list p95 improved from 18 ms to 2 ms; most indexed
  queries were 1 ms p95.
- Documents examined fell from collection-scale (up to 40,000) to 25 for a
  25-row page.
- Initial gzip JavaScript fell from 371.17 kB to 217.02 kB (41.53%).
- Frontend tests and production build passed.

## Honest limitations

The direct query benchmark is not an HTTP API benchmark and is labelled
accordingly. Dashboard and vehicle-profile API median/p95, authenticated
10-user load results, query counts, Lighthouse, CLS, and error rate remain
**not measured** because no isolated authenticated application runtime backed by
the generated performance organisation was available. The load script is ready
for that environment. These values are not fabricated and the final release
gate must treat the corresponding performance requirements as unproven.

