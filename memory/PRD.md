# PRD — FleetFlow (Complete Fleet Operations Management)

## Original problem statement
Originally: Rajguru Foods Fleet & Vehicle Management System — a centralized fleet
repository and operations platform. **June 2026 directive:** transform the app into
**FleetFlow**, a premium multi-company fleet-management SaaS:
- Tagline: "Every Vehicle. Every Journey. Completely Under Control."
- Complete rebranding, public landing page, organisation onboarding wizard,
  isolated demo environment, backend-enforced multi-tenancy, Expense Intelligence
  module, search/filters/tabs everywhere, role dashboards, premium UI/UX.

## Architecture (July 2026)
```
/app/backend/
├── database.py        # TenantDB proxy — org_id auto-injected per request (contextvar)
├── auth.py            # 12 roles → 6 enforcement tiers (ROLE_EQUIV), create_session,
│                      #   login/me return org_id/org_name/is_demo, demo-user guards
├── routes_orgs.py     # onboarding/register, /org, /branches, checklist, /demo/enter
├── routes_expenses.py # /expenses/overview, /expenses/insights, /budgets CRUD+status
├── demo_seed.py       # demo org (org-fleetflow-demo) — 6 vehicles, 90d trips/fuel,
│                      #   tickets in all stages, docs, budgets; reseeds if >12h old
├── server.py          # FleetFlow brand, org migration, indexes, ticket migrations
└── tests/             # 94 original + 21 FleetFlow tests (test_fleetflow.py)

/app/frontend/src/
├── pages/Landing.jsx      # public landing at /  (dark slate + amber, BrandMark export)
├── pages/Onboarding.jsx   # /get-started — 6-step wizard (all 11 org types, validation)
├── pages/DemoEntry.jsx    # /demo — 8 role cards → POST /api/demo/enter
├── pages/Login.jsx        # FleetFlow login, show/hide pw, links, no creds shown
├── pages/OrgSettings.jsx  # /settings/organisation — profile, branches, checklist
├── pages/Expenses.jsx     # 5 tabs: Overview | Ledger | Manual | Budgets | Insights
├── components/ExpenseIntel.jsx, BudgetPanel.jsx, StatusTabs.jsx,
│   SetupChecklistBanner.jsx (dashboard)
└── App.js                 # / landing · /dashboard app home · roleTier-based guards
```

## Multi-tenancy model
- `organizations` collection; every tenant collection carries `org_id`.
- `TenantCollection` wrapper injects `org_id` into find/insert/update/delete/aggregate
  — isolation at DB layer, verified cross-org (Rajguru ↔ Acme ↔ Demo).
- Usernames/emails globally unique. Legacy data migrated to org `org-rajguru-foods`.

## Roles (12 stored → tiers)
org_admin→admin · owner/fleet_manager→management · operations/maintenance/accounts→data_entry
· viewer (read-only, server-enforced) · driver · test (sandbox) + legacy admin/management/data_entry.

## Demo environment
- Org `org-fleetflow-demo`, users `demo_<role>` (random hashed pw, never exposed).
- Enter via /demo UI or POST /api/demo/enter {role}. Yellow banner + Exit Demo (→ landing).
- Demo users blocked from user management & org settings. Data reseeds after 12 h.

## Expense Intelligence
- Consolidated ledger (fuel/service/greasing/repair/tyres/accident/fastag/trip/manual)
  with source + source_id refs.
- /expenses/overview: totals, MoM, cost/km-vehicle-trip, category & vehicle ranking, 12-mo trend.
- /expenses/insights: top-cost vehicles, category spikes, repair frequency, duplicate
  suspicion, missing attachments, budget overshoot — all data-driven.
- Budgets per category+month (duplicate-rejected), /budgets/status with variance & unbudgeted spend.

## Delivered (this session — July 2026)
- Phase 1: Multi-tenant core + full FleetFlow rebrand (PWA manifest, icons, title, SW).
- Phase 2: Landing page, 6-step onboarding, premium login, demo environment.
- Phase 3: Expense Intelligence (5 tabs, budgets, insights).
- Phase 4 (partial): Status tabs on Trips/Tickets/Drivers, vehicle/driver status filters,
  Org Settings + branches + setup checklist (dashboard banner + settings page).
- Testing: 94/94 legacy pytest + 21/21 FleetFlow pytest + frontend E2E pass (~97%),
  3 low-priority nits fixed (Exit Demo → landing, onboarding Next disabled, month Select).

## Test posture
- /app/backend/tests/test_fleet_backend.py (94) + test_fleetflow.py (21) — all green.
- /app/test_reports/iteration_5.json — full FleetFlow validation report.
- Credentials: /app/memory/test_credentials.md.

## Backlog
P1:
- Notification pipeline (email/SMS/WhatsApp) for compliance expiries & ticket SLA.
- Saved views / advanced filter drawer on module registers; filter persistence.
- Vehicle Cost Profile tab expansion (ownership cost, cost/day) on VehicleProfile.
- Branch/department/cost-centre tagging on operational records.
P2:
- Role-specific dashboard variants (accounts, maintenance, auditor).
- Excel/CSV import wizard for vehicles/drivers/vendors (templates).
- Custom roles & granular permission editor.
- Scheduled demo reset job (currently lazy on entry).
- Server-side search pagination; org logo upload UI.
