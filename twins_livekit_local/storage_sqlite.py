"""SQLite implementation of LiveKitStorage."""

import json
import sqlite3
import threading
from typing import Optional

from twins_livekit.storage import LiveKitStorage


class SQLiteStorage(LiveKitStorage):
    """SQLite-backed storage for the LiveKit proxy twin.

    Thread-safe via a per-instance lock. Uses WAL mode for concurrent reads.
    """

    def __init__(self, db_path: str = "data/livekit_twin.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS rooms (
                        name TEXT PRIMARY KEY,
                        sid TEXT NOT NULL DEFAULT '',
                        max_participants INTEGER NOT NULL DEFAULT 0,
                        empty_timeout INTEGER NOT NULL DEFAULT 300,
                        creation_time INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS participants (
                        room_name TEXT NOT NULL,
                        identity TEXT NOT NULL,
                        sid TEXT NOT NULL DEFAULT '',
                        joined_at INTEGER NOT NULL DEFAULT 0,
                        state TEXT NOT NULL DEFAULT 'ACTIVE',
                        PRIMARY KEY (room_name, identity)
                    );

                    CREATE TABLE IF NOT EXISTS egresses (
                        egress_id TEXT PRIMARY KEY,
                        room_name TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'EGRESS_STARTING',
                        started_at INTEGER NOT NULL DEFAULT 0,
                        stopped_at INTEGER
                    );

                    CREATE TABLE IF NOT EXISTS webhooks (
                        id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        room_name TEXT NOT NULL DEFAULT '',
                        participant_identity TEXT NOT NULL DEFAULT '',
                        timestamp TEXT NOT NULL,
                        payload TEXT NOT NULL DEFAULT '',
                        forwarded INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS faults (
                        id TEXT PRIMARY KEY,
                        target TEXT NOT NULL,
                        action TEXT NOT NULL,
                        config TEXT NOT NULL DEFAULT '{}'
                    );

                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        tenant_id TEXT NOT NULL DEFAULT '',
                        entry TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_logs_tenant ON logs(tenant_id);
                """)
                conn.commit()
            finally:
                conn.close()

    # -- Rooms --

    def create_room(self, data: dict) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO rooms (name, sid, max_participants, empty_timeout, creation_time) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        data["name"],
                        data.get("sid", ""),
                        data.get("max_participants", 0),
                        data.get("empty_timeout", 300),
                        data.get("creation_time", 0),
                    ),
                )
                conn.commit()
                return dict(data)
            finally:
                conn.close()

    def get_room(self, name: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM rooms WHERE name = ?", (name,)).fetchone()
            if row:
                result = dict(row)
                # Add participant count
                count = conn.execute(
                    "SELECT COUNT(*) FROM participants WHERE room_name = ?", (name,)
                ).fetchone()[0]
                result["participant_count"] = count
                return result
            return None
        finally:
            conn.close()

    def list_rooms(self) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM rooms ORDER BY name").fetchall()
            result = []
            for row in rows:
                room = dict(row)
                count = conn.execute(
                    "SELECT COUNT(*) FROM participants WHERE room_name = ?",
                    (room["name"],),
                ).fetchone()[0]
                room["participant_count"] = count
                result.append(room)
            return result
        finally:
            conn.close()

    def delete_room(self, name: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute("DELETE FROM rooms WHERE name = ?", (name,))
                conn.execute("DELETE FROM participants WHERE room_name = ?", (name,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    # -- Participants --

    def add_participant(self, room_name: str, data: dict) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO participants (room_name, identity, sid, joined_at, state) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        room_name,
                        data["identity"],
                        data.get("sid", ""),
                        data.get("joined_at", 0),
                        data.get("state", "ACTIVE"),
                    ),
                )
                conn.commit()
                return dict(data)
            finally:
                conn.close()

    def remove_participant(self, room_name: str, identity: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "DELETE FROM participants WHERE room_name = ? AND identity = ?",
                    (room_name, identity),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def list_participants(self, room_name: str) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM participants WHERE room_name = ? ORDER BY identity",
                (room_name,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # -- Egress --

    def create_egress(self, data: dict) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO egresses (egress_id, room_name, status, started_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        data["egress_id"],
                        data.get("room_name", ""),
                        data.get("status", "EGRESS_STARTING"),
                        data.get("started_at", 0),
                    ),
                )
                conn.commit()
                return dict(data)
            finally:
                conn.close()

    def get_egress(self, egress_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM egresses WHERE egress_id = ?", (egress_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_egress(self, egress_id: str, updates: dict) -> Optional[dict]:
        with self._lock:
            conn = self._get_conn()
            try:
                egress = conn.execute(
                    "SELECT * FROM egresses WHERE egress_id = ?", (egress_id,)
                ).fetchone()
                if not egress:
                    return None

                sets = []
                vals = []
                for key, value in updates.items():
                    if key in ("status", "stopped_at"):
                        sets.append(f"{key} = ?")
                        vals.append(value)

                if sets:
                    vals.append(egress_id)
                    conn.execute(
                        f"UPDATE egresses SET {', '.join(sets)} WHERE egress_id = ?",
                        vals,
                    )
                    conn.commit()

                row = conn.execute(
                    "SELECT * FROM egresses WHERE egress_id = ?", (egress_id,)
                ).fetchone()
                return dict(row)
            finally:
                conn.close()

    def list_egresses(self, room_name: Optional[str] = None) -> list[dict]:
        conn = self._get_conn()
        try:
            if room_name:
                rows = conn.execute(
                    "SELECT * FROM egresses WHERE room_name = ? ORDER BY started_at DESC",
                    (room_name,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM egresses ORDER BY started_at DESC"
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # -- Webhook Events --

    def record_webhook(self, data: dict) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO webhooks (id, event_type, room_name, participant_identity, timestamp, payload, forwarded) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        data.get("id", ""),
                        data["event_type"],
                        data.get("room_name", ""),
                        data.get("participant_identity", ""),
                        data.get("timestamp", ""),
                        data.get("payload", ""),
                        1 if data.get("forwarded") else 0,
                    ),
                )
                conn.commit()
                return dict(data)
            finally:
                conn.close()

    def list_webhooks(
        self,
        room_name: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        conn = self._get_conn()
        try:
            query = "SELECT * FROM webhooks WHERE 1=1"
            params: list = []

            if room_name:
                query += " AND room_name = ?"
                params.append(room_name)
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["forwarded"] = bool(d.get("forwarded"))
                result.append(d)
            return result
        finally:
            conn.close()

    # -- Fault Injection Rules --

    def set_fault(self, fault: dict) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                config_json = json.dumps(fault.get("config", {}))
                conn.execute(
                    "INSERT OR REPLACE INTO faults (id, target, action, config) "
                    "VALUES (?, ?, ?, ?)",
                    (fault["id"], fault["target"], fault["action"], config_json),
                )
                conn.commit()
                fault["config"] = fault.get("config", {})
                return dict(fault)
            finally:
                conn.close()

    def get_fault(self, fault_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM faults WHERE id = ?", (fault_id,)).fetchone()
            if row:
                d = dict(row)
                d["config"] = json.loads(d.get("config", "{}"))
                return d
            return None
        finally:
            conn.close()

    def list_faults(self) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM faults ORDER BY id").fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["config"] = json.loads(d.get("config", "{}"))
                result.append(d)
            return result
        finally:
            conn.close()

    def delete_fault(self, fault_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute("DELETE FROM faults WHERE id = ?", (fault_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def clear_faults(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM faults")
                conn.commit()
            finally:
                conn.close()

    # -- Logs --

    def append_log(self, entry: dict) -> None:
        # entry is a normative record (twins-la/LOGGING.md §3.2) built via
        # twins_local.logs.build_log_record(). Store the full record as a
        # JSON blob; mirror `timestamp` and `tenant_id` as columns for
        # indexing / filtering (§3.3 allows envelope fields).
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO logs (timestamp, tenant_id, entry) VALUES (?, ?, ?)",
                    (
                        entry.get("timestamp", ""),
                        entry.get("tenant_id", ""),
                        json.dumps(entry),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def list_logs(self, limit: int = 100, offset: int = 0,
                  tenant_id: str | None = None) -> list[dict]:
        conn = self._get_conn()
        try:
            if tenant_id is not None:
                rows = conn.execute(
                    "SELECT id, entry FROM logs WHERE tenant_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (tenant_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, entry FROM logs ORDER BY id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            # Flat normative record with pagination `id` envelope (§3.3).
            return [{"id": row["id"], **json.loads(row["entry"])} for row in rows]
        finally:
            conn.close()

    # -- Reset --

    def clear_all(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    DELETE FROM rooms;
                    DELETE FROM participants;
                    DELETE FROM egresses;
                    DELETE FROM webhooks;
                    DELETE FROM faults;
                    DELETE FROM logs;
                """)
                conn.commit()
            finally:
                conn.close()
