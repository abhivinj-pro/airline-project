"""Database layer using SQLite with aiosqlite for async access."""

import aiosqlite
import json
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bookings.db")


async def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            current_step TEXT DEFAULT 'search',
            search_params TEXT,
            selected_flight TEXT,
            passenger_details TEXT,
            passenger_draft TEXT,
            ancillaries TEXT,
            abandonment_score REAL DEFAULT 0.0,
            status TEXT DEFAULT 'active',
            recovery_sent INTEGER DEFAULT 0,
            converted INTEGER DEFAULT 0,
            email TEXT,
            phone TEXT
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            trigger_type TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS recovery_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            message TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            clicked INTEGER DEFAULT 0,
            converted INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            total_sessions INTEGER DEFAULT 0,
            abandonments INTEGER DEFAULT 0,
            ai_interventions INTEGER DEFAULT 0,
            ai_saves INTEGER DEFAULT 0,
            recovery_sent INTEGER DEFAULT 0,
            recovery_conversions INTEGER DEFAULT 0
        );
    """)
    await _ensure_column(db, "sessions", "passenger_draft", "TEXT")
    await db.commit()
    await db.close()


async def _ensure_column(db: aiosqlite.Connection, table_name: str, column_name: str, column_type: str):
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    rows = await cursor.fetchall()
    existing_columns = {row[1] for row in rows}
    if column_name not in existing_columns:
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _load_json_blob(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


def _build_abandoned_session_summary(row: dict):
    search_params = _load_json_blob(row.get("search_params"))
    selected_flight = _load_json_blob(row.get("selected_flight"))
    passenger_details = _load_json_blob(row.get("passenger_details"))

    email = row.get("email") or passenger_details.get("email") or ""
    phone = row.get("phone") or passenger_details.get("phone") or ""
    first_name = passenger_details.get("firstName") or ""
    last_name = passenger_details.get("lastName") or ""
    passenger_name = " ".join(part for part in (first_name, last_name) if part).strip()

    return {
        "session_id": row.get("id"),
        "updated_at": row.get("updated_at"),
        "current_step": row.get("current_step") or "search",
        "status": row.get("status") or "active",
        "recovery_sent": bool(row.get("recovery_sent")),
        "converted": bool(row.get("converted")),
        "route": {
            "from": search_params.get("from") or selected_flight.get("from") or "-",
            "to": search_params.get("to") or selected_flight.get("to") or "-",
            "date": search_params.get("date") or "",
        },
        "flight": {
            "flight_no": selected_flight.get("flight_no") or "",
            "airline": selected_flight.get("airline") or "",
            "price": selected_flight.get("price"),
        },
        "passenger": {
            "name": passenger_name,
            "email": email,
            "phone": phone,
            "has_details": bool(passenger_details),
        },
        "recovery_eligible": bool((email or phone) and not row.get("recovery_sent") and not row.get("converted")),
    }


async def create_session(session_id: str):
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
        (session_id, now, now),
    )
    await db.commit()
    await db.close()


async def update_session(session_id: str, **kwargs):
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    sets = ["updated_at = ?"]
    vals = [now]
    for key, value in kwargs.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        sets.append(f"{key} = ?")
        vals.append(value)
    vals.append(session_id)
    await db.execute(
        f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", vals
    )
    await db.commit()
    await db.close()


async def get_session(session_id: str):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = await cursor.fetchone()
    await db.close()
    if row:
        return dict(row)
    return None


async def log_event(session_id: str, event_type: str, event_data: dict = None):
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO events (session_id, event_type, event_data, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, event_type, json.dumps(event_data or {}), now),
    )
    await db.commit()
    await db.close()


async def save_chat_message(session_id: str, role: str, content: str, trigger_type: str = None):
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO chat_messages (session_id, role, content, timestamp, trigger_type) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, now, trigger_type),
    )
    await db.commit()
    await db.close()


async def get_chat_history(session_id: str, limit: int = 20):
    db = await get_db()
    cursor = await db.execute(
        "SELECT role, content, timestamp FROM chat_messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
        (session_id, limit),
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in reversed(rows)]


async def get_last_intervention(session_id: str):
    db = await get_db()
    cursor = await db.execute(
        """SELECT role, content, timestamp, trigger_type
           FROM chat_messages
           WHERE session_id = ?
             AND role = 'assistant'
             AND trigger_type IS NOT NULL
             AND trigger_type NOT LIKE 'human_save_%'
           ORDER BY timestamp DESC
           LIMIT 1""",
        (session_id,),
    )
    row = await cursor.fetchone()
    await db.close()
    if row:
        return dict(row)
    return None


async def get_latest_step_change(session_id: str, step: str):
    db = await get_db()
    cursor = await db.execute(
        """SELECT event_data, timestamp
           FROM events
           WHERE session_id = ?
             AND event_type = 'step_change'
           ORDER BY timestamp DESC
           LIMIT 50""",
        (session_id,),
    )
    rows = await cursor.fetchall()
    await db.close()

    for row in rows:
        try:
            event_data = json.loads(row["event_data"] or "{}")
        except json.JSONDecodeError:
            event_data = {}

        if event_data.get("step") == step:
            return {
                "step": step,
                "timestamp": row["timestamp"],
            }

    return None


async def get_abandoned_sessions():
    """Get explicitly abandoned sessions that are eligible for recovery outreach."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT * FROM sessions
           WHERE status = 'abandoned'
           AND recovery_sent = 0
           AND converted = 0
           AND (COALESCE(email, '') <> '' OR COALESCE(phone, '') <> '')
           ORDER BY updated_at DESC""",
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


async def get_abandoned_session_summaries():
    db = await get_db()
    cursor = await db.execute(
        """SELECT * FROM sessions
           WHERE status = 'abandoned'
           ORDER BY updated_at DESC""",
    )
    rows = await cursor.fetchall()
    await db.close()
    return [_build_abandoned_session_summary(dict(row)) for row in rows]


async def log_recovery(session_id: str, channel: str, message: str):
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO recovery_campaigns (session_id, channel, message, sent_at) VALUES (?, ?, ?, ?)",
        (session_id, channel, message, now),
    )
    await db.execute(
        "UPDATE sessions SET recovery_sent = 1 WHERE id = ?", (session_id,)
    )
    await db.commit()
    await db.close()


async def get_dashboard_metrics():
    db = await get_db()

    cursor = await db.execute("SELECT COUNT(*) as total FROM sessions")
    total = (await cursor.fetchone())["total"]

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM sessions WHERE status = 'active'"
    )
    active = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM sessions WHERE status = 'abandoned'"
    )
    abandoned = (await cursor.fetchone())["cnt"]

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM chat_messages WHERE role = 'assistant'")
    interventions = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM sessions WHERE converted = 1"
    )
    conversions = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM recovery_campaigns"
    )
    recovery_sent = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM recovery_campaigns WHERE converted = 1"
    )
    recovery_conv = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        """SELECT * FROM sessions
           WHERE status = 'abandoned'
           ORDER BY updated_at DESC"""
    )
    abandoned_sessions = [_build_abandoned_session_summary(dict(row)) for row in await cursor.fetchall()]
    recoverable_abandonments = sum(1 for session in abandoned_sessions if session["recovery_eligible"])

    # Per-step abandonment
    cursor = await db.execute(
        """SELECT current_step, COUNT(*) as cnt
           FROM sessions WHERE status = 'abandoned'
           GROUP BY current_step"""
    )
    step_abandonments = {row["current_step"]: row["cnt"] for row in await cursor.fetchall()}

    await db.close()

    return {
        "total_sessions": total,
        "active_sessions": active,
        "abandonments": abandoned,
        "recoverable_abandonments": recoverable_abandonments,
        "abandoned_sessions": abandoned_sessions,
        "ai_interventions": interventions,
        "conversions": conversions,
        "recovery_sent": recovery_sent,
        "recovery_conversions": recovery_conv,
        "conversion_rate": round(conversions / max(total, 1) * 100, 1),
        "step_abandonments": step_abandonments,
    }
