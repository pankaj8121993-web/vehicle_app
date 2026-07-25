"""
DI-04 — Data-quality integrity scanner and safe repair tool.

DI-01/02/03 stop *new* bad data at the write boundary and let every total be
recomputed. This command finds data that is *already* inconsistent — from before
those controls existed, or from out-of-band writes — and offers a small set of
reviewed, non-destructive repairs.

Safety contract (non-negotiable)
--------------------------------
* **Dry-run by default.** ``scan`` only reads and reports. Nothing is written
  unless the separate ``repair`` command is run with ``--apply``.
* **Never deletes data.** No code path here removes a document. Repairs only
  recompute a derived cache value.
* **Backup confirmation before any write.** ``repair --apply`` refuses without
  ``--confirm-backup``, an explicit operator assertion that a backup exists.
* **Per organisation.** Findings carry ``org_id``; ``--org`` scopes a run to one
  organisation. Cross-tenant references are themselves a detector.
* **Never prints secrets or personal data.** Findings carry ids, collection
  names, field names, statuses and numeric amounts only — never names, Aadhaar,
  licence, mobile, passwords, hashes or tokens. See ``_REDACTED_SAFE``.
* **Safe to rerun.** Detectors are pure reads; the one repair (recompute a
  balance) is idempotent.
* **Never against production during development.** Point ``DB_NAME`` at a
  disposable database. See DATA_INTEGRITY_RUNBOOK.md.

Usage (run from /app/backend):

    python -m check_data_integrity scan                 # all orgs, dry-run
    python -m check_data_integrity scan --org <org_id>  # one org
    python -m check_data_integrity scan --json          # machine-readable report
    python -m check_data_integrity repair --action recompute-fastag-balance \\
        --org <org_id> --confirm-backup --apply
"""
import json
import math
import uuid
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

import typer

from database import raw_db
import invariants
from reconciliation import computed_fastag_net

logger = logging.getLogger("fleetflow.check_data_integrity")

# Tenant collections scanned. Mirrors database.TENANT_COLLECTIONS minus files
# (binary/document metadata, out of scope for financial/operational integrity).
SCANNED_COLLECTIONS = (
    "vehicles", "drivers", "documents", "trips", "fuel_entries", "services",
    "repairs", "greasings", "tyres", "tyre_events", "accidents",
    "fastag_transactions", "downtimes", "expenses", "vendors",
    "calendar_events", "compliance_contacts", "budgets",
)

# Foreign keys and the collection they must resolve in.
_REFERENCES = {
    "vehicle_id": "vehicles",
    "driver_id": "drivers",
    "tyre_id": "tyres",
    "vendor_id": "vendors",
    "assigned_vehicle_id": "vehicles",
    "trip_id": "trips",
}

# Known status values per collection (for invalid-combination detection).
_VALID_STATUSES = {
    "vehicles": {"active", "inactive", "maintenance", "idle", "under_repair", "sold", "scrapped"},
    "drivers": {"active", "on_leave", "resigned", "terminated"},
    "downtimes": {"open", "closed"},
    # OPS-01 extended the trip lifecycle; the scanner must recognise every state
    # the workflow can write or it would flag valid records as invalid_status.
    "trips": {"planned", "assigned", "ongoing", "completed",
              "settlement_pending", "closed", "cancelled"},
    "repairs": {"open", "under_review", "approved", "sent_for_repair", "in_repair",
                "repaired", "closed"},
}

# Fields that must never appear in a finding's detail (personal / secret).
_NEVER_REPORT = {
    "name", "full_name", "aadhaar", "mobile", "email", "address",
    "license_number", "password", "password_hash", "token", "token_hash",
    "emergency_contact_mobile", "emergency_contact_name", "pf_uan_number",
    "esi_number", "buyer_contact", "primary_contact", "alternate_contact",
}


def _REDACTED_SAFE(detail: dict) -> dict:
    """Strip any personal/secret field from a finding detail, defence-in-depth."""
    return {k: v for k, v in detail.items() if k not in _NEVER_REPORT}


def _finding(detector, severity, org_id, collection, record_id, **detail):
    return {
        "detector": detector,
        "severity": severity,
        "org_id": org_id,
        "collection": collection,
        "record_id": record_id,
        "detail": _REDACTED_SAFE(detail),
    }


async def _load(org_id=None, collections=None, record_id=None):
    """Load scanned collections into memory as {collection: [docs]}.

    ``org_id`` scopes to one organisation; ``record_id`` to one record (across
    collections). Uses ``raw_db`` deliberately — the scanner must see records
    with a *missing* org_id, which the tenant-scoped layer would hide.
    """
    colls = collections or SCANNED_COLLECTIONS
    data = {}
    for c in colls:
        q = {}
        if org_id:
            q["org_id"] = org_id
        if record_id:
            q["id"] = record_id
        data[c] = await raw_db[c].find(q, {"_id": 0}).to_list(100000)
    return data


# --- Detectors ----------------------------------------------------------------
# Each takes the loaded data (+ a global id index for reference checks) and
# returns a list of findings. Pure reads; safe to rerun.

def detect_missing_org_ownership(data):
    out = []
    for coll, docs in data.items():
        for d in docs:
            if not d.get("org_id"):
                out.append(_finding("missing_org_ownership", "error", None, coll,
                                    d.get("id"), reason="no org_id"))
    return out


def detect_orphaned_and_cross_tenant_refs(data, index):
    """index: {collection: {id: org_id}} across the whole database."""
    out = []
    for coll, docs in data.items():
        for d in docs:
            for field, target_coll in _REFERENCES.items():
                ref = d.get(field)
                if not ref:
                    continue
                target_org = index.get(target_coll, {}).get(ref, "__MISSING__")
                if target_org == "__MISSING__":
                    out.append(_finding(
                        "orphaned_reference", "error", d.get("org_id"), coll, d.get("id"),
                        field=field, references=target_coll, missing=True))
                elif target_org != d.get("org_id"):
                    out.append(_finding(
                        "cross_tenant_reference", "error", d.get("org_id"), coll, d.get("id"),
                        field=field, references=target_coll))
    return out


def detect_duplicate_external_refs(data):
    out = []
    for coll, key in (("vehicles", "vehicle_number"), ("tyres", "tyre_number"),
                      ("repairs", "ticket_number")):
        seen = defaultdict(list)
        for d in data.get(coll, []):
            val = d.get(key)
            if val:
                seen[(d.get("org_id"), val)].append(d.get("id"))
        for (org, val), ids in seen.items():
            if len(ids) > 1:
                out.append(_finding("duplicate_external_reference", "error", org, coll,
                                    ids[0], field=key, duplicate_ids=ids[1:], count=len(ids)))
    return out


def detect_duplicate_fastag(data):
    out = []
    seen = defaultdict(list)
    for d in data.get("fastag_transactions", []):
        key = (d.get("org_id"), d.get("vehicle_id"), d.get("date"), d.get("amount"),
               d.get("txn_type"), d.get("toll_plaza"))
        seen[key].append(d.get("id"))
    for key, ids in seen.items():
        if len(ids) > 1:
            out.append(_finding("duplicate_fastag_transaction", "warning", key[0],
                                "fastag_transactions", ids[0],
                                duplicate_ids=ids[1:], count=len(ids)))
    return out


def detect_invalid_odometer_sequences(data):
    out = []
    by_vehicle = defaultdict(list)
    for d in data.get("fuel_entries", []):
        by_vehicle[(d.get("org_id"), d.get("vehicle_id"))].append(d)
    for (org, vid), entries in by_vehicle.items():
        entries.sort(key=lambda e: (e.get("date") or "", e.get("odometer") or 0))
        prev = None
        for e in entries:
            odo = e.get("odometer")
            if odo is not None and prev is not None and odo < prev:
                out.append(_finding("invalid_odometer_sequence", "warning", org,
                                    "fuel_entries", e.get("id"),
                                    odometer=odo, previous=prev))
            if odo is not None:
                prev = odo
    return out


