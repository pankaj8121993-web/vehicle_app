# FleetFlow — Tenant-Scoped File Security (FILE-01)

**Status:** Implemented on `feature/file-01-tenant-file-security`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. Threat addressed

### 1.1 Cross-tenant file disclosure (the primary defect, P0)

`files` was **not** listed in `database.TENANT_COLLECTIONS`. Consequences:

* File records carried **no `org_id`** at all.
* `db.files` resolved to an unscoped collection, so `TenantCollection._scope()`
  added nothing to the filter.
* `GET /api/files/{file_id}` therefore matched on `id` alone:

```python
record = await db.files.find_one({"id": file_id, "is_deleted": False})
```

**Any authenticated user of any organisation could download any other
organisation's file** — RC books, insurance documents, driver Aadhaar scans,
accident photographs — given only a file id. Ids are UUIDs, but they are handed
out in API responses (`photo_file_ids`, `file_id` on every record), so this was
reachable, not merely theoretical: an org-A user who ever saw an id could read
the object.

### 1.2 Response-header injection and stored XSS

The download path built:

```python
headers={"Content-Disposition": f'inline; filename="{record["original_filename"]}"'}
```

`original_filename` was stored verbatim from the client. A filename containing a
quote broke out of the quoted-string; one containing CR/LF injected arbitrary
response headers. Worse, `media_type` came from the client's declared
`Content-Type` and the disposition was **`inline`** — so uploading a file
declared as `text/html` yielded stored XSS on the API origin, with no `nosniff`
header to prevent content sniffing either.

### 1.3 Traversal-shaped storage paths

```python
ext = file.filename.split(".")[-1].lower()
path = f"{APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4()}.{ext}"
```

`split(".")[-1]` of `a.jpg/../../evil` is `jpg/../../evil`, which was
interpolated straight into the storage path.

### 1.4 Other gaps

* No file-signature validation — type was decided by the client's extension and
  declared content type.
* No type restriction — `.html`, `.svg`, `.exe` were all storable.
* Size limit applied **after** `await file.read()`, so an oversized body was
  fully buffered in memory before rejection.
* No integrity hash.

---

## 2. Architecture implemented

| Layer | File | Responsibility |
| --- | --- | --- |
| Policy | `backend/file_policy.py` | Type allowlist, magic-byte detection, filename sanitisation, storage naming, disposition, hashing. No DB/route imports — directly unit-testable. |
| Tenant scoping | `backend/database.py` | `files` added to `TENANT_COLLECTIONS`, so every read/insert is org-bound by the TEN-01 machinery. |
| Routes | `backend/routes_core.py` | Streaming size limit, validation, safe response headers, org-scoped lookups. |
| Migration | `backend/server.py` | Accurate per-uploader ownership backfill. |

### 2.1 Ownership

Adding `files` to `TENANT_COLLECTIONS` means TEN-01's guarantees apply without
new code: reads are filtered by the session's `org_id`, inserts have it **forced**
from session context, and a foreign `org_id` raises `TenantViolation`. Upload
fails closed (403) if the session carries no organisation.

A cross-tenant file id now simply does not match, and the route returns the same
`404` as a non-existent id — **no existence disclosure**.

### 2.2 Never trust the client

| Input | Before | Now |
| --- | --- | --- |
| Content type | `file.content_type` (client) | Derived from the file's own magic bytes; mismatch with the extension is **rejected**, not relabelled |
| Storage name | client extension in path | `storage_object_name()` — server UUID, org-namespaced, extension whitelisted to `[a-z0-9]{1,10}` |
| Stored filename | verbatim | `sanitize_filename()` — path components dropped, control chars/quotes replaced, `..` collapsed, length-bounded |
| Size | checked after full read | enforced while streaming in 64 KB chunks |

### 2.3 Type allowlist

`jpg, jpeg, png, gif, webp, pdf, csv, txt` — the set FleetFlow actually uses.
Everything else is refused. CSV/TXT have no magic number and are identified by
UTF-8 decodability plus a control-character check, which is what stops a binary
being smuggled in under a `.csv` extension.

### 2.4 Downloads cannot become active content

* `Content-Disposition`: **images only** render `inline`; everything else —
  including PDF — is forced to `attachment`. A PDF viewer is a large attack
  surface and CSV/TXT can be sniffed into HTML.
* `X-Content-Type-Options: nosniff` — without it a browser may ignore the
  declared type and execute an upload as HTML/JS on this origin.
