"""
Authentication — username + password, opaque session tokens.

AUTH-01 reworked the session lifecycle. Sessions are now identified by a
*hash* of the token (so a database dump cannot be replayed), delivered in an
HttpOnly cookie (so XSS cannot read them), bounded by both an idle and an
absolute clock, rotated on login and privilege change, and protected by
double-submit CSRF on cookie-authenticated writes.

Bearer tokens in the Authorization header remain accepted so that clients
holding one keep working through the migration; see AUTHENTICATION.md.
"""
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response
from passlib.hash import bcrypt
from database import db, raw_db, current_org_id
from models import UserCreate, UserUpdate, PasswordChange, LoginRequest
import session_security as ss

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

ROLES = [
    "org_admin", "owner", "fleet_manager", "operations", "maintenance",
    "accounts", "driver", "viewer",
    # Legacy roles (still supported)
    "data_entry", "management", "admin", "test",
]
# Maps every role onto one of the enforcement tiers: admin / management / data_entry / driver / viewer / test
ROLE_EQUIV = {
    "org_admin": "admin",
    "owner": "management",
    "fleet_manager": "management",
    "operations": "data_entry",
    "maintenance": "data_entry",
    "accounts": "data_entry",
    "viewer": "viewer",
}
ROLE_LABELS = {
    "org_admin": "Organisation Super Admin",
    "owner": "Owner / Management",
    "fleet_manager": "Fleet Manager",
    "operations": "Operations User",
    "maintenance": "Maintenance Manager",
    "accounts": "Accounts User",
    "viewer": "Auditor / Viewer",
    "driver": "Driver",
    "data_entry": "Data Entry Operator",
    "management": "Management",
    "admin": "Admin",
    "test": "Test User",
}

# ---------- Module access matrix (per actual role) ----------
_ALL_ROLES = set(ROLES)
_NO_DRIVER = _ALL_ROLES - {"driver"}
_MGMT = {"admin", "org_admin", "management", "owner", "fleet_manager", "test"}
_FINANCE = _MGMT | {"accounts", "viewer"}

MODULE_ACCESS = {
    "dashboard": _ALL_ROLES,          # drivers get their mobile home
    "analytics": _NO_DRIVER,          # dashboard metrics / drilldown APIs
    "fleet-status": _NO_DRIVER,
    "compliance": _NO_DRIVER,
    "calendar": _NO_DRIVER,
    "reports": _FINANCE,
    "vehicles": _NO_DRIVER,
    "drivers": _NO_DRIVER,
    "documents": _ALL_ROLES,
    "vendors": _NO_DRIVER,
    "trips": _ALL_ROLES,
    "fuel": _ALL_ROLES,
    "maintenance": _NO_DRIVER,
    "repairs": _ALL_ROLES,
    "tyres": _NO_DRIVER,
    "accidents": _ALL_ROLES,
    "fastag": _NO_DRIVER,
    "downtime": _NO_DRIVER,
    "expenses": _FINANCE | {"data_entry", "operations"},
    "search": _NO_DRIVER,
    "org-settings": {"admin", "org_admin", "management", "owner", "fleet_manager"},
    "users": {"admin", "org_admin"},
    "test-data": {"admin", "org_admin"},
}


def allowed_modules(role):
    return sorted(m for m, roles in MODULE_ACCESS.items() if role in roles)


def require_module(module):
    async def dep(user=Depends(require_user)):
        if user.get("_must_change_pw"):
            raise HTTPException(status_code=403, detail="Must change password first")
        role = user.get("actual_role") or user.get("role")
        if role not in MODULE_ACCESS.get(module, set()):
            raise HTTPException(status_code=403, detail="Your role does not have access to this module")
        return user
    return dep

# In-memory cache: token_hash -> (user_dict, session_dict, cached_at).
#
# Keyed by hash, never by the raw token, so process memory holds no replayable
# credential either. The TTL is deliberately short: it is a database-load
# optimisation, not a revocation boundary. Revocation paths evict explicitly,
# and a backend restart still clears everything (see CREDENTIAL_ROTATION.md).
_session_cache = {}
_CACHE_TTL_SECONDS = 60


def _now():
    return datetime.now(timezone.utc)


def _gen_temp_password():
    return ss.generate_token()[:12]


def _evict_cached_user(user_id: str):
    """Drop every cached session for one user. Called by revocation paths."""
    for key in [k for k, (u, _s, _t) in _session_cache.items() if u.get("id") == user_id]:
        _session_cache.pop(key, None)


