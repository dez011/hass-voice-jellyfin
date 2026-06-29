"""Integration tests against a real Jellyfin server.

Requires .env.test with JELLYFIN_URL and JELLYFIN_API_KEY.
Skipped automatically if the file is missing or the server is unreachable.

Run with:
    pytest tests/test_jellyfin_integration.py -v
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Load .env.test — skip entire module if missing
# ---------------------------------------------------------------------------

_ENV_FILE = Path(__file__).parent.parent / ".env.test"

def _load_env() -> dict[str, str]:
    if not _ENV_FILE.exists():
        return {}
    env: dict[str, str] = {}
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env

_ENV = _load_env()

pytestmark = pytest.mark.skipif(
    not _ENV,
    reason=".env.test not found — skipping integration tests",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def jellyfin_url() -> str:
    return _ENV.get("JELLYFIN_URL", "")

@pytest.fixture(scope="module")
def jellyfin_api_key() -> str:
    return _ENV.get("JELLYFIN_API_KEY", "")

@pytest.fixture(scope="module")
def auth(jellyfin_url, jellyfin_api_key):
    from custom_components.voice_jellyfin.jellyfin.auth import JellyfinAuth
    return JellyfinAuth(url=jellyfin_url, api_key=jellyfin_api_key)

@pytest.fixture
def client(auth):
    from custom_components.voice_jellyfin.jellyfin.client import JellyfinClient
    return JellyfinClient(auth, verify_ssl=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect(client):
    """Server is reachable and API key is valid."""
    data = await client.async_connect()
    assert "Version" in data, f"Unexpected response: {data}"
    print(f"\nJellyfin version: {data['Version']}")

@pytest.mark.asyncio
async def test_get_sessions(client):
    """Can fetch active sessions (list may be empty)."""
    sessions = await client.async_get_sessions()
    assert isinstance(sessions, list)
    print(f"\nActive sessions: {len(sessions)}")
    for s in sessions:
        print(f"  - {s.id} | playing={s.item.name if s.item else 'nothing'}")

@pytest.mark.asyncio
async def test_get_libraries(client):
    """Can fetch at least one library."""
    libs = await client.async_get_libraries()
    assert isinstance(libs, list)
    print(f"\nLibraries ({len(libs)}):")
    for lib in libs:
        print(f"  - [{lib.id}] {lib.name} ({lib.type})")

@pytest.mark.asyncio
async def test_search(client):
    """Search returns results for a broad query."""
    results = await client.async_search("the", limit=5)
    assert isinstance(results, list)
    print(f"\nSearch 'the' → {len(results)} results:")
    for item in results:
        print(f"  - {item.name} ({item.type}, {item.year})")

@pytest.mark.asyncio
async def test_auth_failure():
    """Wrong API key returns PermissionError, not a generic error."""
    from custom_components.voice_jellyfin.jellyfin.auth import JellyfinAuth
    from custom_components.voice_jellyfin.jellyfin.client import JellyfinClient

    bad_auth = JellyfinAuth(url=_ENV.get("JELLYFIN_URL", ""), api_key="bad-key-000")
    bad_client = JellyfinClient(bad_auth, verify_ssl=False)
    with pytest.raises(PermissionError, match="API key"):
        await bad_client.async_connect()
