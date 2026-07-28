# UX-R1 synchronous export verification

## Inventory and contract

FleetFlow has one synchronous export surface,
`GET /api/reports/{key}/export`, producing Excel or PDF for these 15 report
keys:

`trips`, `fuel`, `services`, `service_due`, `repairs`, `documents`, `expenses`,
`expense_category`, `tyres`, `accidents`, `downtime`, `cost_per_km`,
`fuel_efficiency`, `greasing`, and `greasing_due`.

There are no CSV, background, scheduled, or other synchronous download
implementations in the repository.

Every export runs the same `build_report` function used by its on-screen report.
Applicable filters are:

| Report family | Date range | Vehicle | Driver |
| --- | --- | --- | --- |
| Trips, fuel, accidents | yes | yes | yes |
| Services, repairs, expenses, downtime, greasing | yes | yes | not applicable |
| Expense category, cost/KM, fuel efficiency | yes | yes | not applicable |
| Documents, tyres | not applicable to current report definition | yes | not applicable |
| Service due, greasing due | current-state snapshot | all authorised vehicles | not applicable |

All reads use the tenant-scoped database proxy and the reports module
permission. Anonymous export is rejected. The workbook and PDF contain the full
authorised filtered report result rather than the visible grid page.

## Safety and limits

- Filenames are fixed allowlisted report keys plus `_report.xlsx` or
  `_report.pdf`.
- Workbook sheet titles remove Excel-invalid characters.
- Cells beginning with `=`, `+`, `-`, or `@` are escaped to prevent spreadsheet
  formula execution.
- The PDF uses the neutral `FleetFlow` heading and safe tabular fields.
- Empty results produce a valid workbook with headings and zero data rows.
- Unsupported formats return HTTP 400; the UI reports export failures.
- Synchronous exports have an explicit 5,000-row limit. The Reports page states
  the limit, and every response returns `X-Export-Row-Limit`,
  `X-Export-Row-Count`, and `X-Export-Truncated`; truncation is never silent.

## Automated evidence

Executed 2026-07-28 on real HTTP with a disposable MongoDB database:

- All 15 Excel variants generated and parsed successfully.
- Filtered Trips Excel was parsed and matched the on-screen report row-for-row.
- The filtered result spanned more than one visible page and all rows were
  present.
- The corresponding PDF had a valid PDF signature and identical row-count
  contract.
- Foreign-tenant fixture data was absent.
- Empty, invalid-format, safe filename, safe heading, safe worksheet title, and
  formula-injection cases were covered.

Combined endpoint/export matrix result: `42 passed` in 2.95 seconds.
Production was not accessed.
