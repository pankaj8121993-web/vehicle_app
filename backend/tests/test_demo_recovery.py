"""DEMO-01 focused recovery regression coverage."""
from datetime import datetime, timedelta, timezone

import demo_seed
import server
from conftest import realhttp_run as _run
from httpx import ASGITransport, AsyncClient


def _org(now, **overrides):
    value = {
        "id": demo_seed.DEMO_ORG_ID,
        "is_demo": True,
        "demo_seed_version": demo_seed.DEMO_SEED_VERSION,
        "demo_seed_status": "complete",
        "demo_seeded_at": now.isoformat(),
    }
    value.update(overrides)
    return value


def test_seed_currency_requires_marker_version_status_and_freshness():
    now = datetime.now(timezone.utc)
    assert demo_seed._seed_is_current(_org(now), now)
    assert not demo_seed._seed_is_current(_org(now, is_demo=False), now)
    assert not demo_seed._seed_is_current(_org(now, demo_seed_version=0), now)
    assert not demo_seed._seed_is_current(_org(now, demo_seed_status="failed"), now)
    expired = now - timedelta(hours=demo_seed.RESET_HOURS + 1)
    assert not demo_seed._seed_is_current(_org(expired), now)
    assert not demo_seed._seed_is_current(_org(now), now, force=True)


def test_canonical_role_catalogue_is_complete_and_unique():
    roles = [role for role, _name, _designation in demo_seed.DEMO_USERS]
    assert roles == [
        "org_admin", "owner", "fleet_manager", "operations", "maintenance",
        "driver", "accounts", "viewer",
    ]
    assert len(roles) == len(set(roles))


def test_every_demo_role_gets_isolated_refreshable_session():
    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://demo.test"
        ) as client:
            for role, _name, _designation in demo_seed.DEMO_USERS:
                entered = await client.post("/api/demo/enter", json={"role": role})
                assert entered.status_code == 200, (role, entered.text)
                assert "fleet_session" in entered.cookies
                assert "fleet_csrf" in entered.cookies
                me = await client.get("/api/auth/me")
                assert me.status_code == 200
                assert me.json()["role"] == role
                logged_out = await client.post("/api/auth/logout")
                assert logged_out.status_code == 200
                assert (await client.get("/api/auth/me")).status_code == 401

    _run(scenario())
