"""LiveKit twin storage abstract base class."""

from abc import ABC, abstractmethod
from typing import Optional


class LiveKitStorage(ABC):
    """State tracked by the twin proxy (not the underlying livekit-server)."""

    # -- Rooms --

    @abstractmethod
    def create_room(self, data: dict) -> dict:
        """Create a room record.

        data: {name, max_participants, empty_timeout, creation_time}
        """

    @abstractmethod
    def get_room(self, name: str) -> Optional[dict]:
        """Fetch a room by name. Returns None if not found."""

    @abstractmethod
    def list_rooms(self) -> list[dict]:
        """List all rooms."""

    @abstractmethod
    def delete_room(self, name: str) -> bool:
        """Delete a room by name. Returns True if deleted, False if not found."""

    # -- Participants --

    @abstractmethod
    def add_participant(self, room_name: str, data: dict) -> dict:
        """Add a participant to a room.

        data: {identity, sid, joined_at, state}
        """

    @abstractmethod
    def remove_participant(self, room_name: str, identity: str) -> bool:
        """Remove a participant. Returns True if removed."""

    @abstractmethod
    def list_participants(self, room_name: str) -> list[dict]:
        """List participants in a room."""

    # -- Egress --

    @abstractmethod
    def create_egress(self, data: dict) -> dict:
        """Create an egress record.

        data: {egress_id, room_name, status, started_at}
        """

    @abstractmethod
    def get_egress(self, egress_id: str) -> Optional[dict]:
        """Fetch an egress by ID."""

    @abstractmethod
    def update_egress(self, egress_id: str, updates: dict) -> Optional[dict]:
        """Update an egress record. Returns updated record or None."""

    @abstractmethod
    def list_egresses(self, room_name: Optional[str] = None) -> list[dict]:
        """List egresses, optionally filtered by room."""

    # -- Webhook Events --

    @abstractmethod
    def record_webhook(self, data: dict) -> dict:
        """Record a webhook event.

        data: {event_type, room_name, participant_identity, timestamp, payload}
        """

    @abstractmethod
    def list_webhooks(
        self,
        room_name: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List recorded webhook events."""

    # -- Fault Injection Rules --

    @abstractmethod
    def set_fault(self, fault: dict) -> dict:
        """Create or update a fault injection rule.

        fault: {id, target, action, config}
        """

    @abstractmethod
    def get_fault(self, fault_id: str) -> Optional[dict]:
        """Fetch a fault rule by ID."""

    @abstractmethod
    def list_faults(self) -> list[dict]:
        """List all fault rules."""

    @abstractmethod
    def delete_fault(self, fault_id: str) -> bool:
        """Delete a fault rule. Returns True if deleted."""

    @abstractmethod
    def clear_faults(self) -> None:
        """Delete all fault rules."""

    # -- Logs --

    @abstractmethod
    def append_log(self, entry: dict) -> None:
        """Append an operation log entry."""

    @abstractmethod
    def list_logs(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """List operation logs."""

    # -- Reset --

    @abstractmethod
    def clear_all(self) -> None:
        """Clear all state (rooms, participants, egresses, webhooks, faults, logs)."""
