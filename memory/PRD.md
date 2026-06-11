# PRD — Rajguru Foods Fleet & Vehicle Management System

## Original Problem Statement
Build a centralized Fleet & Vehicle Management System for Rajguru Foods: a complete digital vehicle file and fleet ERP covering vehicle master, document management with expiry alerts, drivers, trips, fuel, maintenance, breakdown/repairs, tyres, accidents, Fastag, downtime, expenses, alerts, dashboards and reports — accessible on web & mobile with role-based access (Driver, Data Entry Operator, Fleet Manager, Management). Currency: INR (₹); distances in KM.

## User Choices
- Auth: Emergent-managed Google login (first user → management role; later users → driver; management changes roles via /users)
- Scope: Build ALL modules in MVP
- File uploads: Yes (Emergent object storage)
- Report export: Excel AND PDF
- INR + KM confirmed

## Architecture
- **Backend**: FastAPI (port 8001, /api prefix), MongoDB (motor), modular routers:
  - `auth.py` — Emergent OAuth session exchange, cookie+Bearer auth, RBAC deps, user/role mgmt (last-management lockout guard)
  - `routes_core.py` — vehicles (+/summary), drivers (+/stats), documents, file upload/download (Emergent object storage)
  - `routes_ops.py` — trips (auto distance, close-trip flow), fuel (auto mileage & cost/km), services, repairs (minor direct; major workflow reported→approved→in_repair→completed, sequential transitions enforced; approve = fleet_manager/management only)
  - `routes_assets.py` — tyres, tyre-events (replacement marks tyre removed), accidents, fastag (recharge/toll auto-adjusts vehicle balance), downtime (auto days), expenses + `/expenses/ledger` (unified aggregation across all modules)
  - `routes_analytics.py` — `/dashboard`, `/alerts`, `/reports` (13 report types), `/reports/{key}/export?format=excel|pdf` (openpyxl/reportlab)
  - `helpers.py` — generic CRUD factory (`make_crud`) with vehicle/driver enrichment + `gather_expenses`
  - Cascade-delete of dependent records on vehicle delete; orphan-safe alerts
- **Frontend**: React + shadcn + Tailwind. Swiss/high-contrast light theme (Chivo + IBM Plex Sans/Mono), dark slate sidebar, sharp corners.
  - Generic `CrudModule.jsx` (config-driven tables + sheet forms + edit/delete + file upload fields) powered by `lib/configs.js`
  - Pages: Dashboard (metrics + alerts panel), Vehicles → VehicleProfile (12 stat cards + 10 tabs), Drivers, Documents, Trips (close-trip dialog), Fuel, Maintenance, Repairs (workflow buttons), Tyres+Events, Accidents, Fastag, Downtime, Expenses (ledger + manual), Reports (filters + Excel/PDF export), Users & Roles, Login (Google OAuth split-screen)

## What's Implemented (2026-06-11)
All modules above, tested end-to-end (testing agent iteration_1: backend 27/27 passed; frontend ~95%, all flows functional). Fixes applied post-test: orphaned alert filtering, vehicle cascade delete, last-management demotion guard, sequential repair transitions, tab testid alignment.

## Test Setup
- Test session: see `/app/memory/test_credentials.md` and `/app/auth_testing.md`
- Backend pytest: `/app/backend/tests/test_fleet_backend.py`

## Backlog / Next Tasks
- P1: Pagination for large datasets (lists capped at 3000); GET /vehicles/{id} endpoint; driver profile page using existing /drivers/{id}/stats
- P1: Alerts for missing fuel/trip entries and pending invoice uploads (spec §16, partially covered)
- P2: Charts on dashboard (recharts is installed); monthly/yearly expense trend graphs
- P2: Notifications (email/SMS) for expiring documents
- P2: Multi-file attachments per record (currently one file per record)
- P2: ISO date validation on inputs; audit trail of edits