async def revoke_user_sessions(user_id: str, *, reason: str):
    """Revoke every session for a user and evict them from the cache.

    AUTH-01 requires immediate revocation after a password change or reset, a
    role change, deactivation, or organisation suspension. Callers pass a reason
    purely so the audit line says why.
    """
    res = await db.user_sessions.update_many(
        {"user_id": user_id, "revoked": False},
        {"$set": {"revoked": True, "revoked_at": _now(), "revoked_reason": reason}},
    )
    _evict_cached_user(user_id)
    if res.modified_count:
        logger.info(
            "Revoked %d session(s) for user %s (%s)", res.modified_count, user_id, reason
        )
    return res.modified_count


async def create_session(user_id: str, *, request: Request = None) -> tuple:
    """Create a session. Returns ``(token, csrf_token)``.

    Only the *hashes* are persisted. The raw values are returned once, to be set
    as cookies, and are unrecoverable afterwards.
    """
    token = ss.generate_token()
    csrf = ss.generate_csrf_token()
    created = _now()
    await db.user_sessions.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "token_hash": ss.hash_token(token),
        "csrf_hash": ss.hash_token(csrf),
        "created_at": created,
        "last_used_at": created,
        # Real datetimes: the TTL index needs a BSON date, and both expiry
        # clocks compare datetimes rather than ISO strings.
        "absolute_expires_at": ss.absolute_expiry(created),
        "revoked": False,
        "user_agent": (request.headers.get("user-agent") if request else None),
        "ip": (request.client.host if request and request.client else None),
    })
    return token, csrf


async def _resolve_session(token: str):
    """Validate a raw token. Returns (user, session) or (None, None)."""
    if not token:
        return None, None
    token_hash = ss.hash_token(token)

    cached = _session_cache.get(token_hash)
    if cached:
        user, session, cached_at = cached
        if (_now() - cached_at).total_seconds() < _CACHE_TTL_SECONDS:
            # Re-check expiry on every hit: the cache must never extend a
            # session's life past either clock.
            if ss.is_expired(session):
                _session_cache.pop(token_hash, None)
                return None, None
            return user, session
        _session_cache.pop(token_hash, None)

    session = await db.user_sessions.find_one(
        {"token_hash": token_hash, "revoked": False}, {"_id": 0}
    )
    if not session or ss.is_expired(session):
        return None, None
    user = await db.users.find_one(
        {"id": session["user_id"], "is_active": True}, {"_id": 0, "password_hash": 0}
    )
    if not user:
        return None, None

    # Sliding refresh moves only the idle clock. absolute_expires_at is never
    # extended, so a stolen token cannot be kept alive by using it.
    if ss.should_refresh(session.get("last_used_at")):
        await db.user_sessions.update_one(
            {"id": session["id"]}, {"$set": {"last_used_at": _now()}}
        )

    user = dict(user)
    _session_cache[token_hash] = (user, session, _now())
    return user, session


def _extract_token(request: Request, authorization: str):
    """Return (token, via) where via is "cookie" or "bearer".

    Cookie first: it is the AUTH-01 mechanism. The Authorization header stays
    supported so clients holding a bearer token keep working through the
    migration — and because a bearer token cannot be sent cross-site by a
    browser without script, only the cookie path needs CSRF.
    """
    cookie_token = request.cookies.get(ss.SESSION_COOKIE) if request else None
    if cookie_token:
        return cookie_token, "cookie"
    if authorization and authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "").strip(), "bearer"
    return None, None


def _enforce_csrf(request: Request, session: dict, via: str):
    """Double-submit CSRF check for cookie-authenticated state changes.

    Only cookie auth is vulnerable: the browser attaches the cookie
    automatically on a cross-site request, whereas an Authorization header
    requires script that same-origin policy already prevents.
    """
    if via != "cookie" or request.method in ss.SAFE_METHODS:
        return
    provided = request.headers.get(ss.CSRF_HEADER)
    expected_hash = session.get("csrf_hash")
    if not provided or not expected_hash:
        raise HTTPException(status_code=403, detail="CSRF token missing")
    if not ss.csrf_valid(expected_hash, ss.hash_token(provided)):
        raise HTTPException(status_code=403, detail="CSRF token invalid")


async def require_user(request: Request, authorization: str = Header(None)):
    token, via = _extract_token(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user, session = await _resolve_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    _enforce_csrf(request, session, via)
    # Standardize internal fields + apply effective role tier & org context
    user = dict(user)
    user.setdefault("user_id", user["id"])
    user.setdefault("name", user.get("full_name") or user.get("username"))
    user["actual_role"] = user.get("role")
    user["role"] = ROLE_EQUIV.get(user.get("role"), user.get("role"))
    current_org_id.set(user.get("org_id"))
    if user.get("must_change_password"):
        return {**user, "_must_change_pw": True}
    return user


def require_role(*roles):
    async def dep(user=Depends(require_user)):
        if user.get("_must_change_pw"):
            raise HTTPException(status_code=403, detail="Must change password first")
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dep


async def is_last_active_org_admin(users, uid, target) -> bool:
    """True if deleting `target` (id == uid) would remove an organisation's last
    active org_admin.

    `users` must be the organisation-scoped users collection, so the count is
    naturally limited to the caller's organisation. Only role ``org_admin`` is
    protected; other roles (and inactive admins) are never blocked here.
    """
    if target.get("role") != "org_admin" or not target.get("is_active", True):
        return False
    other_admins = await users.count_documents(
        {"role": "org_admin", "is_active": True, "id": {"$ne": uid}}
    )
    return other_admins == 0


# ---------- Auth endpoints ----------

async def _org_name(org_id):
    if not org_id:
        return None
    org = await raw_db.organizations.find_one({"id": org_id}, {"_id": 0, "trade_name": 1, "legal_name": 1})
    return (org.get("trade_name") or org.get("legal_name")) if org else None


async def _user_payload(user):
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
        "must_change_password": user.get("must_change_password", False),
        "org_id": user.get("org_id"),
        "org_name": await _org_name(user.get("org_id")),
        "is_demo": bool(user.get("is_demo")),
        "modules": allowed_modules(user["role"]),
    }


def set_session_cookies(response: Response, token: str, csrf: str):
    """Attach the session and CSRF cookies. The single place that does this."""
    response.set_cookie(ss.SESSION_COOKIE, token, **ss.cookie_params())
    response.set_cookie(ss.CSRF_COOKIE, csrf, **ss.csrf_cookie_params())
    # Auth responses carry identity; keep them out of shared and back/forward
    # caches so a logged-out browser cannot show them again.
    response.headers["Cache-Control"] = "no-store, private"


def clear_session_cookies(response: Response):
    params = ss.cookie_params()
    response.delete_cookie(ss.SESSION_COOKIE, path=params["path"], samesite=params["samesite"], secure=params["secure"])
    response.delete_cookie(ss.CSRF_COOKIE, path=params["path"], samesite=params["samesite"], secure=params["secure"])
    response.headers["Cache-Control"] = "no-store, private"


async def _record_failed_login(username: str, ip: str):
    await raw_db.login_attempts.insert_one({
        "username": (username or "").lower().strip(),
        "ip": ip or "unknown",
        "at": _now(),
    })


async def _is_throttled(username: str, ip: str) -> bool:
    """True if this username OR this IP has too many recent failures.

    Counted independently so neither a targeted attack on one account nor a
    spray from one address can run unbounded. Uses the same generic error as a
    wrong password, so throttling never confirms an account exists.
    """
    since = _now() - ss.THROTTLE_WINDOW
    uname = (username or "").lower().strip()
    by_user = await raw_db.login_attempts.count_documents(
        {"username": uname, "at": {"$gte": since}}
    )
    if by_user >= ss.MAX_FAILED_ATTEMPTS:
        return True
    by_ip = await raw_db.login_attempts.count_documents(
        {"ip": ip or "unknown", "at": {"$gte": since}}
    )
    return by_ip >= ss.MAX_FAILED_ATTEMPTS


