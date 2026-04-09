"""Shared fixtures for LiveKit twin smoke tests."""

import pytest

from twins_livekit.app import create_app
from twins_livekit_local.storage_sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    """Create a fresh SQLiteStorage with an ephemeral database."""
    db_path = str(tmp_path / "test_livekit_twin.db")
    return SQLiteStorage(db_path=db_path)


@pytest.fixture
def twin_app(storage):
    """Create a fresh twin app with test configuration."""
    app = create_app(
        storage=storage,
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
