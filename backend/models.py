from pydantic import BaseModel, model_validator
from typing import ClassVar, Optional, List

from tenant_policy import reject_protected_fields


class TenantSafeModel(BaseModel):
    """Base for request models: rejects server-owned fields in the request body.

    TEN-01. Pydantic's default ``extra="ignore"`` meant a body containing
    ``org_id`` was silently dropped — the write was safe, but the client was told
    it had succeeded as sent. This validator rejects protected fields explicitly
    (HTTP 400) so ownership injection is a visible error.

    Unknown *non-protected* fields are still ignored rather than forbidden. A
    blanket ``extra="forbid"`` would turn every harmless frontend/model drift
    into a 422 without adding tenant safety, so it is deliberately not used;
    protected-field rejection is the part that carries the security property.

    Subclasses that legitimately own a protected field (e.g. ``UserCreate`` and
    ``role``) declare it in ``allow_protected``. It is a ``ClassVar`` so it stays
    policy metadata and never becomes a request field of its own.
    """

    allow_protected: ClassVar[frozenset] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _reject_protected(cls, data):
        if isinstance(data, dict):
            reject_protected_fields(data, allow=cls.allow_protected)
        return data


class OrgRegister(TenantSafeModel):
    org: dict
    admin: dict
    branch: Optional[dict] = None
    preferences: Optional[dict] = None
    compliance_docs: Optional[List[str]] = None
    fleet_profile: Optional[dict] = None


class UserCreate(TenantSafeModel):
    # The user-administration path legitimately sets role and the initial
    # password. It is permission-checked in auth.create_user, which also pins the
    # new user's org_id to the caller's organisation and rejects role escalation.
    allow_protected: ClassVar[frozenset] = frozenset({"role", "password"})

    username: str
    password: str
    role: str
    full_name: str
    is_active: Optional[bool] = True


class UserUpdate(TenantSafeModel):
    # Role changes are permitted here and nowhere else; auth.update_user enforces
    # who may make them. org_id is deliberately absent — users are never moved
    # between organisations through this endpoint.
    allow_protected: ClassVar[frozenset] = frozenset({"role"})

    role: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordChange(TenantSafeModel):
    current_password: str
    new_password: str


class LoginRequest(TenantSafeModel):
    # "password" is a protected field name everywhere else; login is the one
    # place a caller is supposed to send one.
    allow_protected: ClassVar[frozenset] = frozenset({"password"})

    username: str
    password: str


class VehicleCreate(TenantSafeModel):
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


class DriverCreate(TenantSafeModel):
    name: str
    employee_number: Optional[str] = None
    mobile: Optional[str] = None
    address: Optional[str] = None
    aadhaar: Optional[str] = None
    license_number: Optional[str] = None
    license_expiry: Optional[str] = None
    license_categories: Optional[List[str]] = []
    skills: Optional[List[str]] = []
    esi_number: Optional[str] = None
    pf_uan_number: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    emergency_contact_mobile: Optional[str] = None
    assigned_vehicle_id: Optional[str] = None
    status: Optional[str] = "active"
    photo_file_id: Optional[str] = None
    # Exit management fields (Phase 1)
    exit_date: Optional[str] = None
    exit_reason: Optional[str] = None


class DocumentCreate(TenantSafeModel):
    vehicle_id: str
    doc_type: str
    doc_number: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    file_id: Optional[str] = None
    notes: Optional[str] = None


class TripCreate(TenantSafeModel):
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


class TripPlan(TenantSafeModel):
    """OPS-01 — plan a trip before a vehicle/driver is committed.

    Unlike ``TripCreate`` (the quick full-entry path), planning is deliberately
    permissive about what is known up front: a planned trip may have no vehicle,
    no driver and no opening odometer yet — those are supplied through the
    dedicated assign/dispatch actions. Financial fields are intentionally absent;
    they belong to the completion/settlement steps.
    """
    date: str
    vehicle_id: Optional[str] = None
    driver_id: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    purpose: Optional[str] = None
    planned_start_date: Optional[str] = None
    planned_end_date: Optional[str] = None
    opening_km: Optional[float] = None
    notes: Optional[str] = None


class FuelCreate(TenantSafeModel):
    date: str
    vehicle_id: str
    driver_id: Optional[str] = None
    odometer: float
    quantity: float
    amount: float
    station: Optional[str] = None
    file_id: Optional[str] = None
    notes: Optional[str] = None


class ServiceCreate(TenantSafeModel):
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


class RepairCreate(TenantSafeModel):
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
    # Ticket fields (Checkpoint 4)
    ticket_category: Optional[str] = None  # Engine | Clutch | Brake | Electrical | Suspension | Body Damage | Other
    photo_file_ids: Optional[List[str]] = []
    vendor_id: Optional[str] = None


class VendorCreate(TenantSafeModel):
    name: str
    vendor_type: str  # Repair | Tyre | Showroom | Breakdown | Insurance | Fastag | Fuel | Other
    primary_contact: Optional[str] = None
    mobile: Optional[str] = None
    alternate_contact: Optional[str] = None
    alternate_mobile: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = True


class TyreCreate(TenantSafeModel):
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


class TyreEventCreate(TenantSafeModel):
    tyre_id: str
    vehicle_id: Optional[str] = None
    event_type: str  # puncture | rotation | retreading | replacement
    date: str
    odometer: Optional[float] = None
    cost: Optional[float] = 0
    notes: Optional[str] = None


class AccidentCreate(TenantSafeModel):
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


class FastagTxnCreate(TenantSafeModel):
    vehicle_id: str
    txn_type: str  # toll | recharge
    date: str
    toll_plaza: Optional[str] = None
    amount: float
    notes: Optional[str] = None


class DowntimeCreate(TenantSafeModel):
    vehicle_id: str
    reason: str  # service | breakdown | accident | compliance | other
    start_date: str
    end_date: Optional[str] = None
    notes: Optional[str] = None


class ExpenseCreate(TenantSafeModel):
    vehicle_id: str
    category: str
    date: str
    amount: float
    description: Optional[str] = None
    file_id: Optional[str] = None


class GreasingCreate(TenantSafeModel):
    vehicle_id: str
    date: str
    odometer: Optional[float] = None
    responsible_person: Optional[str] = None
    cost: Optional[float] = 0
    next_due_date: Optional[str] = None
    next_due_km: Optional[float] = None
    file_id: Optional[str] = None
    notes: Optional[str] = None


class ComplianceContactCreate(TenantSafeModel):
    compliance_type: str
    contact_person_name: str
    mobile: str
    email: Optional[str] = None
    vendor_name: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = True


class CalendarEventCreate(TenantSafeModel):
    title: str
    date: str
    time: Optional[str] = None
    vehicle_id: Optional[str] = None
    driver_id: Optional[str] = None
    responsible_person: Optional[str] = None
    notes: Optional[str] = None
    recurrence: Optional[str] = None  # weekly | monthly | yearly
    recurrence_until: Optional[str] = None
