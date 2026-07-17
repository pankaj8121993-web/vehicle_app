"""
FILE-01 — Tenant-scoped file security.

The defect these tests pin: ``files`` was absent from
``database.TENANT_COLLECTIONS``, so file records carried no ``org_id`` and
``GET /api/files/{file_id}`` resolved by id alone. Any authenticated user could
download any organisation's file. The upload path additionally trusted the
client's filename and Content-Type, allowing response-header injection, stored
XSS and traversal-shaped storage paths.

Layered like the TEN-01 suite: policy is unit-tested directly, and the tenant
scoping is asserted against the real ``TenantCollection`` with a fake driver, so
no live database is needed. Project convention: no pytest-asyncio.
"""
import asyncio

import pytest

import file_policy
from file_policy import (
    ALLOWED_TYPES,
    INLINE_CONTENT_TYPES,
    FileRejected,
    content_disposition,
    detect_content_type,
    extract_extension,
    sanitize_filename,
    sha256_hex,
    storage_object_name,
    validate_upload,
)


def _run(coro):
    return asyncio.run(coro)


# --- Sample bytes with real magic numbers -------------------------------------

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"x" * 32
CSV = b"vehicle,date\nKA01AB1234,2026-01-01\n"
TXT = b"just some notes\n"
HTML = b"<html><script>alert(1)</script></html>"
ELF = b"\x7fELF" + b"\x00" * 32


# --- Tenant scoping: the core defect -------------------------------------------

def test_files_collection_is_tenant_scoped():
    """The regression that motivated FILE-01.

    If "files" ever leaves TENANT_COLLECTIONS, every file becomes readable by
    every organisation again.
    """
    from database import TENANT_COLLECTIONS

    assert "files" in TENANT_COLLECTIONS


class _FakeMotorCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.inserted = []
        self.last_filter = None

    async def insert_one(self, doc, **k):
        self.inserted.append(doc)
        return doc

    async def find_one(self, flt=None, projection=None, **k):
        self.last_filter = flt
        for d in self.docs:
            if all(d.get(key) == val for key, val in (flt or {}).items()):
                return d
        return None


@pytest.fixture
def files_coll():
    """A tenant-scoped `files` collection bound to org-a."""
    import database

    fake = _FakeMotorCollection(docs=[
        {"id": "f-a", "org_id": "org-a", "is_deleted": False, "storage_path": "p/a"},
        {"id": "f-b", "org_id": "org-b", "is_deleted": False, "storage_path": "p/b"},
    ])
    coll = database.TenantCollection(fake, "files")
    token = database.current_org_id.set("org-a")
    yield coll, fake
    database.current_org_id.reset(token)


def test_file_read_is_scoped_to_the_session_org(files_coll):
    coll, fake = files_coll
    _run(coll.find_one({"id": "f-a", "is_deleted": False}))
    assert fake.last_filter["org_id"] == "org-a"


def test_own_org_file_is_found(files_coll):
    coll, _ = files_coll
    assert _run(coll.find_one({"id": "f-a", "is_deleted": False}))["id"] == "f-a"


def test_cross_tenant_file_id_returns_nothing(files_coll):
    """Org A asking for Org B's file id must find nothing — the route turns this
    into the same 404 as a non-existent id, so existence is not disclosed."""
    coll, _ = files_coll
    assert _run(coll.find_one({"id": "f-b", "is_deleted": False})) is None


def test_upload_stamps_owning_org(files_coll):
    coll, fake = files_coll
    _run(coll.insert_one({"id": "f-new", "storage_path": "p/new"}))
    assert fake.inserted[0]["org_id"] == "org-a"


def test_upload_cannot_be_filed_under_another_org(files_coll):
    from tenant_policy import TenantViolation

    coll, fake = files_coll
    with pytest.raises(TenantViolation):
        _run(coll.insert_one({"id": "f-x", "org_id": "org-b"}))
    assert fake.inserted == []


# --- Filename sanitisation / header injection ---------------------------------

