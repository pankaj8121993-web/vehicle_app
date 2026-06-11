import uuid
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request, Response, Body, Depends
from database import db

router = APIRouter(tags=["auth"])

ROLES = ["driver", "data_entry", "fleet_manager", "management"]
SESSION_DATA_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


async def get_user_from_request(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
    if not token:
        token = request.query_params.get("auth")
    if not token:
        return None
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        return None
    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    return await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})


async def require_user(request: Request):
    user = await get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_role(*roles):
    async def dep(request: Request):
        user = await require_user(request)
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dep


@router.post("/auth/session")
async def create_session(response: Response, payload: dict = Body(...)):
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    async with httpx.AsyncClient() as client:
        resp = await client.get(SESSION_DATA_URL, headers={"X-Session-ID": session_id}, timeout=30)
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    data = resp.json()

    user = await db.users.find_one({"email": data["email"]}, {"_id": 0})
    if not user:
        users_count = await db.users.count_documents({})
        role = "management" if users_count == 0 else "driver"
        user = {
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": data["email"],
            "name": data.get("name", ""),
            "picture": data.get("picture", ""),
            "role": role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one({**user})
    else:
        await db.users.update_one(
            {"email": data["email"]},
            {"$set": {"name": data.get("name", user.get("name")), "picture": data.get("picture", user.get("picture"))}},
        )
        user = await db.users.find_one({"email": data["email"]}, {"_id": 0})

    session_token = data["session_token"]
    await db.user_sessions.insert_one({
        "user_id": user["user_id"],
        "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    response.set_cookie(
        key="session_token", value=session_token, httponly=True,
        secure=True, samesite="none", path="/", max_age=7 * 24 * 3600,
    )
    return user


@router.get("/auth/me")
async def get_me(user=Depends(require_user)):
    return user


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@router.get("/users")
async def list_users(user=Depends(require_role("management", "fleet_manager"))):
    return await db.users.find({}, {"_id": 0}).to_list(500)


@router.patch("/users/{user_id}/role")
async def set_role(user_id: str, payload: dict = Body(...), user=Depends(require_role("management"))):
    role = payload.get("role")
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if target and target.get("role") == "management" and role != "management":
        mgmt_count = await db.users.count_documents({"role": "management"})
        if mgmt_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last Management user")
    res = await db.users.update_one({"user_id": user_id}, {"$set": {"role": role}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return await db.users.find_one({"user_id": user_id}, {"_id": 0})
