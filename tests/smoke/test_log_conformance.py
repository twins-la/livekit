"""LOGGING.md §3.2 conformance smoke test for the LiveKit twin."""

REQUIRED_FIELDS = {
    "timestamp", "twin", "tenant_id", "correlation_id",
    "plane", "operation", "resource", "outcome", "reason", "details",
}
VALID_PLANES = {"twin", "control", "data", "runtime"}
VALID_OUTCOMES = {"success", "failure"}


def _assert_record_conforms(rec):
    assert REQUIRED_FIELDS.issubset(rec.keys()), rec
    assert rec["timestamp"].endswith("Z")
    assert rec["twin"] == "livekit"
    assert isinstance(rec["tenant_id"], str) and rec["tenant_id"]
    assert isinstance(rec["correlation_id"], str) and rec["correlation_id"]
    assert rec["plane"] in VALID_PLANES, rec
    assert isinstance(rec["operation"], str) and rec["operation"]
    assert rec["resource"] is None or (
        isinstance(rec["resource"], dict)
        and set(rec["resource"].keys()) == {"type", "id"}
    )
    assert rec["outcome"] in VALID_OUTCOMES, rec
    if rec["outcome"] == "failure":
        assert isinstance(rec["reason"], str) and rec["reason"].strip()
    assert isinstance(rec["details"], dict)


def test_tenant_and_reset_logs_conform(client, tenant_headers):
    # POST /_twin/tenants (unauth) emits twin.tenant.create; /_twin/reset
    # clears and emits twin.reset. Both visible to any bearer since the
    # fixture leaves admin_token="" (local-dev: accept any bearer).
    resp = client.post("/_twin/tenants", json={"friendly_name": "Conf"})
    assert resp.status_code == 201
    admin_headers = {"Authorization": "Bearer any"}
    resp = client.post("/_twin/reset", headers=admin_headers)
    assert resp.status_code == 204

    resp = client.get("/_twin/logs", headers=admin_headers)
    logs = resp.get_json()["logs"]
    # /reset clears logs; one twin.reset record should remain.
    assert logs
    for rec in logs:
        _assert_record_conforms(rec)


def test_correlation_id_is_echoed(client):
    resp = client.get("/_twin/health", headers={"X-Correlation-Id": "caller-xyz"})
    assert resp.headers.get("X-Correlation-Id") == "caller-xyz"
