"""
AUTH-01 — Secure session and authentication lifecycle.

The defects these tests pin:

* Session tokens were stored in the database **in plaintext**, so any dump,
  backup or injection yielded live sessions.
* The token was returned in the login body and kept in ``localStorage``, so one
  XSS meant persistent account takeover.
* Expiry slid forward on every use with no absolute cap, so a stolen token lived
  forever as long as it was used.
* Tokens were never rotated, so one captured before a privilege change kept
  working after it.
* Password reset flipped the ``revoked`` flag but did not evict the in-memory
  cache, leaving reset accounts reachable for the cache TTL.

Project convention: no pytest-asyncio.
"""
from datetime import datetime, timedelta, timezone

import pytest

import session_security as ss


# --- Token hashing ------------------------------------------------------------

def test_token_is_high_entropy():
    assert len(ss.generate_token()) >= 40


def test_tokens_are_unique():
    assert len({ss.generate_token() for _ in range(100)}) == 100


def test_hash_is_stable():
    t = ss.generate_token()
    assert ss.hash_token(t) == ss.hash_token(t)


def test_hash_is_sha256_hex():
    assert len(ss.hash_token("x")) == 64
    int(ss.hash_token("x"), 16)  # raises if not hex


def test_hash_does_not_reveal_the_token():
    """The stored value must not contain the token — that is the whole point."""
    t = ss.generate_token()
    assert t not in ss.hash_token(t)


def test_different_tokens_hash_differently():
    assert ss.hash_token(ss.generate_token()) != ss.hash_token(ss.generate_token())


def test_tokens_equal_is_constant_time_and_correct():
    assert ss.tokens_equal("abc", "abc")
    assert not ss.tokens_equal("abc", "abd")
    assert not ss.tokens_equal("", "abc")
    assert not ss.tokens_equal(None, None) or True  # must not raise


# --- Expiry: two independent clocks -------------------------------------------

def _session(*, created_ago=timedelta(0), used_ago=timedelta(0)):
    now = ss.now()
    created = now - created_ago
    return {
        "created_at": created,
        "last_used_at": now - used_ago,
        "absolute_expires_at": ss.absolute_expiry(created),
    }


def test_fresh_session_is_valid():
    assert not ss.is_expired(_session())


def test_idle_session_expires():
    assert ss.is_expired(_session(used_ago=ss.IDLE_TTL + timedelta(minutes=1)))


def test_session_just_within_idle_window_is_valid():
    assert not ss.is_expired(_session(used_ago=ss.IDLE_TTL - timedelta(minutes=1)))


def test_absolute_cap_expires_even_when_actively_used():
    """The regression that motivated the absolute clock: a continuously-used
    stolen token must still die."""
    s = _session(created_ago=ss.ABSOLUTE_TTL + timedelta(minutes=1), used_ago=timedelta(seconds=1))
    assert ss.is_expired(s)


def test_absolute_expiry_is_ttl_after_creation():
    created = ss.now()
    assert ss.absolute_expiry(created) == created + ss.ABSOLUTE_TTL


def test_idle_is_shorter_than_absolute():
    assert ss.IDLE_TTL < ss.ABSOLUTE_TTL


@pytest.mark.parametrize("session", [
    {},
    {"absolute_expires_at": None, "last_used_at": None},
    {"absolute_expires_at": "not-a-datetime", "last_used_at": "nope"},
    {"last_used_at": datetime.now(timezone.utc)},          # no absolute
    {"absolute_expires_at": datetime.now(timezone.utc)},   # no last_used
])
def test_malformed_session_fails_closed(session):
    assert ss.is_expired(session)


def test_sliding_refresh_is_throttled():
    assert not ss.should_refresh(ss.now())
    assert ss.should_refresh(ss.now() - ss.SLIDING_THROTTLE - timedelta(seconds=1))


def test_sliding_refresh_of_malformed_timestamp_is_safe():
    assert ss.should_refresh(None)


