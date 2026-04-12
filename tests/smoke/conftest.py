"""Shared fixtures for LiveKit twin smoke tests.

Starts the twin in-process using Flask's test client, SQLite storage,
and an in-process SQLiteTenantStore. No Docker or external process is
needed for testing.
"""

import base64

import pytest

from twins_livekit.app import create_app
from twins_livekit_local.storage_sqlite import SQLiteStorage
from twins_local.tenants import (
    SQLiteTenantStore,
    ensure_default_tenant,
    generate_tenant_id,
    generate_tenant_secret,
    hash_secret,
)


@pytest.fixture
def tenant_store(tmp_path):
    """Fresh tenant store with the default tenant bootstrapped."""
    store = SQLiteTenantStore(db_path=str(tmp_path / "tenants.sqlite3"))
    ensure_default_tenant(store)
    return store


@pytest.fixture
def storage(tmp_path):
    """Create a fresh SQLiteStorage with an ephemeral database."""
    db_path = str(tmp_path / "test_livekit_twin.db")
    return SQLiteStorage(db_path=db_path)


@pytest.fixture
def twin_app(storage, tenant_store):
    """Create a fresh twin app with test configuration."""
    app = create_app(
        storage=storage,
        tenants=tenant_store,
        config={
            "base_url": "http://localhost:7880",
            "upstream_url": "http://localhost:7881",
            "livekit_api_key": "devkey",
            "livekit_api_secret": "secret",
            "app_webhook_url": "",
            "admin_token": "",
        },
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(twin_app):
    """Flask test client."""
    return twin_app.test_client()


@pytest.fixture
def tenant(tenant_store):
    """Create and return a test tenant (distinct from the default tenant)."""
    tenant_id = generate_tenant_id()
    tenant_secret = generate_tenant_secret()
    tenant_store.create_tenant(
        tenant_id=tenant_id,
        secret_hash=hash_secret(tenant_secret),
        friendly_name="Test Tenant",
    )
    return {"tenant_id": tenant_id, "tenant_secret": tenant_secret}


@pytest.fixture
def tenant_headers(tenant):
    """HTTP Basic Auth headers for the test tenant."""
    creds = base64.b64encode(
        f"{tenant['tenant_id']}:{tenant['tenant_secret']}".encode()
    ).decode()
    return {"Authorization": f"Basic {creds}"}
