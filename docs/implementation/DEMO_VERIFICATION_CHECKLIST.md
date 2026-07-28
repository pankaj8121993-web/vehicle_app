# DEMO-01 verification checklist

Use only the non-production preview.

- Confirm `/demo` displays a role-loading state and all eight server roles.
- For every role, enter without credentials and confirm `/auth/me` returns 200.
- Check dashboard, vehicles, trips, and exceptions permitted by that role.
- Confirm a permitted action succeeds and a restricted mutation returns 403.
- Refresh dashboard plus two permitted module routes.
- Confirm `fleet_session` is HttpOnly and `fleet_csrf` is readable; both use
  path `/`, the expected SameSite/Secure policy, and are sent to `/auth/me`.
- Confirm state-changing cookie-authenticated calls send `X-CSRF-Token`.
- Logout, confirm the old session returns 401, and re-enter.
- Repeat in a clean session, an isolated incognito-equivalent session, and a
  mobile viewport; inspect console and network logs.
- Run focused demo tests, concurrency tests, integrity/reconciliation checks,
  full backend tests, frontend production build, Ruff, compilation, and secret
  scan.

API sequence:

`GET roles → POST enter → GET me → GET dashboard → GET vehicles → GET trips →
GET exceptions → POST logout → POST enter`.
