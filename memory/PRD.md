# PRD — Rajguru Foods Fleet & Vehicle Management System

## Original Problem Statement
Build a centralized Fleet & Vehicle Management System for Rajguru Foods: a complete digital vehicle file and fleet ERP covering vehicle master, document management with expiry alerts, drivers, trips, fuel, maintenance, breakdown/repairs, tyres, accidents, Fastag, downtime, expenses, alerts, dashboards and reports — accessible on web & mobile with role-based access (Driver, Data Entry Operator, Fleet Manager, Management). Currency: INR (₹); distances in KM.

## User Choices
- Auth: REMOVED (2026-06-11, user request). Replaced by role-picker screen at /login — 4 profiles with distinct rights, role sent via X-Role header:
  - Driver: create trips/fuel/breakdown reports only; read-only elsewhere; no edit/delete
  - Data Entry Operator: create + edit everything, upload files; no delete
  - Management: data_entry rights + approve major repairs + dashboards/reports
  - Admin: full control incl. delete
- Scope: Build ALL modules in MVP
- File uploads: Yes (Emergent object storage)
- Report export: Excel AND PDF
- INR + KM confirmed
- Fastag auto-retrieval: SIMULATED sync (no public NPCI/bank API) — clearly labeled in UI, swappable for real API later
- Vehicle photos: multiple per vehicle with gallery tab

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

### Iteration 2 (2026-06-11) — tested, 27/27 backend passed
- Auth removed → role-picker (`RoleSelect.jsx`, `permissions.js`, X-Role header in `auth.py`); Users page removed; RBAC enforced backend (make_crud guards) + frontend (button gating)
- Server-side pagination (25/page, `?all=true` for dropdown options) across all list endpoints + CrudModule footer
- Driver profile page `/drivers/:id` (stats + Trips/Fuel/Accidents tabs); driver rows clickable
- Dashboard 6-month trend charts (`/api/dashboard/trends` + recharts: monthly cost bars, KM line)
- Vehicle photo gallery (Photos tab — now 11 tabs on vehicle profile; `photo_file_ids` on vehicle; `VehiclePhotos.jsx`)
- SIMULATED Fastag auto-sync (`POST /api/fastag/sync/{vehicle_id}` — MOCKED demo data generator, labeled in UI)

## Test Setup
- No auth. Backend: `X-Role: driver|data_entry|management|admin` header (missing → admin). Frontend: localStorage `fleet_role`.
- Backend pytest (canonical regression, X-Role model): `/app/backend/tests/test_fleet_backend.py`

## Backlog / Next Tasks
- P1: Email/SMS expiry notifications (user deferred to "later") — needs SendGrid/Twilio keys
- P2: Real Fastag API integration when bank API access is available (replace simulated sync)
- P2: Charts on vehicle profile; monthly/yearly expense trend filters
- P2: Multi-file attachments per record (currently one file per record + multi-photo on vehicles)
- P2: ISO date validation on inputs; audit trail of edits
