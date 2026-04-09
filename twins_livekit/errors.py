"""LiveKit-style error responses (Twirp format)."""

from flask import jsonify


def twirp_error(code: str, msg: str, http_status: int):
    """Return a Twirp-format error response.

    LiveKit uses Twirp RPC which returns errors as:
    {"code": "<twirp_code>", "msg": "<message>"}
    """
    resp = jsonify({"code": code, "msg": msg})
    resp.status_code = http_status
    return resp


def not_found(msg: str = "not found"):
    return twirp_error("not_found", msg, 404)


def internal_error(msg: str = "internal error"):
    return twirp_error("internal", msg, 500)


def unauthenticated(msg: str = "unauthenticated"):
    return twirp_error("unauthenticated", msg, 401)


def permission_denied(msg: str = "permission denied"):
    return twirp_error("permission_denied", msg, 403)


def bad_request(msg: str = "invalid argument"):
    return twirp_error("invalid_argument", msg, 400)


def unavailable(msg: str = "service unavailable"):
    return twirp_error("unavailable", msg, 503)