@pytest.mark.parametrize("raw,expected_absent", [
    ("../../etc/passwd", "/"),
    ("..\\..\\windows\\system32", "\\"),
    ('evil"; filename="x.exe', '"'),
    ("bad\r\nSet-Cookie: a=b", "\r"),
    ("bad\r\nSet-Cookie: a=b", "\n"),
])
def test_sanitize_filename_strips_dangerous_characters(raw, expected_absent):
    assert expected_absent not in sanitize_filename(raw)


def test_sanitize_filename_drops_directory_components():
    assert sanitize_filename("../../etc/passwd") == "passwd"


def test_sanitize_filename_collapses_traversal():
    assert ".." not in sanitize_filename("a..b..c.jpg")


def test_sanitize_filename_handles_empty():
    assert sanitize_filename("") == "file"
    assert sanitize_filename(None) == "file"


def test_sanitize_filename_bounds_length():
    assert len(sanitize_filename("a" * 500 + ".jpg")) <= 120


def test_sanitize_filename_keeps_ordinary_names():
    assert sanitize_filename("RC Book 2026.pdf") == "RC Book 2026.pdf"


def test_content_disposition_cannot_be_escaped():
    """A quote in the filename must not break out of the quoted-string."""
    header = content_disposition("application/pdf", 'x"; filename="evil.exe')
    assert header.count('"') == 2


def test_content_disposition_cannot_inject_a_header():
    header = content_disposition("image/png", "a\r\nSet-Cookie: b=c.png")
    assert "\r" not in header and "\n" not in header


@pytest.mark.parametrize("content_type", sorted(INLINE_CONTENT_TYPES))
def test_images_render_inline(content_type):
    assert content_disposition(content_type, "p.png").startswith("inline")


@pytest.mark.parametrize("content_type", [
    "application/pdf", "text/csv", "text/plain", "application/octet-stream",
])
def test_non_images_are_forced_to_download(content_type):
    """Anything a browser might execute or sniff into HTML must not render."""
    assert content_disposition(content_type, "f.pdf").startswith("attachment")


# --- Extension extraction / path traversal ------------------------------------

@pytest.mark.parametrize("filename,expected", [
    ("photo.jpg", "jpg"),
    ("PHOTO.JPG", "jpg"),
    ("archive.tar.gz", "gz"),
    ("noext", ""),
    ("", ""),
    ("trailing.", ""),
])
def test_extract_extension(filename, expected):
    assert extract_extension(filename) == expected


@pytest.mark.parametrize("filename", [
    "a.jpg/../../evil",
    "a.jpg/../../../etc/passwd",
    "x.jp g",
    "x.<script>",
    "x.a/b",
])
def test_extension_cannot_carry_a_path(filename):
    """Pre-FILE-01 used filename.split(".")[-1] straight into the storage path."""
    ext = extract_extension(filename)
    assert "/" not in ext and "\\" not in ext and ".." not in ext


def test_storage_name_contains_no_client_input():
    name = storage_object_name("org-a", "jpg")
    assert name.startswith("org-a/") and name.endswith(".jpg")
    assert "/" not in name[len("org-a/"):]


def test_storage_name_rejects_a_hostile_extension():
    name = storage_object_name("org-a", "../../evil")
    assert name.endswith(".bin") and ".." not in name


def test_storage_name_is_unique_per_call():
    assert storage_object_name("org-a", "jpg") != storage_object_name("org-a", "jpg")


def test_storage_name_is_org_namespaced():
    assert storage_object_name("org-b", "png").startswith("org-b/")


# --- Content-type detection from magic bytes ----------------------------------

@pytest.mark.parametrize("data,expected", [
    (JPEG, "image/jpeg"),
    (PNG, "image/png"),
    (GIF, "image/gif"),
    (WEBP, "image/webp"),
    (PDF, "application/pdf"),
])
def test_detect_binary_types(data, expected):
    assert detect_content_type(data, "jpg") == expected


def test_detect_csv_and_txt():
    assert detect_content_type(CSV, "csv") == "text/csv"
    assert detect_content_type(TXT, "txt") == "text/plain"


def test_binary_is_not_mistaken_for_text():
    assert detect_content_type(ELF, "txt") is None


