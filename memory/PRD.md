# PRD — Rajguru Foods Fleet & Vehicle Management System

## Original Problem Statement
Build a centralized Fleet & Vehicle Management System for Rajguru Foods: a complete digital vehicle file and fleet ERP covering vehicle master, document management with expiry alerts, drivers, trips, fuel, maintenance, breakdown/repairs, tyres, accidents, Fastag, downtime, expenses, alerts, dashboards and reports — accessible on web & mobile with role-based access (Driver, Data Entry Operator, Fleet Manager, Management). Currency: INR (₹); distances in KM.

## User Choices
- Auth: REMOVED — role-picker at /login → 4 profiles, X-Role header
  - Driver: create trips/fuel/breakdown reports only
  - Data Entry Operator: create + edit + uploads; no delete
  - Management: data_entry rights + approve repairs + dispose vehicles + exit drivers
  - Admin: full control including delete
- INR + KM; Excel + PDF exports; Fastag simulated sync; multi-photo per vehicle

## Architecture
- **Backend**: FastAPI (port 8001, /api prefix), MongoDB (motor)
  - `auth.py` — role enforcement via X-Role header
  - `routes_core.py` — vehicles, drivers, documents, file storage. Phase 1: driver exit + vehicle disposal management.
  - `routes_ops.py` — trips, fuel, services, repairs (approval workflow)
  - `routes_assets.py` — tyres, tyre-events, accidents, fastag (incl. simulated /sync), downtime, expenses + ledger
  - `routes_analytics.py` — /dashboard, /alerts, /dashboard/trends, /reports (13 reports), exports (Excel/PDF). Phase 1: excludes sold/scrapped vehicles everywhere.
  - `routes_drilldowns.py` (Phase 1, NEW) — 9 dashboard drilldown endpoints under /api/drilldowns/
  - `helpers.py` — generic CRUD factory (`make_crud`) with date_field filtering + vehicle/driver enrichment + `gather_expenses`
- **Frontend**: React + shadcn + Tailwind. Swiss/high-contrast theme, dark slate sidebar.
  - `CrudModule.jsx` (Phase 1: + `readOnly` prop + driver dropdown uses /drivers/active)
  - `PeriodFilter.jsx` (Phase 1, NEW) — 9 presets (All/Today/Yesterday/This Week/Month/Last Month/Quarter/Year/Custom)
  - `DrillDownDialog.jsx` (Phase 1, NEW) — generic drilldown modal with row→navigate
  - Pages: Dashboard (clickable cards + drilldowns), Vehicles (Include Disposed toggle), VehicleProfile (disposal banner + readOnly tabs when sold/scrapped), Drivers, Trips/Fuel/Maintenance/Repairs/Tyres/Fastag/Downtime/Expenses (all gained PeriodFilter in Phase 1), Reports (Print button + @media print stylesheet)

## What's Implemented

### Iteration 1 & 2 (2026-06-11) — MVP — 27/27 tests
All 12 modules + role picker + pagination + driver profile + dashboard trends + photo gallery + simulated Fastag sync.

### Phase 1 (2026-06-15) — 48/48 tests, all flows verified
- **Driver Exit Management** — statuses active/on_leave/resigned/terminated + exit_date + exit_reason. Management/admin RBAC for terminal status. Auto-exit-date. Auto-unassign. Delete blocked if trips/fuel/accidents exist. NEW `GET /api/drivers/active` for form dropdowns.
- **Vehicle Disposal Management** — statuses sold/scrapped + disposal_date + sale_value + buyer_name + buyer_contact + disposal_remarks. Management/admin RBAC. Auto-disposal-date. Auto-close open downtimes. Auto-unassign drivers. Cascade-delete REMOVED. Delete blocked when history exists. `include_disposed` query on /vehicles (default false). Dashboard / alerts / trends EXCLUDE disposed vehicles. Disposal banner + read-only tabs on profile.
- **PeriodFilter Component** — wired into Trips, Fuel, Maintenance, Repairs, Tyres, Fastag, Downtime, Expenses.
- **Clickable Dashboard Widgets** — 9 metric cards + list items open `DrillDownDialog`. New `routes_drilldowns.py` with 9 endpoints (docs_expiring, docs_expired, vehicles_under_repair, service_due, top_fuel_consumers, top_cost_vehicles, low_mileage_vehicles, licenses_expiring, active_trips) — all exclude sold/scrapped vehicles.
- **Print Export** — `Print` button on Reports + `@media print` CSS (hides sidebar/header/buttons/filters, repeats table headers per page, prints in A4 landscape).

## Test Setup
- No auth. Backend: `X-Role` header. Frontend: localStorage `fleet_role`.
- pytest: `/app/backend/tests/test_fleet_backend.py` — 48 tests.
- E2E iteration reports: `/app/test_reports/iteration_1.json`, `iteration_2.json`, `iteration_3.json` (Phase 1).

## Backlog / Next Tasks
- P1: Email/SMS expiry notifications (SendGrid/Twilio) — deferred by user
- P2: Real Fastag API integration when bank API access available
- P2: Charts on vehicle profile; monthly/yearly expense trend filters
- P2: Multi-file attachments per record
- P2: Audit trail of edits
- P2: Vehicle File PDF — single-shot full profile export
