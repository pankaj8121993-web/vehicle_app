# FleetFlow demo environment

The canonical demo tenant is `org-fleetflow-demo`. It is never a production
tenant and the seeder scopes every deletion and insertion to that ID.

Supported roles are `org_admin`, `owner`, `fleet_manager`, `operations`,
`maintenance`, `accounts`, `driver`, and `viewer`. Canonical users use
`demo_<role>` usernames, random inaccessible passwords, `is_demo: true`, and
no platform privileges. Each seed check repairs those fields. A collision with
a genuine non-demo username fails closed.

## Seed lifecycle

`DEMO_SEED_VERSION` is stored as `demo_seed_version` on the organisation.
Missing, stale, incomplete, failed, expired, or older seeds are rebuilt.
Current seeds receive contained user repair only. A MongoDB lease in
`demo_seed_state` serialises reseeds across workers; other requests wait briefly
for completion and receive a retryable 503 if preparation remains busy. Failed
or stale leases can be acquired by a later request.

To reset in development, call `ensure_demo(force=True)` from an authenticated
development console. Never run a demo reset against production.

## Cookies and CORS

The Emergent preview is same-origin: the browser and `/api` share one HTTPS
origin. `fleet_session` is HttpOnly, path `/`, and SameSite Lax;
`fleet_csrf` is readable so Axios can echo it as `X-CSRF-Token`. Axios always
uses credentials. HTTPS production forces Secure cookies.

For a split-origin deployment set `REACT_APP_BACKEND_URL` to the API origin,
`CORS_ORIGINS` to the exact frontend origin (never `*`),
`FLEETFLOW_CROSS_SITE_COOKIES=true`, and the appropriate `APP_ENV`. This enables
Secure, SameSite None cookies. Do not hardcode preview hosts in source.

## Troubleshooting

Check `/api/demo/roles`, then `/api/demo/enter`, cookie attributes, and
`/api/auth/me` using the same cookie jar. A 503 means preparation is in progress
or a canonical identity conflicted. Inspect `demo_seed_state.status` and backend
logs without exposing internal errors to visitors.

Known limitation: demo changes are shared business data and periodically reset;
visitor authentication sessions are isolated and may coexist.
