"""
DI-01 — Referential integrity for canonical records (DB-aware).

A create body carries foreign keys — ``vehicle_id``, ``driver_id``, ``tyre_id``,
``vendor_id`` — that must point at a real record *in the same organisation* and,
for new operational activity, at one that is still in service. Before DI-01
nothing checked this: a fuel entry could be filed against a ``vehicle_id`` that
did not exist, belonged to another tenant, or named a vehicle already marked
sold/scrapped, leaving an orphaned or cross-tenant reference that every
per-vehicle total then silently mis-attributed.

The checks below all resolve their target through the tenant-scoped ``db``
(``database.TenantCollection``), so a foreign key pointing at another
organisation's record simply does not resolve and is rejected exactly like a
non-existent one — no cross-tenant existence disclosure, consistent with the
TEN-01/TEN-TEST 404-not-403 rule.

Design rules
------------
* **Same-org by construction.** Every lookup uses the scoped ``db``; there is no
  code path here that reads across organisations.
* **Block new activity on retired entities, preserve history.** Operational
  events (trips, fuel, service, greasing, repair, downtime) may not be *created*
  against a disposed vehicle or, for trips, an exited driver — that is new work
  on something no longer in service. Historical/closing records (accidents,
  expenses, documents, tyre removal events) are intentionally *not* blocked, so
  a legitimate post-disposal cost can still be recorded.
* **Optional keys stay optional.** A ``None``/absent foreign key is not an error;
  only a *supplied* one is validated.
"""
from fastapi import HTTPException

from database import db

# Vehicle disposal / driver exit states (kept in step with routes_core).
DISPOSED_VEHICLE_STATUSES = {"sold", "scrapped"}
EXITED_DRIVER_STATUSES = {"resigned", "terminated"}

# Collections whose *new* records represent live operational activity and so may
# not be filed against a disposed vehicle. Everything else may reference a
# disposed vehicle (historical corrections, closing costs, accident records).
OPERATIONAL_VEHICLE_COLLECTIONS = {
    "trips", "fuel_entries", "services", "greasings", "repairs", "downtimes",
}

# Collections where a new record may not name an exited driver.
DRIVER_ACTIVE_REQUIRED_COLLECTIONS = {"trips"}


async def _vehicle(vehicle_id):
    return await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0, "id": 1, "status": 1})


async def validate_references(collection, doc):
    """Validate every foreign key present in ``doc`` for ``collection``.

    Raises HTTP 400 when a referenced vehicle/driver/tyre/vendor does not exist
    in the caller's organisation, or 400 when new operational activity targets a
    disposed vehicle or an exited driver. Safe to call with a partial document.
    """
    vehicle_id = doc.get("vehicle_id")
    if vehicle_id:
        vehicle = await _vehicle(vehicle_id)
        if not vehicle:
            raise HTTPException(status_code=400, detail="Referenced vehicle does not exist")
        if (
            collection in OPERATIONAL_VEHICLE_COLLECTIONS
            and vehicle.get("status") in DISPOSED_VEHICLE_STATUSES
        ):
            raise HTTPException(
                status_code=400,
                detail="Cannot record new activity against a sold or scrapped vehicle",
            )

    driver_id = doc.get("driver_id")
    if driver_id:
        driver = await db.drivers.find_one(
            {"id": driver_id}, {"_id": 0, "id": 1, "status": 1}
        )
        if not driver:
            raise HTTPException(status_code=400, detail="Referenced driver does not exist")
        if (
            collection in DRIVER_ACTIVE_REQUIRED_COLLECTIONS
            and driver.get("status") in EXITED_DRIVER_STATUSES
        ):
            raise HTTPException(
                status_code=400,
                detail="Cannot assign a resigned or terminated driver",
            )

    # A driver's assigned vehicle is a foreign key too; a driver may only be
    # assigned to a real, in-service vehicle in their own organisation.
    assigned_vehicle_id = doc.get("assigned_vehicle_id")
    if assigned_vehicle_id:
        assigned = await _vehicle(assigned_vehicle_id)
        if not assigned:
            raise HTTPException(status_code=400, detail="Assigned vehicle does not exist")
        if assigned.get("status") in DISPOSED_VEHICLE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="Cannot assign a driver to a sold or scrapped vehicle",
            )

    tyre_id = doc.get("tyre_id")
    if tyre_id:
        tyre = await db.tyres.find_one({"id": tyre_id}, {"_id": 0, "id": 1})
        if not tyre:
            raise HTTPException(status_code=400, detail="Referenced tyre does not exist")

    vendor_id = doc.get("vendor_id")
    if vendor_id:
        vendor = await db.vendors.find_one({"id": vendor_id}, {"_id": 0, "id": 1})
        if not vendor:
            raise HTTPException(status_code=400, detail="Referenced vendor does not exist")

    # OPS-04: an accident (or other record) may reference the trip it belongs to;
    # the trip must exist in the same organisation. Resolved through the scoped
    # db, so a cross-tenant trip id is rejected like a non-existent one.
    trip_id = doc.get("trip_id")
    if trip_id:
        trip = await db.trips.find_one({"id": trip_id}, {"_id": 0, "id": 1})
        if not trip:
            raise HTTPException(status_code=400, detail="Referenced trip does not exist")