@router.post("/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    username = payload.username.lower().strip()
    ip = request.client.host if request.client else "unknown"

    if await _is_throttled(username, ip):
        # Deliberately the same shape as a bad password: a distinct "locked"
        # message would confirm the account exists.
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Please try again later.",
        )

    user = await raw_db.users.find_one({"username": username, "is_active": True})
    # Always run a bcrypt verify, even when the user does not exist, so the
    # response time does not reveal which usernames are real.
    stored_hash = user["password_hash"] if user else bcrypt.hash("invalid-placeholder")
    password_ok = bcrypt.verify(payload.password, stored_hash)
    if not user or not password_ok:
        await _record_failed_login(username, ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Session fixation: any pre-login session for this user is discarded, so a
    # token an attacker planted before authentication cannot survive it.
    await revoke_user_sessions(user["id"], reason="login_rotation")
    token, csrf = await create_session(user["id"], request=request)
    await raw_db.login_attempts.delete_many({"username": username})

    set_session_cookies(response, token, csrf)
    return {
        # Returned for backward compatibility with clients still reading a
        # bearer token. The cookie above is the mechanism AUTH-01 relies on;
        # this field goes away once no client needs it (see AUTHENTICATION.md).
        "token": token,
        "csrf_token": csrf,
        "user": await _user_payload(user),
    }


@router.post("/auth/logout")
async def logout(request: Request, response: Response, authorization: str = Header(None)):
    token, _via = _extract_token(request, authorization)
    if token:
        token_hash = ss.hash_token(token)
        await db.user_sessions.update_one(
            {"token_hash": token_hash},
            {"$set": {"revoked": True, "revoked_at": _now(), "revoked_reason": "logout"}},
        )
        _session_cache.pop(token_hash, None)
    clear_session_cookies(response)
    return {"ok": True}


# ---------- Session / device management ----------

@router.get("/auth/sessions")
async def list_sessions(request: Request, user=Depends(require_user), authorization: str = Header(None)):
    """The caller's own active sessions. Never exposes tokens or hashes."""
    token, _via = _extract_token(request, authorization)
    current_hash = ss.hash_token(token) if token else None
    out = []
    # Inclusion projection: csrf_hash and any future secret are excluded by
    # simply not being listed. (Mongo rejects mixing inclusion and exclusion.)
    # token_hash is fetched only to mark the current session and is not returned.
    async for s in db.user_sessions.find(
        {"user_id": user["user_id"], "revoked": False},
        {"_id": 0, "id": 1, "token_hash": 1, "created_at": 1,
         "last_used_at": 1, "absolute_expires_at": 1, "user_agent": 1, "ip": 1},
    ):
        if ss.is_expired(s):
            continue
        out.append({
            "id": s["id"],
            "created_at": s.get("created_at"),
            "last_used_at": s.get("last_used_at"),
            "expires_at": s.get("absolute_expires_at"),
            "user_agent": s.get("user_agent"),
            "ip": s.get("ip"),
            "current": s.get("token_hash") == current_hash,
        })
    out.sort(key=lambda r: r.get("last_used_at") or r.get("created_at"), reverse=True)
    return out


@router.delete("/auth/sessions/{session_id}")
async def revoke_session(session_id: str, user=Depends(require_user)):
    """Revoke one of the caller's own sessions.

    Scoped by user_id, so a session id belonging to someone else simply does not
    match and returns 404 — no existence disclosure.
    """
    session = await db.user_sessions.find_one(
        {"id": session_id, "user_id": user["user_id"]}, {"_id": 0, "token_hash": 1}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.user_sessions.update_one(
        {"id": session_id},
        {"$set": {"revoked": True, "revoked_at": _now(), "revoked_reason": "user_revoked"}},
    )
    _session_cache.pop(session.get("token_hash"), None)
    return {"ok": True}


@router.post("/auth/sessions/revoke-all")
async def revoke_all_sessions(response: Response, user=Depends(require_user)):
    """Revoke every session for the caller, including the current one."""
    count = await revoke_user_sessions(user["user_id"], reason="user_revoked_all")
    clear_session_cookies(response)
    return {"ok": True, "revoked": count}


@router.get("/auth/me")
async def me(request: Request, response: Response, authorization: str = Header(None)):
    # Allows even must_change_password users to read their own profile
    token, _via = _extract_token(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user, _session = await _resolve_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    # AUTH-01: /auth/me is what the frontend revalidates against on route change
    # and tab focus. It must never be served from the back/forward cache, or a
    # logged-out user would see a stale authenticated shell.
    response.headers["Cache-Control"] = "no-store, private"
    return await _user_payload(user)


@router.post("/auth/change-password")
async def change_password(
    payload: PasswordChange,
    request: Request,
    response: Response,
    authorization: str = Header(None),
):
    token, via = _extract_token(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user, session = await _resolve_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired")
    _enforce_csrf(request, session, via)

    full_user = await db.users.find_one({"id": user["id"]})
    if not full_user or not bcrypt.verify(payload.current_password, full_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": bcrypt.hash(payload.new_password),
                  "must_change_password": False}},
    )
    # Every existing session dies, including this one — a password change must
    # evict anyone who captured a token before it. The caller is then re-issued a
    # fresh session so they are not logged out of the tab they are typing in.
    await revoke_user_sessions(user["id"], reason="password_change")
    new_token, new_csrf = await create_session(user["id"], request=request)
    set_session_cookies(response, new_token, new_csrf)
    return {"ok": True, "token": new_token, "csrf_token": new_csrf}


# ---------- User Management (admin only) ----------

@router.get("/users")
async def list_users(user=Depends(require_role("admin"))):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("username", 1).to_list(500)
    return users


@router.post("/users")
async def create_user(payload: UserCreate, user=Depends(require_role("admin"))):
    if user.get("is_demo"):
        raise HTTPException(status_code=403, detail="Demo users cannot manage users")
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    username = payload.username.lower().strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    existing = await raw_db.users.find_one({"username": username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    doc = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": bcrypt.hash(payload.password),
        "role": payload.role,
        "full_name": payload.full_name,
        "is_active": payload.is_active if payload.is_active is not None else True,
        "must_change_password": True,
        "created_at": _now().isoformat(),
        "created_by": user["id"],
    }
    await db.users.insert_one({**doc})
    doc.pop("password_hash", None)
    return doc


@router.put("/users/{uid}")
async def update_user(uid: str, payload: UserUpdate, user=Depends(require_role("admin"))):
    if user.get("is_demo"):
        raise HTTPException(status_code=403, detail="Demo users cannot manage users")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates.get("role") and updates["role"] not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    res = await db.users.update_one({"id": uid}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    if "role" in updates or "is_active" in updates:
        # A privilege change must not leave a token minted under the old role
        # (or under an active account) working.
        reason = "role_change" if "role" in updates else "activation_change"
        await revoke_user_sessions(uid, reason=reason)
    return await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})


@router.post("/users/{uid}/reset-password")
async def reset_password(uid: str, user=Depends(require_role("admin"))):
    if user.get("is_demo"):
        raise HTTPException(status_code=403, detail="Demo users cannot manage users")
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Use change-password for yourself")
    temp = _gen_temp_password()
    await db.users.update_one(
        {"id": uid},
        {"$set": {"password_hash": bcrypt.hash(temp), "must_change_password": True}},
    )
    # Revoke through the shared path so the in-memory cache is evicted too —
    # the old code only flipped the database flag, leaving a reset user's
    # sessions live for up to the cache TTL.
    await revoke_user_sessions(uid, reason="password_reset")
    return {"temporary_password": temp, "username": target["username"]}


@router.delete("/users/{uid}")
async def delete_user(uid: str, user=Depends(require_role("admin"))):
    if user.get("is_demo"):
        raise HTTPException(status_code=403, detail="Demo users cannot manage users")
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # Never let an organisation delete its last active org_admin. db.users is
    # already scoped to the caller's organisation, so the count is org-local.
    if await is_last_active_org_admin(db.users, uid, target):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the last active organisation administrator",
        )
    await db.user_sessions.update_many({"user_id": uid}, {"$set": {"revoked": True}})
    await db.users.delete_one({"id": uid})
    return {"ok": True}


@router.get("/roles")
async def list_roles():
    rights = {
        "org_admin": "Full control of this organisation — users, settings, data cleanup and deletes.",
        "owner": "Dashboards, reports, approvals, disposals and organisation settings.",
        "fleet_manager": "Dashboards, reports, ticket approvals, vehicle & driver lifecycle.",
        "operations": "Add & edit trips, fuel, maintenance and operational records.",
        "maintenance": "Add & edit services, greasing, repairs, tyres and vendor jobs.",
        "accounts": "Add & edit expenses, budgets, FASTag and payment records.",
        "driver": "Add trips, fuel entries and breakdown reports. View only elsewhere.",
        "viewer": "Read-only access to every module — ideal for auditors.",
        "data_entry": "Add & edit all records, upload documents. Cannot delete.",
        "management": "Dashboards, reports, approve repairs, disposals and driver exits.",
        "admin": "Full control including delete, user management and data cleanup.",
        "test": "Sandbox — creates are tagged as test data, cannot modify real records.",
    }
    return [{"role": r, "label": ROLE_LABELS[r], "rights": rights[r]} for r in ROLES]


# ---------- Admin: purge test data ----------

@router.post("/admin/purge-test-data")
async def purge_test_data(user=Depends(require_role("admin"))):
    collections = [
        "vehicles", "drivers", "documents", "trips", "fuel_entries",
        "services", "repairs", "tyres", "tyre_events", "accidents",
        "fastag_transactions", "downtimes", "expenses", "greasings",
        "calendar_events",
    ]
    deleted = {}
    for coll in collections:
        r = await db[coll].delete_many({"is_test_data": True})
        deleted[coll] = r.deleted_count
    return {"deleted": deleted, "total": sum(deleted.values())}