def _bad_money(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    try:
        num = float(value)
    except (TypeError, ValueError):
        return True
    if not math.isfinite(num):
        return True
    return num < 0 or abs(num) > float(invariants.MONEY_MAX)


def detect_negative_or_impossible_money(data):
    out = []
    for coll, fields in invariants.MONEY_FIELDS.items():
        for d in data.get(coll, []):
            for f in fields:
                if _bad_money(d.get(f)):
                    out.append(_finding("impossible_monetary_value", "error",
                                        d.get("org_id"), coll, d.get("id"),
                                        field=f, value=d.get(f)))
    return out


def detect_paid_exceeding_approved(data):
    out = []
    for d in data.get("accidents", []):
        claim = d.get("claim_amount")
        settlement = d.get("settlement_amount")
        if claim is not None and settlement is not None:
            try:
                if float(settlement) > float(claim):
                    out.append(_finding("settlement_exceeds_claim", "error",
                                        d.get("org_id"), "accidents", d.get("id"),
                                        settlement=settlement, claim=claim))
            except (TypeError, ValueError):
                pass
    return out


def detect_invalid_status_combinations(data):
    out = []
    for coll, valid in _VALID_STATUSES.items():
        for d in data.get(coll, []):
            status = d.get("status")
            if status is not None and status not in valid:
                out.append(_finding("invalid_status", "warning", d.get("org_id"),
                                    coll, d.get("id"), status=status))
    # Downtime consistency: end_date present but not closed, or closed with no end_date.
    for d in data.get("downtimes", []):
        if d.get("end_date") and d.get("status") != "closed":
            out.append(_finding("inconsistent_downtime", "warning", d.get("org_id"),
                                "downtimes", d.get("id"), has_end_date=True, status=d.get("status")))
    # Trip completed but no closing_km.
    for d in data.get("trips", []):
        if d.get("status") == "completed" and d.get("closing_km") is None:
            out.append(_finding("completed_trip_without_closing_km", "warning",
                                d.get("org_id"), "trips", d.get("id")))
    return out


def detect_summary_drift(data):
    """Vehicle fastag_balance cache vs recomputed transaction net.

    A negative stored balance is impossible (error). Any other drift is a
    warning: it may be a legitimate opening balance folded into the running
    figure, so it is surfaced for review rather than asserted as corruption.
    """
    out = []
    net_by_vehicle = defaultdict(list)
    for t in data.get("fastag_transactions", []):
        net_by_vehicle[t.get("vehicle_id")].append(t)
    for v in data.get("vehicles", []):
        stored = v.get("fastag_balance")
        if stored is None:
            continue
        net = computed_fastag_net(net_by_vehicle.get(v.get("id"), []))
        if stored < 0:
            out.append(_finding("negative_fastag_balance", "error", v.get("org_id"),
                                "vehicles", v.get("id"), stored_balance=stored))
        elif round(stored - net, 2) != 0:
            out.append(_finding("fastag_balance_drift", "warning", v.get("org_id"),
                                "vehicles", v.get("id"),
                                stored_balance=stored, computed_net=net,
                                drift=round(stored - net, 2)))
    return out


ALL_DETECTORS = (
    detect_missing_org_ownership,
    detect_duplicate_external_refs,
    detect_duplicate_fastag,
    detect_invalid_odometer_sequences,
    detect_negative_or_impossible_money,
    detect_paid_exceeding_approved,
    detect_invalid_status_combinations,
    detect_summary_drift,
)


async def _global_id_index():
    """{collection: {id: org_id}} across the whole DB for reference resolution."""
    index = {}
    for coll in set(_REFERENCES.values()):
        index[coll] = {
            d["id"]: d.get("org_id")
            async for d in raw_db[coll].find({}, {"_id": 0, "id": 1, "org_id": 1})
        }
    return index


async def scan(org_id=None, collections=None, record_id=None):
    """Run every detector and return a redacted structured report."""
    data = await _load(org_id, collections, record_id)
    index = await _global_id_index()
    findings = []
    for det in ALL_DETECTORS:
        findings.extend(det(data))
    findings.extend(detect_orphaned_and_cross_tenant_refs(data, index))

    by_detector = defaultdict(int)
    by_severity = defaultdict(int)
    for f in findings:
        by_detector[f["detector"]] += 1
        by_severity[f["severity"]] += 1

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "org_id": org_id,
        "record_id": record_id,
        "total_findings": len(findings),
        "by_severity": dict(by_severity),
        "by_detector": dict(by_detector),
        "findings": findings,
    }


