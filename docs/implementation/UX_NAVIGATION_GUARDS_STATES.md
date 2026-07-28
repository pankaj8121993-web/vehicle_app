# UX-01 — Navigation, Guards and Page States

**Baseline:** `09050bf19cfabb2bfd464841b68f318b134a00f6`  
**Production accessed:** No

## Guard model

- `/` is public and remains usable regardless of auth state.
- `/login`, `/demo`, and `/get-started` are guest-only. They wait for auth
  hydration, remain stable for anonymous users, and send authenticated users to
  their dashboard.
- Authenticated routes wait for hydration, preserve a safe intended destination
  on login, and enforce forced-password change before rendering application
  chrome.
- Module and role restrictions render `/permission-denied`; they do not masquerade
  as an unauthenticated redirect or silently bounce to dashboard.
- Server authentication and permission enforcement remain authoritative. The
  frontend module filter is navigation affordance, not a security control.
- Unknown URLs render a recoverable not-found state.

## Actual route matrix

All protected pages use the shared full-page loading state, explicit permission
denial, and the existing responsive `Layout`/mobile sheet. Page-local empty and
API-error behaviour remains listed where it differs.

| Path | Page | Access / module | Detail / row action | Back and states |
| --- | --- | --- | --- | --- |
| `/` | Landing | Public | — | Public content; responsive landing |
| `/get-started` | Onboarding | Guest-only | Landing CTA | Step back; form feedback |
| `/demo` | DemoEntry | Guest-only | Landing/demo CTA | Role loading/error/retry |
| `/login` | Login | Guest-only | Protected redirect | Safe intended destination retained |
| `/change-password` | ChangePassword | Authenticated | User menu / forced flow | Forced-password redirect; form error |
| `/dashboard` | Dashboard or DriverHome | Authenticated | Sidebar | Skeleton/loading; dashboard sections |
| `/vehicles` | Vehicles | Authenticated; `vehicles` | Row → `/vehicles/:id` | Query context passed to detail |
| `/vehicles/:id` | VehicleProfile | Authenticated; `vehicles` | Vehicle rows/search/drilldowns | Return to originating list URL; loading/not-found |
| `/drivers` | DriversPage | Authenticated; `drivers` | Row → `/drivers/:id` | Query context passed to detail |
| `/drivers/:id` | DriverProfile | Authenticated; `drivers` | Driver rows/search/drilldowns | Return to originating list URL; loading/not-found |
| `/documents` | DocumentsPage | Authenticated; `documents` | Sidebar | Crud loading/empty/error toast |
| `/trips` | TripsPage | Authenticated; `trips` | Sidebar/driver actions | Crud loading/empty/error toast |
| `/fuel` | FuelPage | Authenticated; `fuel` | Sidebar/driver actions | Crud loading/empty/error toast |
| `/maintenance` | MaintenancePage | Authenticated; `maintenance` | Sidebar | Crud loading/empty/error toast |
| `/repairs` | RepairsPage | Authenticated; `repairs` | Sidebar/search tickets | Crud loading/empty/error toast |
| `/tyres` | TyresPage | Authenticated; `tyres` | Sidebar | Crud loading/empty/error toast |
| `/accidents` | AccidentsPage | Authenticated; `accidents` | Sidebar/driver action | Crud loading/empty/error toast |
| `/fastag` | FastagPage | Authenticated; `fastag` | Sidebar | Crud loading/empty/error toast |
| `/downtime` | DowntimePage | Authenticated; `downtime` | Sidebar | Crud loading/empty/error toast |
| `/expenses` | Expenses | Authenticated; `expenses` | Sidebar/driver action | Ledger loading and error feedback |
| `/reports` | Reports | Authenticated; `reports` | Sidebar | Generate/export loading and error |
| `/compliance` | Compliance | Authenticated; `compliance` | Sidebar | Loading and expiry empty sections |
| `/compliance/contacts` | ComplianceContacts | Management/admin; `compliance` | Compliance/admin nav | Explicit permission denial |
| `/calendar` | CalendarPage | Authenticated; `calendar` | Sidebar | Calendar loading/action feedback |
| `/fleet-status` | FleetStatus | Authenticated; `fleet-status` | Vehicle card → profile | Loading/refresh and profile navigation |
| `/vendors` | Vendors | Authenticated; `vendors` | Sidebar | Page-local list states |
| `/settings/organisation` | OrgSettings | Management/admin; `org-settings` | Admin nav | Loading/error; explicit denial |
| `/users` | UserManagement | Admin; `users` | Admin nav | Loading/action feedback; explicit denial |
| `/admin/test-data` | TestDataAdmin | Admin; `test-data` | Admin nav | Action loading/result; explicit denial |
| `/permission-denied` | PermissionDenied | Authenticated | Guard outcome | Clear explanation and dashboard action |
| `*` | NotFound | Public fallback | Invalid address | Clear explanation and home action |

Server roles are mapped through the existing `roleTier` compatibility layer;
module availability comes from the authenticated server profile. The supported
business roles remain `org_admin`, `owner`, `fleet_manager`, `operations`,
`maintenance`, `accounts`, `driver`, and `viewer`; effective access is determined
by their backend-issued role/module profile.

## Reusable state contract

`PageLoading` announces initial loading without showing empty content.
`PageState` covers empty, no-results, recoverable/nonrecoverable error, network
unavailable, permission denied, and not-found presentations with an optional
retry/recovery action. It deliberately accepts user-safe copy only; callers
must not pass raw backend exceptions.

## Test evidence

- React route suite: 9 passed.
- Covered: public-route stability, protected redirect, permission denial, auth
  hydration, guest-only redirect, and broken-route fallback.
- Playwright: 3/3 passed on Chromium desktop and 3/3 passed on mobile Chromium,
  covering anonymous public routes, protected redirect, and fallback.
- Production build: pass; main JS 369.39 kB gzip.
- Backend application code was not changed.

Role-backed browser fixtures are retained as a documented follow-on test-harness
extension; the server-issued module contract itself is covered by the component
guard suite.
