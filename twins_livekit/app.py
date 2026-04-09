"""Flask application factory for the LiveKit proxy twin."""

from flask import Flask, g
from flask_sock import Sock

from .explainer import explainer_bp
from .proxy import proxy_bp
from .twin_plane.routes import twin_plane_bp
from .webhooks import webhook_bp
from .ws_proxy import proxy_websocket


def create_app(storage, config: dict | None = None) -> Flask:
    """Create and configure the LiveKit proxy twin Flask application.

    Args:
        storage: A LiveKitStorage implementation provided by the host.
        config: Configuration dict. Supported keys:
            - base_url: The base URL of the twin (e.g., "http://localhost:7880")
            - upstream_url: URL of the real livekit-server (e.g., "http://localhost:7881")
            - livekit_api_key: LiveKit API key (default: "devkey")
            - livekit_api_secret: LiveKit API secret (default: "secret")
            - app_webhook_url: URL to forward webhooks to the app
            - admin_token: Bearer token for admin twin plane operations
            - process_manager: Optional LiveKitProcess instance for server lifecycle
    """
    config = config or {}

    app = Flask(__name__)
    app.config["TWIN_STORAGE"] = storage
    app.config["TWIN_BASE_URL"] = config.get("base_url", "http://localhost:7880")
    app.config["TWIN_UPSTREAM_URL"] = config.get("upstream_url", "http://localhost:7881")
    app.config["TWIN_LIVEKIT_API_KEY"] = config.get("livekit_api_key", "devkey")
    app.config["TWIN_LIVEKIT_API_SECRET"] = config.get("livekit_api_secret", "secret")
    app.config["TWIN_APP_WEBHOOK_URL"] = config.get("app_webhook_url", "")
    app.config["TWIN_ADMIN_TOKEN"] = config.get("admin_token", "")
    app.config["TWIN_PROCESS_MANAGER"] = config.get("process_manager")

    sock = Sock(app)

    @app.before_request
    def inject_context():
        """Make storage, config, and process manager available to all handlers."""
        g.storage = app.config["TWIN_STORAGE"]
        g.base_url = app.config["TWIN_BASE_URL"]
        g.upstream_url = app.config["TWIN_UPSTREAM_URL"]
        g.livekit_api_key = app.config["TWIN_LIVEKIT_API_KEY"]
        g.livekit_api_secret = app.config["TWIN_LIVEKIT_API_SECRET"]
        g.app_webhook_url = app.config["TWIN_APP_WEBHOOK_URL"]
        g.admin_token = app.config["TWIN_ADMIN_TOKEN"]
        g.process_manager = app.config["TWIN_PROCESS_MANAGER"]

    # Register blueprints
    app.register_blueprint(twin_plane_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(explainer_bp)
    app.register_blueprint(proxy_bp)

    # WebSocket route (must use flask-sock, not blueprint)
    @sock.route("/rtc")
    def rtc_websocket(ws):
        """WebSocket proxy for LiveKit signaling."""
        upstream_base = app.config["TWIN_UPSTREAM_URL"].replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        # Preserve query string (contains access token — redacted in logs)
        from flask import request as flask_request

        qs = flask_request.query_string.decode()
        upstream_url = f"{upstream_base}/rtc"
        if qs:
            upstream_url += f"?{qs}"

        proxy_websocket(ws, upstream_url, app.config["TWIN_STORAGE"])

    return app