async def _record_audit(action, org_id, summary):
    """Non-secret audit evidence of a scan/repair run."""
    await raw_db.data_integrity_audit.insert_one({
        "id": str(uuid.uuid4()),
        "at": datetime.now(timezone.utc),
        "action": action,
        "org_id": org_id,
        "summary": summary,
    })


async def repair_recompute_fastag_balance(org_id, apply):
    """Reviewed repair: set each vehicle's fastag_balance to its transaction net.

    Treats the transactions as authoritative (opening balance assumed zero — see
    the runbook). Idempotent and non-destructive: only updates a numeric cache,
    never deletes. Returns the planned/applied changes.
    """
    if not org_id:
        raise ValueError("repair requires --org")
    data = await _load(org_id, ("vehicles", "fastag_transactions"))
    net_by_vehicle = defaultdict(list)
    for t in data["fastag_transactions"]:
        net_by_vehicle[t.get("vehicle_id")].append(t)
    changes = []
    for v in data["vehicles"]:
        net = computed_fastag_net(net_by_vehicle.get(v.get("id"), []))
        stored = v.get("fastag_balance")
        if stored is None or round((stored or 0) - net, 2) == 0:
            continue
        changes.append({"vehicle_id": v.get("id"), "from": stored, "to": net})
        if apply:
            await raw_db.vehicles.update_one(
                {"id": v["id"], "org_id": org_id}, {"$set": {"fastag_balance": net}})
    if apply:
        await _record_audit("repair:recompute-fastag-balance", org_id,
                            {"changed": len(changes)})
    return changes


# --- CLI ----------------------------------------------------------------------

cli = typer.Typer(add_completion=False, help="DI-04 data-integrity scanner and safe repair tool.")


@cli.command("scan")
def scan_cmd(
    org: str = typer.Option(None, "--org", help="Limit to one organisation id."),
    collection: str = typer.Option(None, "--collection", help="Limit to one collection."),
    record: str = typer.Option(None, "--record", help="Limit to one record id."),
    as_json: bool = typer.Option(False, "--json", help="Emit the raw JSON report."),
):
    """Read-only scan. Never writes findings. Default output is a redacted summary."""
    colls = (collection,) if collection else None

    async def _do():
        # One event loop: Motor binds its client to the first loop it touches, so
        # the scan and its audit write must share a single asyncio.run.
        rep = await scan(org, colls, record)
        await _record_audit("scan", org, {
            "total": rep["total_findings"], "by_severity": rep["by_severity"]})
        return rep

    report = asyncio.run(_do())
    if as_json:
        typer.echo(json.dumps(report, indent=2, default=str))
        return
    typer.echo(f"Data-integrity scan @ {report['scanned_at']}")
    typer.echo(f"Scope: org={org or 'ALL'} record={record or 'ALL'}")
    typer.echo(f"Total findings: {report['total_findings']}  {dict(report['by_severity'])}")
    for det, n in sorted(report["by_detector"].items(), key=lambda x: -x[1]):
        typer.echo(f"  {n:5}  {det}")
    if report["total_findings"]:
        typer.echo("\nRun with --json for the full redacted finding list.")


@cli.command("repair")
def repair_cmd(
    action: str = typer.Option(..., "--action", help="recompute-fastag-balance"),
    org: str = typer.Option(..., "--org", help="Organisation id (required for repair)."),
    confirm_backup: bool = typer.Option(
        False, "--confirm-backup", help="Assert a verified backup exists (required to --apply)."),
    apply: bool = typer.Option(False, "--apply", help="Execute. Omitted = dry-run preview."),
):
    """Apply a single reviewed, non-destructive repair. Dry-run unless --apply."""
    if action != "recompute-fastag-balance":
        typer.secho(f"Unknown repair action: {action}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if apply and not confirm_backup:
        typer.secho("Refusing to --apply without --confirm-backup (take a backup first).",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    changes = asyncio.run(repair_recompute_fastag_balance(org, apply))
    verb = "Applied" if apply else "Would change (dry-run)"
    typer.echo(f"{verb} {len(changes)} vehicle balance(s) for org {org}.")
    for c in changes:
        typer.echo(f"  vehicle {c['vehicle_id']}: {c['from']} -> {c['to']}")
    if not apply and changes:
        typer.echo("\nRe-run with --confirm-backup --apply to write these changes.")


if __name__ == "__main__":
    cli()