# --- Upload validation --------------------------------------------------------

@pytest.mark.parametrize("filename,data,expected_type", [
    ("p.jpg", JPEG, "image/jpeg"),
    ("p.jpeg", JPEG, "image/jpeg"),
    ("p.png", PNG, "image/png"),
    ("p.gif", GIF, "image/gif"),
    ("p.webp", WEBP, "image/webp"),
    ("d.pdf", PDF, "application/pdf"),
    ("d.csv", CSV, "text/csv"),
    ("d.txt", TXT, "text/plain"),
])
def test_valid_uploads_are_accepted(filename, data, expected_type):
    ext, content_type, digest = validate_upload(filename, data)
    assert content_type == expected_type
    assert digest == sha256_hex(data)


@pytest.mark.parametrize("filename", [
    "evil.html", "evil.svg", "evil.js", "evil.exe", "evil.sh",
    "evil.zip", "evil.docm", "evil.php", "noextension",
])
def test_disallowed_extensions_are_rejected(filename):
    with pytest.raises(FileRejected):
        validate_upload(filename, PNG)


def test_html_disguised_as_an_image_is_rejected():
    """Extension says png, bytes say HTML — the signature check catches it."""
    with pytest.raises(FileRejected):
        validate_upload("evil.png", HTML)


def test_executable_disguised_as_a_pdf_is_rejected():
    with pytest.raises(FileRejected):
        validate_upload("evil.pdf", ELF)


def test_pdf_disguised_as_a_jpg_is_rejected():
    """Signature/extension mismatch is refused rather than quietly relabelled."""
    with pytest.raises(FileRejected):
        validate_upload("x.jpg", PDF)


def test_empty_file_is_rejected():
    with pytest.raises(FileRejected):
        validate_upload("p.jpg", b"")


def test_oversized_file_is_rejected():
    with pytest.raises(FileRejected):
        validate_upload("p.jpg", JPEG + b"\x00" * file_policy.MAX_UPLOAD_BYTES)


def test_csv_and_txt_are_interchangeable():
    """Byte-identical formats; either text type is fine for either extension."""
    assert validate_upload("d.csv", TXT)[1] in {"text/csv", "text/plain"}
    assert validate_upload("d.txt", CSV)[1] in {"text/csv", "text/plain"}


def test_rejection_message_is_client_safe():
    """No internal paths, no stack detail, no echoed content."""
    with pytest.raises(FileRejected) as e:
        validate_upload("evil.html", HTML)
    msg = str(e.value)
    assert "/app" not in msg and "Traceback" not in msg


def test_every_allowed_type_is_detectable():
    """An allowlisted extension nobody can actually upload would be a trap."""
    samples = {
        "jpg": JPEG, "jpeg": JPEG, "png": PNG, "gif": GIF,
        "webp": WEBP, "pdf": PDF, "csv": CSV, "txt": TXT,
    }
    assert set(samples) == set(ALLOWED_TYPES)
    for ext, data in samples.items():
        assert validate_upload(f"f.{ext}", data)[1] is not None


# --- Integrity ----------------------------------------------------------------

def test_hash_is_stable_and_distinguishing():
    assert sha256_hex(JPEG) == sha256_hex(JPEG)
    assert sha256_hex(JPEG) != sha256_hex(PNG)
    assert len(sha256_hex(JPEG)) == 64


# --- Migration safety ---------------------------------------------------------

def test_files_are_excluded_from_the_blanket_default_org_backfill():
    """Assigning every legacy file to DEFAULT_ORG_ID would misfile other
    organisations' documents into the default org. Files get a real backfill
    derived from their uploader instead."""
    import server

    assert "files" not in server.DEFAULT_ORG_BACKFILL_COLLECTIONS
    assert "vehicles" in server.DEFAULT_ORG_BACKFILL_COLLECTIONS


def test_unresolvable_files_are_quarantined_not_guessed():
    import server

    # No session carries this org, so quarantined files are unreachable (404).
    assert server.UNRESOLVED_FILE_ORG_ID != server.DEFAULT_ORG_ID
