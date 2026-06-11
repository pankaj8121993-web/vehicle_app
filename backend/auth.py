from fastapi import APIRouter, HTTPException, Request, Depends

router = APIRouter(tags=["roles"])

# Simple role-based access (no login). Frontend sends the selected role in the X-Role header.
ROLES = ["driver", "data_entry", "management", "admin"]
ROLE_LABELS = {
    "driver": "Driver",
    "data_entry": "Data Entry Operator",
    "management": "Management",
    "admin": "Admin",
}


async def require_user(request: Request):
    role = request.headers.get("X-Role", "admin")
    if role not in ROLES:
        role = "admin"
    return {"user_id": f"role-{role}", "name": ROLE_LABELS[role], "role": role}


def require_role(*roles):
    async def dep(request: Request):
        user = await require_user(request)
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dep


@router.get("/roles")
async def list_roles():
    return [
        {"role": "driver", "label": "Driver", "rights": "Add trips, fuel entries & breakdown reports. View-only access elsewhere."},
        {"role": "data_entry", "label": "Data Entry Operator", "rights": "Add & edit all records, upload documents and invoices. Cannot delete."},
        {"role": "management", "label": "Management", "rights": "Dashboards, reports, approve major repairs, add & edit records. Cannot delete."},
        {"role": "admin", "label": "Admin", "rights": "Full control — everything including delete and data cleanup."},
    ]
