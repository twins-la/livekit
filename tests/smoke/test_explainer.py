"""Tests for the explainer page."""


class TestExplainer:
    def test_root_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"livekit.twins.la" in resp.data
        assert b"#12b5b0" in resp.data  # LiveKit teal

    def test_explainer_has_livekit_class(self, client):
        resp = client.get("/")
        assert b'class="livekit"' in resp.data

    def test_agent_instructions_plain_text(self, client):
        resp = client.get("/_twin/agent-instructions")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/plain")
        assert b"LiveKit Proxy Twin" in resp.data

    def test_agent_instructions_has_endpoints(self, client):
        resp = client.get("/_twin/agent-instructions")
        assert b"/_twin/health" in resp.data
        assert b"/_twin/faults" in resp.data
        assert b"/_twin/simulate/webhook" in resp.data
