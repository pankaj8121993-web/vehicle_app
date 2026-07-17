"""
AUTH-01 — Secure session and authentication lifecycle primitives.

Before AUTH-01 FleetFlow issued an opaque bearer token, **stored it in the
database in plaintext**, returned it in the login response body for the frontend
to keep in ``localStorage``, and refreshed its expiry on every use with no
absolute cap. That gave four problems:

* A database read (backup, dump, injection, operator access) yielded *live*
  session tokens — the sessions collection was a credential store.
* ``localStorage`` is readable by any script on the origin, so a single XSS
  became full, persistent account takeover.
* Sliding expiry with no absolute cap meant a stolen token stayed valid
  indefinitely as long as it was used.
* Tokens were never rotated, so a token captured before a privilege change kept
  working after it.

This module holds the primitives that fix those. It has no database or route
imports so it can be unit-tested directly.

Design rules
------------
* **Store a hash, never the token.** The database holds SHA-256 of the token, so
  a dump cannot be replayed. SHA-256 (not bcrypt) is correct here: the token is
  256 bits of CSPRNG output, not a low-entropy human password, so there is
  nothing to brute-force and the lookup must stay fast.
* **Two independent clocks.** Idle expiry bounds an abandoned session; absolute
  expiry bounds a stolen one. Sliding only ever moves the idle clock.
* **Fail closed** on anything malformed.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

# --- Lifetimes ----------------------------------------------------------------

# Hard cap from session creation. Sliding refresh can never push past this, so a
# stolen token has a bounded life even if it is used continuously.
ABSOLUTE_TTL = timedelta(days=7)

# Inactivity cap. An unattended browser stops being a valid session well before
# the absolute cap.
IDLE_TTL = timedelta(hours=12)

# Only rewrite last_used_at at most this often; a write on every request would
# make the sessions collection the hottest thing in the database.
SLIDING_THROTTLE = timedelta(minutes=5)


# --- Cookie / header names ----------------------------------------------------

SESSION_COOKIE = "fleet_session"
# Readable by JS on purpose: the double-submit pattern needs the client to echo
# it back in a header. It is not a credential on its own.
CSRF_COOKIE = "fleet_csrf"
CSRF_HEADER = "X-CSRF-Token"

# Methods that change state and therefore require a CSRF token when the request
# is authenticated by cookie.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


# --- Token generation and hashing ---------------------------------------------

def generate_token() -> str:
    """256 bits of CSPRNG output, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of a session token, hex.

    What is stored and what is indexed. See the module docstring for why a fast
    hash is the right choice for a high-entropy token.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    """Constant-time comparison, so a timing signal cannot leak a token."""
    return hmac.compare_digest(str(a or ""), str(b or ""))


# --- Expiry -------------------------------------------------------------------

def now() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(value):
    """Normalise a datetime read back from MongoDB to timezone-aware UTC.

    Motor returns naive datetimes by default, while everything created in-process
    is aware — comparing the two raises TypeError. Mongo always stores UTC, so
    attaching UTC to a naive value is correct rather than a guess. Returns None
    for anything that is not a datetime, which the callers treat as expired.
    """
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def absolute_expiry(created_at: datetime) -> datetime:
    return created_at + ABSOLUTE_TTL


def is_expired(session: dict, at: datetime = None) -> bool:
    """True if a session has passed either clock.

    Fails closed: a session missing or carrying a malformed timestamp is treated
    as expired rather than trusted.
    """
    at = at or now()
    absolute = as_aware(session.get("absolute_expires_at"))
    last_used = as_aware(session.get("last_used_at"))
    if absolute is None or last_used is None:
        return True
    if at >= absolute:
        return True
    return at >= last_used + IDLE_TTL


def should_refresh(last_used, at: datetime = None) -> bool:
    last_used = as_aware(last_used)
    if last_used is None:
        return True
    return (at or now()) - last_used > SLIDING_THROTTLE


# --- CSRF ---------------------------------------------------------------------

def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_valid(expected: str, provided: str) -> bool:
    """Double-submit check.

    An attacker's cross-site page can make the browser *send* the session cookie,
    but same-origin policy stops it reading the CSRF cookie, so it cannot echo
    the value into the header. Empty values never validate — a missing token must
    never be treated as a match.
    """
    if not expected or not provided:
        return False
    return tokens_equal(expected, provided)


# --- Cookie attributes --------------------------------------------------------

def is_production() -> bool:
    return os.environ.get("APP_ENV", "development").lower() == "production"


def cookie_params(*, cross_site: bool = None) -> dict:
    """Cookie attributes for the current environment.

    Secure is forced in production. In development it must stay optional: the
    preview container is served over plain HTTP, and a Secure cookie there would
    simply never be stored, locking everyone out.

    SameSite=Lax is the default and blocks the ordinary cross-site CSRF vectors
    by itself. A deployment serving the API from a different site than the
    frontend must set FLEETFLOW_CROSS_SITE_COOKIES=true, which requires
    SameSite=None — and None without Secure is rejected by browsers, so that
    combination is only allowed when Secure is on.
    """
    if cross_site is None:
        cross_site = os.environ.get("FLEETFLOW_CROSS_SITE_COOKIES", "").lower() == "true"
    secure = is_production() or cross_site
    same_site = "none" if cross_site else "lax"
    return {
        "httponly": True,
        "secure": secure,
        "samesite": same_site,
        "path": "/",
    }


def csrf_cookie_params() -> dict:
    """Same as the session cookie but readable by JS (double-submit needs it)."""
    params = cookie_params()
    params["httponly"] = False
    return params


# --- Login throttling ---------------------------------------------------------

# Counted per username and per client IP independently, so neither a targeted
# attack on one account nor a spray from one address can run unbounded.
MAX_FAILED_ATTEMPTS = 10
THROTTLE_WINDOW = timedelta(minutes=15)
LOCKOUT_DURATION = timedelta(minutes=15)


def throttle_key(username: str, ip: str) -> tuple:
    return (str(username or "").lower().strip(), str(ip or "unknown"))