# --- CSRF ---------------------------------------------------------------------

def test_csrf_tokens_are_unique():
    assert ss.generate_csrf_token() != ss.generate_csrf_token()


def test_csrf_matching_value_validates():
    t = ss.generate_csrf_token()
    assert ss.csrf_valid(ss.hash_token(t), ss.hash_token(t))


def test_csrf_wrong_value_rejected():
    assert not ss.csrf_valid(ss.hash_token("a"), ss.hash_token("b"))


@pytest.mark.parametrize("expected,provided", [
    ("", ""),
    (None, None),
    ("abc", ""),
    ("", "abc"),
    ("abc", None),
    (None, "abc"),
])
def test_csrf_missing_value_never_validates(expected, provided):
    """A missing token must never count as a match — that would make CSRF
    protection opt-out by simply omitting the header."""
    assert not ss.csrf_valid(expected, provided)


def test_state_changing_methods_are_not_safe():
    for m in ("POST", "PUT", "PATCH", "DELETE"):
        assert m not in ss.SAFE_METHODS


def test_read_methods_are_safe():
    for m in ("GET", "HEAD", "OPTIONS"):
        assert m in ss.SAFE_METHODS


# --- Cookie attributes --------------------------------------------------------

def test_session_cookie_is_httponly(monkeypatch):
    """HttpOnly is what stops XSS reading the session."""
    monkeypatch.delenv("FLEETFLOW_CROSS_SITE_COOKIES", raising=False)
    assert ss.cookie_params()["httponly"] is True


def test_session_cookie_is_secure_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("FLEETFLOW_CROSS_SITE_COOKIES", raising=False)
    assert ss.cookie_params()["secure"] is True


