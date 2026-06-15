from pydantic import BaseModel
from typing import Optional, List


class VehicleCreate(BaseModel):
    vehicle_number: str
    make: Optional[str] = None
    model: Optional[str] = None
    vtype: Optional[str] = None
    fuel_type: Optional[str] = None
    chassis_number: Optional[str] = None
    engine_number: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    current_odometer: Optional[float] = 0
    status: Optional[str] = "active"
    fastag_number: Optional[str] = None
    fastag_bank: Optional[str] = None
    fastag_balance: Optional[float] = 0
    photo_file_ids: Optional[List[str]] = []
    notes: Optional[str] = None
    # Disposal fields (Phase 1)
    disposal_date: Optional[str] = None
    sale_value: Optional[float] = None
    buyer_name: Optional[str] = None
    buyer_contact: Optional[str] = None
    disposal_remarks: Optional[str] = None


class DriverCreate(BaseModel):
    name: str
    mobile: Optional[str] = None
    address: Optional[str] = None
    aadhaar: Optional[str] = None
    license_number: Optional[str] = None
    license_expiry: Optional[str] = None
    assigned_vehicle_id: Optional[str] = None
    status: Optional[str] = "active"
    photo_file_id: Optional[str] = None
    # Exit management fields (Phase 1)
    exit_date: Optional[str] = None
    exit_reason: Optional[str] = None


class DocumentCreate(BaseModel):
    vehicle_id: str
    doc_type: str
    doc_number: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    file_id: Optional[str] = None
    notes: Optional[str] = None


class TripCreate(BaseModel):
    date: str
    vehicle_id: str
    driver_id: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    purpose: Optional[str] = None
    opening_km: float
    closing_km: Optional[float] = None
    toll_expense: Optional[float] = 0
    parking_expense: Optional[float] = 0
    misc_expense: Optional[float] = 0
    file_id: Optional[str] = None
    notes: Optional[str] = None


class FuelCreate(BaseModel):
    date: str
    vehicle_id: str
    driver_id: Optional[str] = None
    odometer: float
    quantity: float
    amount: float
    station: Optional[str] = None
    file_id: Optional[str] = None
    notes: Optional[str] = None


class ServiceCreate(BaseModel):
    vehicle_id: str
    service_type: str
    date: str
    odometer: Optional[float] = None
    vendor: Optional[str] = None
    responsible_person: Optional[str] = None
    cost: Optional[float] = 0
    file_id: Optional[str] = None
    next_due_date: Optional[str] = None
    next_due_km: Optional[float] = None
    notes: Optional[str] = None


class RepairCreate(BaseModel):
    vehicle_id: str
    repair_type: str  # minor | major
    issue: str
    date: str
    vendor: Optional[str] = None
    cost: Optional[float] = 0
    downtime_days: Optional[float] = 0
    root_cause: Optional[str] = None
    file_id: Optional[str] = None
    notes: Optional[str] = None


class TyreCreate(BaseModel):
    vehicle_id: str
    tyre_number: str
    brand: Optional[str] = None
    size: Optional[str] = None
    position: Optional[str] = None
    installation_date: Optional[str] = None
    installation_km: Optional[float] = None
    cost: Optional[float] = 0
    status: Optional[str] = "active"
    notes: Optional[str] = None


class TyreEventCreate(BaseModel):
    tyre_id: str
    vehicle_id: Optional[str] = None
    event_type: str  # puncture | rotation | retreading | replacement
    date: str
    odometer: Optional[float] = None
    cost: Optional[float] = 0
    notes: Optional[str] = None


class AccidentCreate(BaseModel):
    vehicle_id: str
    driver_id: Optional[str] = None
    date: str
    time: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    fir_number: Optional[str] = None
    file_id: Optional[str] = None
    insurance_claim_number: Optional[str] = None
    claim_status: Optional[str] = None
    repair_cost: Optional[float] = 0
    claim_amount: Optional[float] = 0
    settlement_amount: Optional[float] = 0


class FastagTxnCreate(BaseModel):
    vehicle_id: str
    txn_type: str  # toll | recharge
    date: str
    toll_plaza: Optional[str] = None
    amount: float
    notes: Optional[str] = None


class DowntimeCreate(BaseModel):
    vehicle_id: str
    reason: str  # service | breakdown | accident | compliance | other
    start_date: str
    end_date: Optional[str] = None
    notes: Optional[str] = None


class ExpenseCreate(BaseModel):
    vehicle_id: str
    category: str
    date: str
    amount: float
    description: Optional[str] = None
    file_id: Optional[str] = None
