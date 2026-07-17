"""
FILE-01 — Tenant-scoped file security policy.

Before FILE-01 the ``files`` collection was not in ``database.TENANT_COLLECTIONS``,
so file records carried no ``org_id`` and ``GET /api/files/{file_id}`` resolved a
file by id alone. Any authenticated user could download **any organisation's**
file by guessing or observing an id — a cross-tenant IDOR. The upload path also
trusted the client's filename and content type, which allowed response-header
injection and stored XSS.

This module holds the decisions that keep uploads safe. It is deliberately free
of database and FastAPI-route imports so it can be unit-tested directly.

Design rules
------------
* **Never trust the client.** The filename, extension and ``Content-Type`` in a
  multipart upload are all attacker-controlled. The stored name is generated
  server-side and the content type is derived from the file's own magic bytes.
* **Allowlist, not denylist.** Only types FleetFlow actually uses are accepted.
* **Fail closed.** Anything unrecognised is rejected rather than stored as
  ``application/octet-stream``.
"""
import hashlib
import re
import unicodedata

# Maximum accepted upload. Enforced while streaming, before the whole body is
# buffered, so an oversized upload cannot exhaust memory first.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

# Read the body in chunks when enforcing the size limit.
UPLOAD_CHUNK_BYTES = 64 * 1024


class FileRejected(Exception):
    """Upload refused by policy. The message is safe to show a client."""


# --- Type allowlist -----------------------------------------------------------

# Canonical extension -> content type. This is the complete set FleetFlow
# accepts: vehicle/driver photos, scanned compliance documents, and CSV/text
# imports. Anything else (svg, html, js, zip, office macros, …) is refused —
# several of those execute script in a browser context if ever served inline.
ALLOWED_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "csv": "text/csv",
    "txt": "text/plain",
}

# Content types that may be rendered in the browser. Everything else downloads.
# Images only: a PDF viewer is a large attack surface and CSV/TXT can be sniffed
# into HTML by some browsers, so those are always attachments.
INLINE_CONTENT_TYPES = frozenset({
    "image/jpeg", "image/png", "image/gif", "image/webp",
})


# --- Magic-byte detection -----------------------------------------------------

def _sniff_webp(data: bytes) -> bool:
    # RIFF....WEBP
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def _sniff_binary(data: bytes):
    """Return a content type from the file's own leading bytes, or None."""
    signatures = (
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"%PDF-", "application/pdf"),
    )
    for magic, content_type in signatures:
        if data.startswith(magic):
            return content_type
    if _sniff_webp(data):
        return "image/webp"
    return None


def _looks_like_text(data: bytes) -> bool:
    """True if the bytes decode as UTF-8 and hold no control characters.

    CSV and text have no magic number, so they are identified by exclusion. The
    control-character check is what stops a binary or a script being smuggled in
    under a .csv extension.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return not any(ord(c) < 9 or 13 < ord(c) < 32 for c in text)


def detect_content_type(data: bytes, declared_ext: str):
    """Derive the content type from the bytes. Returns None if unrecognised.

    ``declared_ext`` only chooses between the two text types (csv/txt), which are
    byte-identical; it can never widen what is accepted.
    """
    sniffed = _sniff_binary(data)
    if sniffed:
        return sniffed
    if _looks_like_text(data):
        return "text/csv" if declared_ext == "csv" else "text/plain"
    return None


# --- Filename handling --------------------------------------------------------

_UNSAFE_FILENAME_CHARS = re.compile(r'[^A-Za-z0-9._ -]')
_COLLAPSE_DOTS = re.compile(r'\.{2,}')


def extract_extension(filename: str) -> str:
    """Return the lowercase extension, or "" if there is no usable one.

    Taken from the final path segment only. The pre-FILE-01 code used
    ``filename.split(".")[-1]`` and interpolated the result straight into the
    storage path, so a name like ``a.jpg/../../evil`` produced a traversing
    extension. Anything that is not plain alphanumerics is discarded here.
    """
    if not filename:
        return ""
    tail = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in tail:
        return ""
    ext = tail.rsplit(".", 1)[-1].lower().strip()
    if not re.fullmatch(r"[a-z0-9]{1,10}", ext):
        return ""
    return ext


def sanitize_filename(filename: str) -> str:
    """Return a display-safe original filename.

    The result is only ever echoed back in metadata and in a Content-Disposition
    header — it is never used to build a storage path. Strips directory
    components, control characters (CR/LF would allow response-header injection),
    quotes (which would break out of the header's quoted-string), and collapses
    ".." so a traversal-looking name cannot be displayed or re-used as one.
    """
    if not filename:
        return "file"
    name = unicodedata.normalize("NFKD", str(filename))
    name = name.replace("\\", "/").rsplit("/", 1)[-1]     # drop any path
    name = _UNSAFE_FILENAME_CHARS.sub("_", name)           # kills CR, LF, ", ;
    name = _COLLAPSE_DOTS.sub(".", name).strip(". ")
    name = name[:120]
    return name or "file"


def storage_object_name(org_id: str, ext: str) -> str:
    """Server-generated storage path segment. No client input reaches it.

    Namespacing by organisation means a storage-path disclosure still cannot be
    walked into another tenant's object, and it keeps the object store
    inspectable per tenant.
    """
    import uuid
    safe_ext = ext if re.fullmatch(r"[a-z0-9]{1,10}", ext or "") else "bin"
    return f"{org_id}/{uuid.uuid4()}.{safe_ext}"


def content_disposition(content_type: str, filename: str) -> str:
    """Build a safe Content-Disposition header value.

    ``filename`` is sanitised first, so the quoted-string cannot be escaped and
    no CR/LF can be injected. Only image types render inline; everything else is
    forced to download, which — together with X-Content-Type-Options: nosniff —
    is what stops an uploaded file being served as active content.
    """
    safe = sanitize_filename(filename)
    disposition = "inline" if content_type in INLINE_CONTENT_TYPES else "attachment"
    return f'{disposition}; filename="{safe}"'


# --- Integrity ----------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- Upload validation --------------------------------------------------------

def validate_upload(filename: str, data: bytes):
    """Validate an upload and return ``(ext, content_type, sha256)``.

    Raises :class:`FileRejected` with a client-safe message. The extension is
    only advisory: the returned content type always comes from the bytes, and a
    file whose signature disagrees with its extension is refused rather than
    quietly relabelled — a .jpg that is really a PDF is either a bug or an
    attempt to smuggle a type past a naive check.
    """
    if not data:
        raise FileRejected("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileRejected(
            f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB)."
        )

    ext = extract_extension(filename)
    if ext not in ALLOWED_TYPES:
        allowed = ", ".join(sorted(ALLOWED_TYPES))
        raise FileRejected(f"Unsupported file type. Allowed: {allowed}.")

    detected = detect_content_type(data, ext)
    if detected is None:
        raise FileRejected("File content is not a supported type.")

    expected = ALLOWED_TYPES[ext]
    # jpg/jpeg both map to image/jpeg; csv/txt are byte-identical, so accept
    # either text type for either extension. Everything else must agree.
    text_types = {"text/csv", "text/plain"}
    if detected != expected and not (detected in text_types and expected in text_types):
        raise FileRejected(
            "File content does not match its extension."
        )

    return ext, detected, sha256_hex(data)
