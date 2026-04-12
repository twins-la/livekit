"""Twin plane authentication — re-exports from twins_local.tenants.auth.

LiveKit API auth (API key + secret) lives in ../auth.py and governs
proxied Twirp endpoints. Twin Plane auth is the shared tenant layer.
"""

from twins_local.tenants.auth import (
    require_tenant,
    require_tenant_or_admin,
    require_admin,
)

__all__ = ["require_tenant", "require_tenant_or_admin", "require_admin"]
