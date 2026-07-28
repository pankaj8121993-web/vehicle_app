# FleetFlow Core UX and Performance Baseline

**Roadmap:** Original Phase 3 — Core UX and Performance  
**Starting `develop`:** `09050bf19cfabb2bfd464841b68f318b134a00f6`  
**Recorded:** 28 July 2026 (isolated local worktree; production not accessed)

## Validation baseline

| Check | Result |
| --- | --- |
| Latest recorded backend suite | 814 passed, 3 skipped in the merged UAT release gate |
| Backend rerun in this environment | Not run: the pinned `requirements.txt` resolver reports a `litellm==1.80.0` / `emergentintegrations==0.2.0` conflict |
| Frontend test capability at start | No test files, setup file, E2E configuration, or test-specific scripts |
| Frontend production build after dependency bootstrap | Pass |
| Initial production bundle | 1,289,364 bytes JavaScript raw; 369.39 kB gzip; CSS 77,353 bytes raw / 13.56 kB gzip |
| Existing CI | Secret-scan workflow only |

The backend count above is historical merged evidence, not a new execution. No
backend performance service or synthetic large dataset was available at
baseline, so dashboard and vehicle-profile median/p95 timings are **not
measured**. UX-04 must establish them; this document does not fabricate values.

## Route inventory summary

The application defines four guest/public entry routes, 26 authenticated routes
(including two detail routes and permission-denied), and a fallback. The detailed
route matrix is in `UX_NAVIGATION_GUARDS_STATES.md`.

## Baseline findings

| Area | Observed baseline |
| --- | --- |
| Authentication | `ProtectedRoute` waits for hydration. A 401 interceptor redirected every anonymous path except `/`, `/login`, `/demo`, and `/register`; `/get-started` was omitted. |
| Permission denial | Restricted users were silently redirected to dashboard, making access denial indistinguishable from navigation failure. |
| Broken route | Unknown URLs silently redirected to `/`, losing the requested address and giving no explanation. |
| Detail return | Vehicle and driver profile back buttons returned to an unfiltered list and discarded URL query context. |
| Navigation visibility | Sidebar modules are filtered using server-provided modules; administration entries are additionally role-tier filtered. |
| Page states | Loading/empty/error rendering is implemented independently by pages; no reusable page-level state contract existed. Several pages rely only on toast errors. |
| Lists | `CrudModule` fetches configured endpoints and applies filters client-side to the returned collection; no shared pagination response contract exists. This requires endpoint-by-endpoint reproduction in UX-03 before classification as truncation. |
| Exports | Reports expose synchronous CSV/PDF actions; filter parity and whole-result behaviour require UX-03 verification. |
| Mobile | Layout provides a sheet navigation below `lg`; desktop grids remain the principal list presentation. Automated 360 px overflow evidence did not exist. |
| Accessibility | Radix primitives provide a foundation, but the auth splash lacked an announced status and no automated accessibility harness existed. |

## Defect register

Only repeatable or test-backed findings are classified here.

| ID | Severity | Finding | Evidence |
| --- | --- | --- | --- |
| UX-B01 | P1 | `/get-started` could be redirected to login when anonymous `/auth/me` returned 401 | Interceptor route-set contract plus anonymous public-route E2E coverage |
| UX-B02 | P1 | Permission restrictions silently redirected to dashboard | Route test demonstrates explicit denial is required |
| UX-B03 | P2 | Unknown route silently redirected to landing | Route fallback test |
| UX-B04 | P2 | Vehicle/driver URL filter context was discarded on profile return | Representative row/back navigation implementation and tests pending browser run |
| UX-B05 | P2 | No frontend automated harness or CI quality command | Repository inventory |

No P0 defect was reproduced during baseline preparation.

