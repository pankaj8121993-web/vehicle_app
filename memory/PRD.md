# PRD — Rajguru Foods Fleet & Vehicle Management System

## Original problem statement
A centralized Fleet & Vehicle Management System to serve as a complete digital
repository and operational management platform for all company vehicles.
Accessible through web and mobile devices. Role-based access for admin,
management, data-entry, driver, and test-sandbox users. Complete life-cycle
tracking: vehicles, drivers, trips, fuel, maintenance, greasing, tickets,
tyres, accidents, downtime, expenses, compliance, calendar, fleet status,
statistics, vendors, global search, PWA install.

## Core users & personas
- **Admin (`admin`)** — full access, user management, purge test data.
- **Management (`management`)** — approvals (ticket approve/close/reject), all
  reports & dashboards.
- **Data entry (`data_entry`)** — creates most operational records; cannot
  approve/close tickets.
- **Driver (`driver`)** — mobile home screen with 8 quick actions; can log
  trips, fuel, breakdowns, accidents, expenses.
- **Test (`test`)** — sandbox role; every record is stamped `is_test_data`.

## Delivered features (Feb 2026)
### Phase 1
- Vehicle disposal (sold/scrapped) with banner + read-only lock.
- Driver exit flow.
- Dashboard clickable drilldowns, period filters, print/export.

### Checkpoint 1
- Greasing module + phase-1.5 patches, driver enrichment.

### Checkpoint 2 — Real authentication
- JWT bearer tokens, forced-password-change on first login.
- User Management page (admin only), TestDataAdmin page.
- `test` role sandbox tagging + admin `?include_test=true` opt-in.

### Commit A (Checkpoint 3 + E1 + E2)
- Compliance dashboard with contacts directory.
- Fleet Calendar (recurring events).
- Fleet Status Board.
- Per-vehicle Statistics tab (lifetime + trend charts).

### Commit B (Checkpoint 4 + E3 + Checkpoint 5) — **This session**
- **CP4 Service Tickets** — 7-stage workflow
  `Open → Under Review → Approved → Sent for Repair → In Repair → Repaired → Closed`
  with auto TKT-YYYY-NNNN numbering, timeline UI, per-stage timestamps + actor
  attribution, photo uploads (max 8), reject-back-to-open with reason, RBAC
  gates (Approve/Close/Reject → management+), backfill migration on startup.
- **E3 Vendor Master** — dedicated CRUD (`vendors`), 8 vendor types, active
  flag, GST/mobile/email/address. "Pick from saved vendors" dropdown in
  service and repair forms auto-fills the free-text vendor field.
- **CP5 Global Search** — `/api/search?q=` across vehicles/drivers/tickets/
  documents; debounced 300 ms, grouped dropdown, keyboard navigation, recent
  searches (localStorage, 5 entries), test-data & disposed records excluded.
- **CP5 PWA** — manifest, service worker (never caches `/api/*`), placeholder
  icons (192/512 PNG), `beforeinstallprompt` capture, dismissible install
  prompt with 30-day cooldown, worker registration in `index.js`.
- **CP5 Driver Mobile Home** — 8 quick-action tiles (`/` for `role=driver`):
  Start Trip, End Trip (contextual disabled), Add Fuel, Report Breakdown,
  Report Accident, Upload Invoice, View Documents, Call Fleet Manager (env
  `REACT_APP_FLEET_MANAGER_PHONE`; disabled when unset).

## Test posture
- Backend: **94/94 pytest cases** passing (`/app/backend/tests/`).
  Added `TestVendors` (4), `TestTicketWorkflow` (6), `TestGlobalSearch` (4).
- Session-scoped `conftest.py` restores default seeded passwords after every
  pytest run so manual UI login continues to work.
- Frontend: `testing_agent_v3_fork` regression pass 4 → ~98%.
  1 minor UI nit auto-fixed: TicketDetail drawer subtitle vehicle_number
  preservation across PATCH updates.

## Architecture
```
/app/
├── backend/
│   ├── auth.py, database.py, helpers.py, models.py
│   ├── routes_analytics.py, routes_assets.py, routes_calendar.py,
│   │   routes_compliance.py, routes_core.py, routes_drilldowns.py,
│   │   routes_fleet_status.py, routes_ops.py, routes_search.py,
│   │   routes_vendors.py
│   ├── server.py         # startup: user seed + ticket migrations
│   └── tests/
│       ├── conftest.py   # session-teardown restores seeded passwords
│       └── test_fleet_backend.py  (94 tests)
└── frontend/
    ├── public/
    │   ├── manifest.json, service-worker.js
    │   └── icon-192.png, icon-512.png
    └── src/
        ├── App.js  (HomeRoute: Dashboard vs DriverHome)
        ├── components/
        │   ├── CrudModule.jsx  (vendor_picker + boolean field types)
        │   ├── GlobalSearch.jsx
        │   ├── InstallPrompt.jsx
        │   ├── Layout.jsx  (Vendors nav + GlobalSearch in header)
        │   └── TicketDetail.jsx
        ├── lib/configs.js  (vendorConfig, TICKET_CATEGORIES, VENDOR_TYPES)
        └── pages/
            ├── DriverHome.jsx
            ├── Vendors.jsx
            └── … existing pages
```

## API surface (highlights)
- Auth: `/api/auth/login`, `/auth/me`, `/auth/change-password`
- Users: `/api/users`, `/api/admin/purge-test-data`
- Vehicles / drivers / documents / trips / fuel / services / greasings /
  tyres / tyre_events / accidents / fastag / downtime / expenses.
- Tickets: `POST/PUT/DELETE /api/repairs`, `PATCH /api/repairs/{id}/status`
- Vendors: `GET/POST/PUT/DELETE /api/vendors`
- Search: `GET /api/search?q=`
- Analytics: `/api/dashboard`, `/api/dashboard/trends`, `/api/reports/*`
- Compliance: `/api/compliance`, `/api/compliance-contacts`
- Calendar: `/api/calendar`
- Fleet status: `/api/fleet-status`
- Statistics: `/api/vehicles/{id}/statistics`

## Backlog (P1 / polish tier — not in scope of Commit B)
- Notifications: email/SMS for compliance expiries + ticket state changes.
- Server-side pagination for global search when result sets grow.
- Real hi-res "RF" icon set from a designer.
- Deeper offline support (currently: app-shell only; forms are online-only).
- Driver ↔ user_id linkage on `drivers` collection (currently name-match).

## Seeded users (post-conftest teardown)
Refer to `/app/memory/test_credentials.md`.
