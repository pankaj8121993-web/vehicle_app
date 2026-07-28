"""Safe, reusable server-side list query helpers."""
import math
import re


SEARCH_FIELDS = {
    "vehicles": ("vehicle_number", "make", "model", "chassis_number", "engine_number"),
    "drivers": ("name", "employee_number", "mobile", "license_number"),
    "trips": ("from_location", "to_location", "purpose", "status"),
    "expenses": ("category", "description", "vendor", "status"),
    "fuel_entries": ("fuel_station", "payment_mode"),
    "fastag_transactions": ("plaza_name", "txn_type"),
    "repair_tickets": ("ticket_number", "category", "description", "status"),
    "repairs": ("ticket_number", "category", "description", "status"),
    "tyres": ("tyre_number", "brand", "status"),
    "downtimes": ("reason", "status"),
    "accidents": ("location", "description", "claim_status"),
    "documents": ("doc_type", "doc_number"),
    "vendors": ("name", "vendor_type", "contact_person", "mobile"),
}


def add_safe_search(query: dict, collection: str, term: str | None) -> dict:
    term = (term or "").strip()
    fields = SEARCH_FIELDS.get(collection, ())
    if not term or not fields:
        return query
    escaped = re.escape(term[:100])
    query["$or"] = [{field: {"$regex": escaped, "$options": "i"}} for field in fields]
    return query


def pagination(params: dict) -> tuple[int, int]:
    try:
        page = max(int(params.get("page", 1)), 1)
        page_size = min(max(int(params.get("page_size", 25)), 1), 200)
    except (TypeError, ValueError):
        page, page_size = 1, 25
    return page, page_size


def sort_spec(params: dict, allowed: set[str], default_field: str, default_direction: int = -1) -> tuple[str, int]:
    field = params.get("sort_by") or default_field
    if field not in allowed:
        field = default_field
    direction = -1 if (params.get("sort_dir") or ("desc" if default_direction < 0 else "asc")).lower() == "desc" else 1
    return field, direction


def page_response(items: list, total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }
