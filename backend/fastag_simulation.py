"""
FASTAG-01 — Demo-only FASTag simulation.

``POST /fastag/sync/{vehicle_id}`` fabricates FASTag toll/recharge activity
because no public NPCI/bank FASTag API exists. Before FASTAG-01 it was
``require_user`` and available to **every organisation**: any authenticated user
could generate 4–8 random toll transactions plus a random recharge for a real
vehicle and **overwrite its ``fastag_balance`` with a random number**
(``random.uniform(250, 2800)``). That is fabricated financial activity and
silent balance corruption in a real tenant.

This module draws the line between three clearly separate paths:

* **Demo simulation** — synthetic data, allowed *only* inside the canonical demo
  organisation, fail-closed everywhere else. This module.
* **Manual import** — a user entering a real transaction they hold a receipt for,
  via ``POST /fastag`` (the generic create). Unchanged, tenant-scoped, real.
* **Future live-provider integration** — a real bank/NPCI feed. Does not exist;
  ``PROVIDER_INTEGRATION_AVAILABLE`` is ``False`` so any accidental call to a
  provider path fails closed rather than silently doing nothing.

Design rules
------------
* **Fail closed off the demo org.** A non-demo caller is refused with 403; no
  transaction is ever written and no balance is ever touched outside demo.
* **Idempotent.** A run carries a batch key; replaying the same key returns the
  original result and writes nothing new, so a double-click or a retry cannot
  double the fabricated activity.
* **No random balance.** The balance is *computed* from the vehicle's FASTag
  transactions (recharges − tolls), so a replay is stable and the number is not
  invented.
"""
import hashlib
import random
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException

from demo_seed import DEMO_ORG_ID

# The one source marker for simulated rows. Distinct from "auto_sync" (the old
# marker) and from manual entries (no source), so simulated data is always
# identifiable and can never be confused with a real import.
SIMULATION_SOURCE = "demo_simulation"

# There is no live provider yet. Any code path that would call one must check
# this and fail closed rather than pretend.
PROVIDER_INTEGRATION_AVAILABLE = False

# Bounded, sane synthetic values — never free-form amounts.
TOLL_PLAZAS = ["Khed Shivapur Plaza", "Talegaon Plaza", "Anewadi Plaza", "Tasawade Plaza",
               "Kini Plaza", "Vashi Plaza", "Charoti Plaza", "Dahisar Plaza"]
TOLL_AMOUNTS = [45, 65, 85, 105, 140, 165, 210, 240, 330]
RECHARGE_AMOUNTS = [500, 1000, 2000]
MAX_TOLLS_PER_RUN = 8
MAX_LOOKBACK_DAYS = 30


def simulation_allowed(user: dict) -> bool:
    """True only for a user of the canonical demo organisation.

    Both markers must agree: ``is_demo`` and membership of ``DEMO_ORG_ID``. A
    real user cannot satisfy this, and a stray ``is_demo`` flag on a non-demo org
    cannot either — the simulation is pinned to the one demo tenant.
    """
    return bool(user.get("is_demo")) and user.get("org_id") == DEMO_ORG_ID


def assert_simulation_allowed(user: dict):
    """Fail closed unless the caller is in the demo organisation."""
    if not simulation_allowed(user):
        raise HTTPException(
            status_code=403,
            detail=("FASTag sync is a demo-only simulation and cannot run for a "
                    "real organisation. Enter FASTag transactions manually."),
        )


def _batch_key(vehicle_id: str, provided) -> str:
    """Stable idempotency key for a run.

    A caller may supply one (so a retried request is recognised); otherwise a
    fresh random key is used, which still lets a within-request replay be
    detected by the stored marker.
    """
    if provided:
        raw = f"{vehicle_id}:{provided}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    return uuid.uuid4().hex


def _seeded_rng(batch_key: str) -> random.Random:
    """Deterministic RNG from the batch key, so a replay reproduces the run."""
    return random.Random(int(hashlib.sha256(batch_key.encode()).hexdigest(), 16))


def build_simulated_batch(vehicle_id: str, user: dict, batch_key: str) -> list:
    """Return the synthetic transactions for a run. Deterministic in ``batch_key``.

    Every row is marked with ``SIMULATION_SOURCE`` and the batch key, so it is
    identifiable, idempotent and never mistakable for a real import.
    """
    rng = _seeded_rng(batch_key)
    now = datetime.now(timezone.utc)
    rows = []

    def _row(txn_type, amount, plaza, note):
        day = now - timedelta(days=rng.randint(0, MAX_LOOKBACK_DAYS))
        return {
            "id": str(uuid.uuid4()),
            "vehicle_id": vehicle_id,
            "txn_type": txn_type,
            "date": day.strftime("%Y-%m-%d"),
            "toll_plaza": plaza,
            "amount": float(amount),
            "notes": note,
            "source": SIMULATION_SOURCE,
            "sim_batch": batch_key,
            "created_at": now.isoformat(),
            "created_by": user["user_id"],
        }

    for _ in range(rng.randint(4, MAX_TOLLS_PER_RUN)):
        rows.append(_row("toll", rng.choice(TOLL_AMOUNTS), rng.choice(TOLL_PLAZAS), None))
    if rng.random() < 0.7:
        rows.append(_row("recharge", rng.choice(RECHARGE_AMOUNTS), None, "Auto recharge"))
    return rows


def computed_balance(transactions: list) -> float:
    """Balance derived from the transactions themselves — never invented.

    Recharges add, tolls subtract. A replay over the same rows yields the same
    number, so the balance cannot drift on retry.
    """
    total = 0.0
    for t in transactions:
        amt = t.get("amount") or 0
        total += amt if t.get("txn_type") == "recharge" else -amt
    return round(total, 2)
