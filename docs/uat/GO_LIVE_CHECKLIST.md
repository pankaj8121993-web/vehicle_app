# FleetFlow — Go-Live Checklist

Operator-led steps that must be completed **after** business UAT sign-off and
**before** production release. Repository work in Phase 4 does not perform any of
these; each is checked off by the named owner against production/staging.

## 1. Business acceptance
- [ ] UAT completed; `UAT_SIGNOFF_TEMPLATE` signed by the business owner
- [ ] No open P0 or P1 UAT defects

## 2. Security operations (operator-led — NOT done in the repository phases)
- [ ] **SEC-004** production credential rotation complete and verified
- [ ] **SEC-005** Git-history secret cleanup complete and verified
- [ ] Recovery/break-glass administrator provisioned and login verified
- [ ] Secret scanning green on the release ref (gitleaks)

## 3. Production data
- [ ] Production **backup** taken and **restore** verified on a copy
- [ ] Production **data-integrity scan** run on a copy (`check_data_integrity.py`)
- [ ] Reconciliation drift reviewed and signed off
- [ ] Required **production data repairs** applied and re-scanned
- [ ] **File ownership migration** verified (every file record org-scoped; no orphan/global files)

## 4. Environment configuration
- [ ] `MONGO_URL` / `DB_NAME` point at production; no test/UAT db
- [ ] **CORS** set to explicit production origin(s) — never `*` with credentials
- [ ] **HTTPS** enforced; secure/HttpOnly/SameSite cookies confirmed
- [ ] Session TTL, CSRF and security headers verified in production config
- [ ] FASTag simulation confirmed **disabled/fail-closed** outside the demo org

## 5. Delivery controls
- [ ] **Branch protection** on `main` and `develop`; required CI checks enforced
- [ ] Required CI checks green on the release commit
- [ ] **Deployment procedure** documented and dry-run
- [ ] **Rollback procedure** documented and dry-run (previous image + db restore path)
- [ ] Monitoring/alerting and log retention in place

## 6. Final authorisation
- [ ] Security release gate, data-integrity release gate and operations release gate reviewed together
- [ ] **Final business-owner sign-off** for production release recorded
- [ ] Go/no-go decision recorded in `RELEASE_READINESS_GATE.md`

> Until every item above is checked, production release remains **blocked**.
