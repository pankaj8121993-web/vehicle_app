# Original Phase 3 resume audit

**Resume starting commit:** `250f05d2a4e0251fcc934d1a3083cfa469c22d73`  
**Audited PRs:** #27, #28, #29, #30  
**Production accessed:** No

Statuses reflect code and newly runnable evidence, not merged documentation
alone.

| Requirement | Status | Evidence / gap |
| --- | --- | --- |
| Routes and guards | Implemented but not fully verified | Explicit public, guest, protected, denied and not-found guards; 9 route tests, but role-backed browser matrix absent |
| Page states | Implemented but not fully verified | Shared loading/error/empty states; incomplete route-wide browser evidence |
| Forms and validation | Partially implemented | Shared CRUD hardened; domain-specific high-risk forms not exhaustively covered |
| Duplicate-submit protection | Implemented but not fully verified | Shared synchronous lock and tests; domain audit incomplete |
| Unsaved-change protection | Implemented but not fully verified | Shared CRUD coverage; domain-specific coverage incomplete |
| Destructive actions | Partially implemented | Shared confirmation improved; domain workflows require browser verification |
| Search, sorting, pagination, totals | Implemented and verified | 25-test real-HTTP/disposable-Mongo endpoint matrix covers all applicable registers |
| Search beyond page one | Implemented and verified | 23-row endpoint fixtures prove server search finds a naturally deep-page record |
| Filters and return persistence | Implemented and verified | Status/date/domain/combined filters plus frontend filter/sort request persistence covered |
| Export-filter parity | Not implemented | Existing exports have not been proven across all active filters |
| Mobile grid behaviour | Not implemented | UX-05 not started |
| Dashboard performance | Not implemented | API median/p95 unmeasured |
| Vehicle-profile performance | Not implemented | API median/p95 unmeasured |
| Large-list performance | Implemented but not fully verified | Direct MongoDB benchmarks only; authenticated API load absent |
| Bundle size | Implemented and verified | UX-04 route splitting reduced initial gzip JS to 217.02 kB |
| Role-backed E2E | Implemented and verified | Eight desktop roles, four mobile roles and three Firefox roles use real logins/cookies and disposable MongoDB |
| Frontend component testing | Partially implemented | Grid behavior expanded; high-risk domain-form regression remains |
| Accessibility testing | Not implemented | No axe harness; UX-05 scope |
| Visual regression | Not implemented | No screenshot baseline |
| CI | Partially implemented | Recovery adds backend/frontend quality workflow; axe awaits UX-05 |

## PR file verification

PR #27 changed routing/auth/page-state files and added the initial React and
Playwright harness. PR #28 changed shared CRUD safety utilities only. PR #29
changed the shared list-query contract and CrudModule. PR #30 added indexes,
synthetic benchmark/load scripts and route splitting. Their actual changed-file
lists match these scopes and do not substantiate the missing evidence above.

UX-R1 remains in progress until the complete backend, endpoint matrix,
authenticated performance, Lighthouse and role-backed E2E gates are green.
