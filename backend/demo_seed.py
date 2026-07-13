"""Demo organisation seeding — realistic sample data, isolated org, periodic reset."""
import random
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from passlib.hash import bcrypt
from database import raw_db, TENANT_COLLECTIONS

DEMO_ORG_ID = "org-fleetflow-demo"
RESET_HOURS = 12

DEMO_USERS = [
    ("org_admin", "Aarav Mehta", "Organisation Super Admin"),
    ("owner", "Vikram Rao", "Managing Director"),
    ("fleet_manager", "Priya Sharma", "Fleet Manager"),
    ("operations", "Rohan Patil", "Operations Executive"),
    ("maintenance", "Suresh Kumar", "Maintenance Manager"),
    ("driver", "Ramesh Yadav", "Driver"),
    ("accounts", "Neha Joshi", "Accounts Officer"),
    ("viewer", "Anil Deshpande", "Internal Auditor"),
]

VEHICLES = [
    ("MH12 AB 1234", "Tata", "407 Gold", "LCV", "diesel", 48500),
    ("MH12 CD 5678", "Ashok Leyland", "Dost+", "LCV", "diesel", 61200),
    ("MH14 EF 9012", "Mahindra", "Bolero Pickup", "Pickup", "diesel", 83400),
    ("MH12 GH 3456", "Tata", "Ace Gold", "Mini Truck", "cng", 39800),
    ("MH14 JK 7890", "Eicher", "Pro 2049", "Truck", "diesel", 112000),
    ("MH12 LM 2468", "Maruti", "Super Carry", "Mini Truck", "cng", 27600),
]

DRIVERS = [
    ("Ramesh Yadav", "9822011001", "MH1220220001111"),
    ("Sanjay Pawar", "9822011002", "MH1220210002222"),
    ("Imran Shaikh", "9822011003", "MH1420190003333"),
    ("Ganesh More", "9822011004", "MH1220230004444"),
    ("Dinesh Kamble", "9822011005", "MH1420200005555"),
]

ROUTES = [
    ("Pune", "Mumbai", 155), ("Pune", "Nashik", 210), ("Pune", "Satara", 115),
    ("Pune", "Kolhapur", 230), ("Pune", "Aurangabad", 235), ("Pune", "Solapur", 250),
]

VENDORS = [
    ("Shree Auto Works", "Repair", "Mahesh Jadhav", "9850012345"),
    ("Apollo Tyre Point", "Tyre", "Kiran Bhosale", "9850023456"),
    ("HP Fuel Station Hadapsar", "Fuel", "Station Manager", "9850034567"),
    ("Bajaj Allianz Motor Desk", "Insurance", "Sneha Kulkarni", "9850045678"),
]


def _iso(dt):
    return dt.strftime("%Y-%m-%d")


async def _wipe_demo_data():
    for coll in TENANT_COLLECTIONS:
        if coll == "users":
            continue
        await raw_db[coll].delete_many({"org_id": DEMO_ORG_ID})


async def ensure_demo(force: bool = False):
    org = await raw_db.organizations.find_one({"id": DEMO_ORG_ID})
    now = datetime.now(timezone.utc)
    if org and not force:
        seeded = org.get("demo_seeded_at")
        try:
            age_ok = seeded and (now - datetime.fromisoformat(seeded)) < timedelta(hours=RESET_HOURS)
        except ValueError:
            age_ok = False
        if age_ok:
            return
    await _seed(now)


