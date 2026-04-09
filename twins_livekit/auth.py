"""Authentication for the LiveKit proxy twin.

LiveKit API auth: API key + secret as HTTP Basic Auth on Twirp endpoints.
Twin plane auth: admin Bearer token for management endpoints.
"""

import functools
import hmac

from flask import g, jsonify, request


def require_livekit_auth(f):
    """Decorator that enforces LiveKit API key/secret auth on proxied endpoints.

    LiveKit server-to-server calls use HTTP Basic Auth where
    username = API key, password = API secret.
    Sets g.api_key on success.
    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or not auth.username or not auth.password:
            # Also check Authorization header for Bearer tokens (LiveKit SDK format)
            auth_header = request.headers.get("Authorization", "")
            if not auth_header:
                return _livekit_auth_error()
            # LiveKit SDKs may send API key as Bearer token — pass through to upstream
            g.api_key = "bearer"
            return f(*args, **kwargs)

        api_key = auth.username
        api_secret = auth.password

        expected_key = g.livekit_api_key
        expected_secret = g.livekit_api_secret

        if not hmac.compare_digest(api_key, expected_key):
            return _livekit_auth_error()
        if not hmac.compare_digest(api_secret, expected_secret):
            return _livekit_auth_error()

        g.api_key = api_key
        return f(*args, **kwargs)

    return wrapper


def require_admin_auth(f):
    """Decorator for twin plane endpoints that require admin auth.

    Accepts Bearer token matching the configured admin token.
    If no admin token is configured, all requests are allowed (local dev).
    Sets g.is_admin on success.
    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        admin_token = g.admin_token

        # No admin token configured — allow all (local dev convenience)
        if not admin_token:
            g.is_admin = True
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _admin_auth_error()

        token = auth_header[7:]
        if not hmac.compare_digest(admin_token, token):
            return _admin_auth_error()

        g.is_admin = True
        return f(*args, **kwargs)

    return wrapper


def _livekit_auth_error():
    resp = jsonify({"code": "unauthenticated", "msg": "invalid API key or secret"})
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Basic realm="LiveKit API"'
    return resp


def _admin_auth_error():
    resp = jsonify({"error": "Authentication required"})
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Bearer realm="Twin Plane"'
    return resp