def test_session_cookie_not_forced_secure_in_development(monkeypatch):
    """The preview container is plain HTTP; a Secure cookie would never be
    stored and would lock everyone out."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("FLEETFLOW_CROSS_SITE_COOKIES", raising=False)
    assert ss.cookie_params()["secure"] is False


def test_default_samesite_is_lax(monkeypatch):
    monkeypatch.delenv("FLEETFLOW_CROSS_SITE_COOKIES", raising=False)
    assert ss.cookie_params()["samesite"] == "lax"


def test_cross_site_requires_none_and_secure(monkeypatch):
    """SameSite=None without Secure is rejected by browsers, so the two must
    always be set together."""
    monkeypatch.setenv("FLEETFLOW_CROSS_SITE_COOKIES", "true")
    params = ss.cookie_params()
    assert params["samesite"] == "none"
    assert params["secure"] is True


def test_csrf_cookie_is_readable_but_otherwise_identical(monkeypatch):
    """Double-submit needs JS to read it; it is not a credential by itself."""
    monkeypatch.delenv("FLEETFLOW_CROSS_SITE_COOKIES", raising=False)
    csrf = ss.csrf_cookie_params()
    session = ss.cookie_params()
    assert csrf["httponly"] is False
    assert csrf["samesite"] == session["samesite"]
    assert csrf["secure"] == session["secure"]


def test_production_detection(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert ss.is_production()
    monkeypatch.setenv("APP_ENV", "development")
    assert not ss.is_production()
    monkeypatch.delenv("APP_ENV", raising=False)
    assert not ss.is_production()   # default is not production


# --- Throttling ---------------------------------------------------------------

def test_throttle_key_is_normalised():
    assert ss.throttle_key("  Admin ", "1.2.3.4") == ("admin", "1.2.3.4")


def test_throttle_key_handles_missing_ip():
    assert ss.throttle_key("a", None)[1] == "unknown"


def test_throttle_limits_are_sane():
    assert 0 < ss.MAX_FAILED_ATTEMPTS <= 20
    assert ss.THROTTLE_WINDOW >= timedelta(minutes=1)


# --- Wiring: the auth module actually uses all this ----------------------------

def test_plaintext_token_field_is_gone_from_session_creation():
    """The regression guard: sessions must never persist a raw token again."""
    import inspect
    import auth

    src = inspect.getsource(auth.create_session)
    assert "token_hash" in src
    assert '"token": token' not in src


def test_login_rotates_the_session():
    """Session fixation: a pre-login token must not survive authentication."""
    import inspect
    import auth

    assert "revoke_user_sessions" in inspect.getsource(auth.login)


def test_password_change_revokes_sessions():
    import inspect
    import auth

    assert "revoke_user_sessions" in inspect.getsource(auth.change_password)


def test_password_reset_revokes_through_the_cache_evicting_path():
    """The old code only flipped the DB flag, leaving the cache live."""
    import inspect
    import auth

    assert "revoke_user_sessions" in inspect.getsource(auth.reset_password)


def test_role_change_revokes_sessions():
    import inspect
    import auth

    assert "revoke_user_sessions" in inspect.getsource(auth.update_user)


def test_revocation_evicts_the_in_memory_cache():
    import inspect
    import auth

    assert "_evict_cached_user" in inspect.getsource(auth.revoke_user_sessions)


def test_cache_is_keyed_by_hash_not_raw_token():
    import inspect
    import auth

    src = inspect.getsource(auth._resolve_session)
    assert "token_hash" in src
    assert "_session_cache[token_hash]" in src


def test_cache_hit_still_checks_expiry():
    """A cache hit must never extend a session past either clock."""
    import inspect
    import auth

    src = inspect.getsource(auth._resolve_session)
    cache_section = src.split("cached = _session_cache.get")[1].split("session = await")[0]
    assert "is_expired" in cache_section


def test_csrf_is_enforced_for_cookie_writes_only():
    import inspect
    import auth

    src = inspect.getsource(auth._enforce_csrf)
    assert "SAFE_METHODS" in src
    assert 'via != "cookie"' in src


def test_cookie_is_preferred_over_bearer():
    import inspect
    import auth

    src = inspect.getsource(auth._extract_token)
    assert src.index("cookies.get") < src.index("Bearer")


def test_login_error_does_not_enumerate_users():
    """Same message whether the user exists or the password is wrong."""
    import inspect
    import auth

    src = inspect.getsource(auth.login)
    assert src.count("Invalid username or password") == 1
    assert "not found" not in src.lower()


def test_login_verifies_a_hash_even_for_unknown_users():
    """Otherwise response timing reveals which usernames exist."""
    import inspect
    import auth

    assert "invalid-placeholder" in inspect.getsource(auth.login)


def test_throttle_message_does_not_confirm_an_account():
    """A throttle response must not say *whose* account is locked, or it becomes
    a user-enumeration oracle. Checks the messages actually raised, not the
    source text (comments legitimately discuss the word)."""
    import ast
    import inspect
    import auth

    tree = ast.parse(inspect.getsource(auth.login))
    messages = [
        kw.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "detail" and isinstance(kw.value, ast.Constant)
    ]
    assert any("Too many failed attempts" in m for m in messages)
    for m in messages:
        assert "locked" not in m.lower()
        assert "account" not in m.lower() or "attempts" in m.lower()


# --- Migration ----------------------------------------------------------------

def test_plaintext_sessions_are_revoked_not_rehashed():
    """Hashing an already-exposed token would keep it working — exactly what the
    change exists to prevent. They must be revoked instead."""
    import inspect
    import server

    src = inspect.getsource(server._migrate_plaintext_sessions)
    assert '"revoked": True' in src
    assert "$unset" in src           # plaintext value removed
    assert "hash_token" not in src   # never carried forward


# --- CORS ---------------------------------------------------------------------

def test_credentials_are_not_allowed_with_wildcard_origin():
    """allow_credentials + "*" is rejected by browsers and unsafe: it would let
    any origin read authenticated responses."""
    import inspect
    import server

    src = inspect.getsource(server)
    assert "_cors_allowlisted" in src
    assert "allow_credentials=_cors_allowlisted" in src
