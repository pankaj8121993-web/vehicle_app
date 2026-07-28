# UX-03 — Search, Filters, Grids and Exports

**Starting develop commit:** `33a4b178a37f7273e1ba430f810a996887636fc4`  
**Production accessed:** No

## Migrated query contract

The high-volume generic CRUD endpoints (trips, expenses, fuel, FASTag, repairs,
tyres, downtime, accidents/claims, documents and related operational registers)
plus vehicles, drivers, and vendors accept:

| Parameter | Contract |
| --- | --- |
| `search` | Escaped, case-insensitive substring across an allowlisted domain field set; max 100 input characters |
| `page` | One-based; invalid values safely fall back to 1 |
| `page_size` | 1–200; UI choices are 25, 50, 100 |
| `sort_by` | Per-endpoint allowlist only |
| `sort_dir` | `asc` or `desc` |
| Domain filters | Existing status, date, vehicle, driver, tyre, category and document filters remain compatible |

The paginated response is:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 25,
  "total_pages": 0
}
```

Legacy `all=true` option-picker responses remain arrays for compatibility. They
are not used by operational grids. This workstream does not silently convert
those lookups into a breaking response shape.

## Tenant and permission safety

Search clauses are added to the existing scoped query and never replace its
status, test-data, or tenant filters. Database access continues through the
tenant-scoped database proxy and endpoint permission/module dependencies.
Regex metacharacters are escaped; arbitrary regex and arbitrary sort fields are
not accepted.

## Frontend grid behaviour

- Search is debounced by 300 ms and sent to the server; it no longer filters
  only the current 25-row page.
- A new search resets to page one and stale debounce timers are cancelled.
- Sorting is sent to the server and exposed with `aria-sort` and a visible
  direction indicator.
- Result ranges use the server total; page boundaries and page size are explicit.
- Empty datasets and no-search-results use different copy.
- Existing status/date domain filters remain visible in their page controls and
  feed the same server request.
- Detail routes continue preserving URL filter context from UX-01.

## Exports

Existing report Excel/PDF exports already call the server with the same report
date, vehicle and driver parameters used for report generation. Export data is
generated from the filtered server query, not the visible grid page, and remains
tenant/permission scoped. No scheduled or asynchronous export platform was
introduced.

## Evidence

Pure backend contract tests cover regex escaping, filter preservation, invalid
pagination, page boundaries, total pages, and sort allowlisting. Frontend unit,
build, and Playwright regression commands are rerun. Full database-backed suite
execution remains subject to the repository requirements resolver limitation
recorded in the baseline.