* `Content-Security-Policy: default-src 'none'; sandbox`.
* `Cache-Control: private, no-store` — keeps tenant files out of shared caches.

### 2.5 Integrity

Every record stores a `sha256` of the bytes as received.

---

## 3. Migration — and why the obvious approach is wrong

`server._migrate_org_ids()` blanket-assigns `DEFAULT_ORG_ID` to any record in
`TENANT_COLLECTIONS` lacking an `org_id`. Simply adding `files` to that set would
have handed **every existing file of every organisation to the default
organisation** — a data-integrity fault and a fresh cross-tenant disclosure, in
the very change meant to close one.

Instead:

* `DEFAULT_ORG_BACKFILL_COLLECTIONS = TENANT_COLLECTIONS - {"files"}` excludes
  files from the blanket backfill.
* `_migrate_file_org_ids()` derives each file's owner from its **uploader**
  (`uploaded_by` → that user's `org_id`), which is the only trustworthy signal on
  a legacy record. Idempotent; only touches files with no `org_id`.
* Files whose uploader cannot be resolved are set to
  `UNRESOLVED_FILE_ORG_ID = "org-unresolved-quarantine"`. No session ever carries
  that org, so they **fail closed** (404) until an operator reassigns them. They
  are logged at WARNING. Guessing would be worse than quarantining.

`_ensure_indexes()` iterates `TENANT_COLLECTIONS`, so `files.org_id` is indexed
automatically.

**Production note:** this migration runs at startup and is safe and idempotent,
but it *is* a data change. It has not been run against production — see SEC-004.

---

## 4. Compatibility

* **Frontend unaffected.** `FileWidgets` and `VehiclePhotos` fetch via XHR with
  `responseType: "blob"`, so the disposition change (PDFs now `attachment`) does
  not alter behaviour; they never navigate to the URL.
* **Intentionally breaking:** uploads of types outside the allowlist, and files
  whose bytes contradict their extension, now return 400. Both were previously
  stored.
* **Demo isolation preserved.** Demo files live under the demo org and are scoped
  by the same rule as every other tenant.
* **New endpoint:** `GET /api/files/{id}/metadata` returns non-content metadata,
  org-scoped, with `storage_path` projected out (it is internal).

---

## 5. Tests

`backend/tests/test_file_security.py` — **76 tests**, project `asyncio.run()`
convention, no live database.

Covers: `files` present in `TENANT_COLLECTIONS` (regression guard); reads scoped
to session org; own-org file found; **cross-tenant id returns nothing**; upload
stamps owning org; upload cannot be filed under another org; filename
sanitisation (traversal, quotes, CRLF, length, empty); Content-Disposition cannot
be escaped or injected; images inline / everything else attachment; extension
extraction and traversal resistance; storage names contain no client input, are
org-namespaced and unique; magic-byte detection for all eight types; binary not
mistaken for text; every allowlisted type is actually uploadable; disallowed
extensions rejected; HTML-as-PNG, ELF-as-PDF and PDF-as-JPG all rejected; empty
and oversized rejected; client-safe rejection messages; hash stability; and the
migration-safety guards.

**Results:** 248 passed, 3 skipped (full suite; 172 pre-existing still green).
Ruff introduces no new findings. Gitleaks clean. Frontend builds. `GET /api/` 200.

---

## 6. Remaining limitations (later workstreams)

* **Malware scanning** — no AV/quarantine pipeline. The type allowlist plus
  signature validation plus forced-attachment/nosniff limits what a stored file
  can do, but content is not scanned. Infrastructure for this does not exist in
  the current deployment; it needs a scanning service and a quarantine state
  machine, and is called out as an explicit exception at SEC-CLOSEOUT.
* **Short-lived signed URLs** — downloads are permission-checked streams through
  the API. The Emergent object store is reached with a single app-wide storage
  key, so per-tenant signed URLs are not available without a storage-layer
  change. Streaming is the safe option today and keeps the permission check on
  every read.
* **Linked-record permissions (AUTHZ-01)** — a file is scoped to its
  organisation, but FleetFlow does not yet model *which record* a file belongs
  to, so "can this user see the vehicle this photo is attached to" cannot be
  enforced. Adding `linked_collection`/`linked_id` metadata is future work; today
  any authenticated member of the owning organisation can read its files.
* **Branch scope** — no file carries `branch_id`; blocked on branch scoping
  generally (see TEN-01).
* **Orphaned objects** — `is_deleted` marks records, but storage objects are not
  reaped. No security impact (records are org-scoped), but it is a cost/retention
  gap.
