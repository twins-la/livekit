"""ID generation for LiveKit twin resources."""

import secrets
import uuid


def generate_fault_id() -> str:
    """Generate a unique fault rule ID."""
    return f"FT_{secrets.token_hex(8)}"


def generate_room_sid() -> str:
    """Generate a LiveKit-style room SID."""
    return f"RM_{secrets.token_hex(12)}"


def generate_participant_sid() -> str:
    """Generate a LiveKit-style participant SID."""
    return f"PA_{secrets.token_hex(12)}"


def generate_egress_id() -> str:
    """Generate a LiveKit-style egress ID."""
    return f"EG_{secrets.token_hex(12)}"


def generate_webhook_id() -> str:
    """Generate a unique webhook event ID."""
    return str(uuid.uuid4())