async def _seed(now):
    rng = random.Random(42)
    await _wipe_demo_data()
    await raw_db.organizations.update_one(
        {"id": DEMO_ORG_ID},
        {"$set": {
            "id": DEMO_ORG_ID,
            "legal_name": "FleetFlow Demo Logistics Pvt Ltd",
            "legal_name_lc": "fleetflow demo logistics pvt ltd",
            "trade_name": "FleetFlow Demo Logistics",
            "org_type": "Logistics Business",
            "fleet_ownership": "Mixed",
            "city": "Pune", "state": "Maharashtra", "country": "India",
            "currency": "INR", "timezone": "Asia/Kolkata", "fy_start_month": 4,
            "is_demo": True, "is_default": False, "onboarding_completed": True,
            "compliance_docs": ["RC", "Insurance", "Fitness", "Permit", "PUC", "Road Tax"],
            "demo_seeded_at": now.isoformat(),
        }},
        upsert=True,
    )

    # Demo users (created once, passwords never exposed)
    for role, name, designation in DEMO_USERS:
        username = f"demo_{role}"
        existing = await raw_db.users.find_one({"username": username})
        if not existing:
            await raw_db.users.insert_one({
                "id": str(uuid.uuid4()), "org_id": DEMO_ORG_ID, "username": username,
                "email": f"{username}@demo.fleetflow.app",
                "password_hash": bcrypt.hash(secrets.token_urlsafe(16)),
                "role": role, "full_name": name, "designation": designation,
                "is_active": True, "is_demo": True, "must_change_password": False,
                "created_at": now.isoformat(), "created_by": "demo_seed",
            })

    def base(extra=None):
        d = {"id": str(uuid.uuid4()), "org_id": DEMO_ORG_ID, "is_test_data": False,
             "created_at": now.isoformat(), "created_by": "demo_seed"}
        d.update(extra or {})
        return d

    await raw_db.branches.insert_one(base({
        "name": "Pune Head Office", "code": "PUN", "address": "MIDC Bhosari, Pune 411026",
        "contact_person": "Priya Sharma", "phone": "9850001111", "is_default": True,
    }))

    vendor_ids = []
    for name, vtype, contact, mobile in VENDORS:
        v = base({"name": name, "vendor_type": vtype, "primary_contact": contact,
                  "mobile": mobile, "is_active": True})
        vendor_ids.append(v["id"])
        await raw_db.vendors.insert_one(v)

    vehicle_ids = []
    for num, make, model, vtype, fuel, odo in VEHICLES:
        v = base({"vehicle_number": num, "make": make, "model": model, "vtype": vtype,
                  "fuel_type": fuel, "current_odometer": odo, "status": "active",
                  "fastag_number": f"FT{rng.randint(10**9, 10**10 - 1)}", "fastag_balance": rng.randint(200, 1500)})
        vehicle_ids.append(v["id"])
        await raw_db.vehicles.insert_one(v)

    driver_ids = []
    for i, (name, mobile, lic) in enumerate(DRIVERS):
        exp = now + timedelta(days=[400, 25, 700, 10, 200][i])
        d = base({"name": name, "mobile": mobile, "license_number": lic,
                  "license_expiry": _iso(exp), "status": "active",
                  "assigned_vehicle_id": vehicle_ids[i] if i < len(vehicle_ids) else None})
        driver_ids.append(d["id"])
        await raw_db.drivers.insert_one(d)

    # Documents with mixed expiry windows
    doc_offsets = {"RC": 900, "Insurance": 20, "Fitness": 75, "Permit": 12, "PUC": -5, "Road Tax": 400}
    for vid in vehicle_ids:
        for dt, off in doc_offsets.items():
            jitter = rng.randint(-8, 30)
            await raw_db.documents.insert_one(base({
                "vehicle_id": vid, "doc_type": dt,
                "doc_number": f"{dt[:3].upper()}-{rng.randint(100000, 999999)}",
                "issue_date": _iso(now - timedelta(days=365)),
                "expiry_date": _iso(now + timedelta(days=off + jitter)),
            }))

    # 90 days of trips + fuel
    odo_map = {vid: VEHICLES[i][5] - 9000 for i, vid in enumerate(vehicle_ids)}
    for day in range(90, 0, -1):
        date = _iso(now - timedelta(days=day))
        for vid in rng.sample(vehicle_ids, k=rng.randint(2, 4)):
            origin, dest, dist = rng.choice(ROUTES)
            opening = odo_map[vid]
            closing = opening + dist + rng.randint(-10, 25)
            odo_map[vid] = closing
            await raw_db.trips.insert_one(base({
                "date": date, "vehicle_id": vid, "driver_id": rng.choice(driver_ids),
                "origin": origin, "destination": dest, "purpose": "Delivery",
                "opening_km": opening, "closing_km": closing,
                "distance": round(closing - opening, 1), "status": "completed",
                "toll_expense": rng.choice([0, 120, 245, 380]),
                "parking_expense": rng.choice([0, 0, 50, 100]),
                "misc_expense": rng.choice([0, 0, 0, 150]),
            }))
        if day % 2 == 0:
            vid = rng.choice(vehicle_ids)
            qty = rng.randint(18, 45)
            rate = rng.uniform(89, 96)
            await raw_db.fuel_entries.insert_one(base({
                "date": date, "vehicle_id": vid, "driver_id": rng.choice(driver_ids),
                "odometer": odo_map[vid], "quantity": qty,
                "amount": round(qty * rate, 2), "station": "HP Fuel Station Hadapsar",
                "mileage": round(rng.uniform(7.5, 13.5), 2),
            }))
        if day % 5 == 0:
            await raw_db.fastag_transactions.insert_one(base({
                "date": date, "vehicle_id": rng.choice(vehicle_ids), "txn_type": "toll",
                "toll_plaza": rng.choice(["Khed Shivapur", "Talegaon", "Anewadi", "Kini"]),
                "amount": rng.choice([85, 120, 175, 240]),
            }))

    # One ongoing trip (fleet status "RUNNING")
    origin, dest, dist = ROUTES[0]
    await raw_db.trips.insert_one(base({
        "date": _iso(now), "vehicle_id": vehicle_ids[0], "driver_id": driver_ids[0],
        "origin": origin, "destination": dest, "purpose": "Delivery",
        "opening_km": odo_map[vehicle_ids[0]], "closing_km": None,
        "distance": None, "status": "ongoing", "toll_expense": 0, "parking_expense": 0, "misc_expense": 0,
    }))

    # Services & greasing
    for i, vid in enumerate(vehicle_ids):
        await raw_db.services.insert_one(base({
            "vehicle_id": vid, "service_type": "Periodic Service", "date": _iso(now - timedelta(days=40 + i * 5)),
            "odometer": odo_map[vid] - 4000, "vendor": "Shree Auto Works", "vendor_id": vendor_ids[0],
            "cost": rng.randint(3500, 9500), "next_due_date": _iso(now + timedelta(days=50 - i * 12)),
            "next_due_km": odo_map[vid] + 5000,
        }))
        await raw_db.greasings.insert_one(base({
            "vehicle_id": vid, "date": _iso(now - timedelta(days=20 + i * 3)),
            "odometer": odo_map[vid] - 1500, "cost": rng.randint(300, 700),
            "next_due_date": _iso(now + timedelta(days=25)),
        }))

    # Service tickets across the 7-stage workflow
    ticket_states = [
        ("open", {}),
        ("under_review", {"reviewed_at": now.isoformat(), "reviewed_by": "Priya Sharma"}),
        ("approved", {"reviewed_at": now.isoformat(), "reviewed_by": "Priya Sharma",
                      "approved_at": now.isoformat(), "approved_by": "Vikram Rao"}),
        ("in_repair", {"in_repair_at": now.isoformat()}),
        ("closed", {"closed_at": now.isoformat(), "closed_by": "Vikram Rao"}),
    ]
    issues = ["Clutch plate worn out", "Brake pads replacement needed", "Engine overheating on long runs",
              "Electrical wiring fault — headlights", "Suspension noise from rear axle"]
    for i, (status, extra) in enumerate(ticket_states):
        await raw_db.repairs.insert_one(base({
            "vehicle_id": vehicle_ids[i % len(vehicle_ids)], "repair_type": "major",
            "issue": issues[i], "date": _iso(now - timedelta(days=3 + i * 6)),
            "ticket_number": f"TKT-{now.year}-{9000 + i}", "ticket_category": ["Clutch", "Brake", "Engine", "Electrical", "Suspension"][i],
            "status": status, "vendor": "Shree Auto Works", "vendor_id": vendor_ids[0],
            "cost": rng.randint(2500, 18000) if status != "open" else 0,
            "downtime_days": rng.randint(1, 4), **extra,
        }))

    # Tyres
    for i, vid in enumerate(vehicle_ids[:4]):
        await raw_db.tyres.insert_one(base({
            "vehicle_id": vid, "tyre_number": f"TY-{1000 + i}", "brand": rng.choice(["Apollo", "MRF", "CEAT"]),
            "size": "155 R13", "position": rng.choice(["Front Left", "Front Right", "Rear Left", "Rear Right"]),
            "installation_date": _iso(now - timedelta(days=200)), "installation_km": 20000,
            "cost": rng.randint(3200, 5200), "status": "active",
        }))

    # One accident with insurance claim
    await raw_db.accidents.insert_one(base({
        "vehicle_id": vehicle_ids[2], "driver_id": driver_ids[2],
        "date": _iso(now - timedelta(days=35)), "location": "Mumbai-Pune Expressway, Khalapur",
        "description": "Minor rear-end collision at toll queue", "fir_number": "FIR/2026/04512",
        "insurance_claim_number": "CLM-88231", "claim_status": "Filed",
        "repair_cost": 42000, "claim_amount": 38000, "settlement_amount": 0,
    }))

    # One open downtime
    await raw_db.downtimes.insert_one(base({
        "vehicle_id": vehicle_ids[4], "reason": "service", "start_date": _iso(now - timedelta(days=2)),
        "end_date": None, "status": "open",
    }))

    # Manual expenses
    for cat, desc, amt, off in [
        ("Insurance", "Annual comprehensive policy renewal", 28500, 60),
        ("Permits", "National permit renewal", 15200, 45),
        ("Washing", "Fleet washing — monthly contract", 2400, 12),
        ("Parking", "Night parking, Bhosari yard", 3000, 8),
        ("Fines & Penalties", "Overspeed e-challan MH12 AB 1234", 1000, 20),
        ("GPS Subscription", "GPS tracker annual subscription (6 vehicles)", 7200, 30),
    ]:
        await raw_db.expenses.insert_one(base({
            "vehicle_id": rng.choice(vehicle_ids), "category": cat, "date": _iso(now - timedelta(days=off)),
            "amount": amt, "description": desc,
        }))

    # Budgets for current month
    month = now.strftime("%Y-%m")
    for cat, amt in [("Fuel", 90000), ("Service", 25000), ("Repair", 30000), ("Tyres", 15000), ("Trip", 20000)]:
        await raw_db.budgets.insert_one(base({"category": cat, "month": month, "amount": amt}))
