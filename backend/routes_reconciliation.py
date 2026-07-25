"""
DI-03 — Reconciliation API.

Thin endpoints over the canonical ``reconciliation`` service. They exist so an
operator (or an automated check) can independently verify that the totals shown
elsewhere in the product are recomputable from source records, and can see the
FASTag balance-cache drift, duplicate and unmatched counts.

Access is gated on the reports module (finance/management/admin/auditor), the
same tier that can already see aggregate financial data.
"""
from fastapi import APIRouter, Depends, HTTPException
from auth import require_module
import reconciliation

router = APIRouter(tags=["reconciliation"])


def _include_test(user):
    return user.get("role") == "test"


@router.get("/reconciliation/vehicle/{vehicle_id}")
async def reconcile_vehicle(vehicle_id: str, start_date: str = None, end_date: str = None,
                            user=Depends(require_module("reports"))):
    include_test = _include_test(user)
    return {
        "cost_breakdown": await reconciliation.vehicle_cost_breakdown(
            vehicle_id, start_date, end_date, include_test),
        "fuel": await reconciliation.fuel_reconciliation(vehicle_id),
        "maintenance": await reconciliation.maintenance_reconciliation(vehicle_id),
        "payments": await reconciliation.payment_reconciliation(vehicle_id),
        "fastag": await reconciliation.fastag_reconciliation(vehicle_id),
    }


@router.get("/reconciliation/fastag")
async def reconcile_fastag(user=Depends(require_module("reports"))):
    return await reconciliation.fastag_reconciliation()


@router.get("/reconciliation/maintenance")
async def reconcile_maintenance(user=Depends(require_module("reports"))):
    return await reconciliation.maintenance_reconciliation()


@router.get("/reconciliation/payments")
async def reconcile_payments(user=Depends(require_module("reports"))):
    return await reconciliation.payment_reconciliation()


@router.get("/reconciliation/trip/{trip_id}")
async def reconcile_trip(trip_id: str, user=Depends(require_module("reports"))):
    result = await reconciliation.trip_economics(trip_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return result
