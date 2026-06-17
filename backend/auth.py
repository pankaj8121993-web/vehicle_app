"""
Authentication — username + password, opaque session tokens in MongoDB,
in-memory cache, sliding 7-day expiry. Replaces Phase 1 role-picker.
"""
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header
from passlib.hash import bcrypt
from database import db
from models import UserCreate, UserUpdate, PasswordChange, LoginRequest

router = APIRouter(tags=["auth"])

ROLES = ["driver", "data_entry", "management", "admin", "test"]
ROLE_LABELS = {
    "driver": "Driver",
    "data_entry": "Data Entry Operator",
    "management": "Management",
    "admin": "Admin",
    "test": "Test User",
}

SESSION_TTL_DAYS = 7
SLIDING_THROTTLE_MINUTES = 60

# In-memory cache: token -> (user_dict, cached_at)
_session_cache = {}
_CACHE_TTL_SECONDS = 60


def _now():
    return datetime.now(timezone.utc)


def _gen_token():
    return secrets.token_urlsafe(32)


def _gen_temp_password():
    return secrets.token_urlsafe(6)[:8]


async def _resolve_session(token: str):
    """Validate token via cache or DB. Returns user dict (without password_hash) or None."""
    cached = _session_cache.get(token)
    if cached:
        user, cached_at = cached
        if (_now() - cached_at).total_seconds() < _CACHE_TTL_SECONDS:
            return user
    session = await db.user_sessions.find_one(
        {"token": token, "revoked": False}, {"_id": 0}
    )
    if not session:
        return None
    if session["expires_at"] < _now().isoformat():
        return None
    user = await db.users.find_one(
        {"id": session["user_id"], "is_active": True}, {"_id": 0, "password_hash": 0}
    )
    if not user:
        return None
    # Sliding expiry — only update if last_used_at > throttle ago
    last = session.get("last_used_at") or session["created_at"]
    try:
        last_dt = datetime.fromisoformat(last) if isinstance(last, str) else last
    except ValueError:
        last_dt = _now()
    if (_now() - last_dt).total_seconds() > SLIDING_THROTTLE_MINUTES * 60:
        new_exp = (_now() + timedelta(days=SESSION_TTL_DAYS)).isoformat()
        await db.user_sessions.update_one(
            {"id": session["id"]},
            {"$set": {"last_used_at": _now().isoformat(), "expires_at": new_exp}},
        )
    _session_cache[token] = (user, _now())
    return user


async def require_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "").strip()
    user = await _resolve_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    # Standardize internal fields used across routes
    user.setdefault("user_id", user["id"])
    user.setdefault("name", user.get("full_name") or user.get("username"))
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


# ---------- Auth endpoints ----------

@router.post("/auth/login")
async def login(payload: LoginRequest):
    username = payload.username.lower().strip()
    user = await db.users.find_one({"username": username, "is_active": True})
    if not user or not bcrypt.verify(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = _gen_token()
    expires = (_now() + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    await db.user_sessions.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "token": token,
        "created_at": _now().isoformat(),
        "last_used_at": _now().isoformat(),
        "expires_at": expires,
        "revoked": False,
    })
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "must_change_password": user.get("must_change_password", False),
        },
    }


@router.post("/auth/logout")
async def logout(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
        await db.user_sessions.update_one({"token": token}, {"$set": {"revoked": True}})
        _session_cache.pop(token, None)
    return {"ok": True}


@router.get("/auth/me")
async def me(authorization: str = Header(None)):
    # Allows even must_change_password users to read their own profile
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "").strip()
    user = await _resolve_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
        "must_change_password": user.get("must_change_password", False),
    }


@router.post("/auth/change-password")
async def change_password(payload: PasswordChange, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "").strip()
    session = await db.user_sessions.find_one({"token": token, "revoked": False}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"id": session["user_id"]})
    if not user or not bcrypt.verify(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": bcrypt.hash(payload.new_password),
                  "must_change_password": False}},
    )
    _session_cache.pop(token, None)
    return {"ok": True}


# ---------- User Management (admin only) ----------

@router.get("/users")
async def list_users(user=Depends(require_role("admin"))):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("username", 1).to_list(500)
    return users


@router.post("/users")
async def create_user(payload: UserCreate, user=Depends(require_role("admin"))):
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    username = payload.username.lower().strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    existing = await db.users.find_one({"username": username})
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
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates.get("role") and updates["role"] not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    res = await db.users.update_one({"id": uid}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    if "role" in updates or "is_active" in updates:
        await db.user_sessions.update_many({"user_id": uid}, {"$set": {"revoked": True}})
        for k in list(_session_cache.keys()):
            cached_user, _ = _session_cache[k]
            if cached_user["id"] == uid:
                _session_cache.pop(k, None)
    return await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})


@router.post("/users/{uid}/reset-password")
async def reset_password(uid: str, user=Depends(require_role("admin"))):
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
    await db.user_sessions.update_many({"user_id": uid}, {"$set": {"revoked": True}})
    return {"temporary_password": temp, "username": target["username"]}


@router.delete("/users/{uid}")
async def delete_user(uid: str, user=Depends(require_role("admin"))):
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("username") == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete the primary admin account")
    await db.user_sessions.update_many({"user_id": uid}, {"$set": {"revoked": True}})
    await db.users.delete_one({"id": uid})
    return {"ok": True}


@router.get("/roles")
async def list_roles():
    return [
        {"role": "driver", "label": "Driver",
         "rights": "Add trips, fuel entries, breakdown reports. View only elsewhere."},
        {"role": "data_entry", "label": "Data Entry Operator",
         "rights": "Add & edit all records, upload documents. Cannot delete."},
        {"role": "management", "label": "Management",
         "rights": "Dashboards, reports, approve repairs, mark vehicles disposed / drivers exited."},
        {"role": "admin", "label": "Admin",
         "rights": "Full control including delete, user management and data cleanup."},
        {"role": "test", "label": "Test User",
         "rights": "Sandbox — creates are tagged as test data, cannot modify real records."},
    ]


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
