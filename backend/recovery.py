"""Recovery notification system.

Handles personalized outreach to users who abandoned their booking.
Supports email, SMS, and WhatsApp channels (simulated for MVP).
"""

import json
from datetime import datetime, timezone
from backend.database import get_abandoned_session_summaries, get_abandoned_sessions, log_recovery, get_session
from backend.ai_engine import generate_recovery_message


async def process_abandoned_sessions():
    """Scan for abandoned sessions and trigger recovery campaigns.

    Returns a summary of actions taken.
    """
    abandoned_sessions = await get_abandoned_session_summaries()
    sessions = await get_abandoned_sessions()
    results = []

    for session in sessions:
        session_id = session["id"]
        email = session.get("email")
        phone = session.get("phone")

        # Choose channel based on saved contact details.
        if email:
            channel = "email"
        elif phone:
            channel = "sms"
        else:
            continue  # No contact info, skip

        # Generate personalized recovery message
        recovery_msg = await generate_recovery_message(session, channel)

        # Log the recovery attempt (in production, this would send the actual message)
        await log_recovery(
            session_id=session_id,
            channel=channel,
            message=json.dumps(recovery_msg),
        )

        results.append({
            "session_id": session_id,
            "channel": channel,
            "subject": recovery_msg.get("subject", ""),
            "status": "sent",
        })

    return {
        "abandoned_total": len(abandoned_sessions),
        "eligible": len(sessions),
        "processed": len(results),
        "skipped": max(len(abandoned_sessions) - len(sessions), 0),
        "campaigns": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_recovery_deeplink(session_id: str, base_url: str = "https://airwave-airlines.com") -> str:
    """Build a deep link that restores the user's booking session."""
    return f"{base_url}/booking/resume?sid={session_id}&utm_source=recovery&utm_medium=ai"


async def get_recovery_preview(session_id: str) -> dict:
    """Preview what the recovery message would look like for a given session."""
    session = await get_session(session_id)
    if not session:
        return {"error": "Session not found"}

    email_msg = await generate_recovery_message(session, "email")
    sms_msg = await generate_recovery_message(session, "sms")

    return {
        "session_id": session_id,
        "email_preview": email_msg,
        "sms_preview": sms_msg,
        "deeplink": build_recovery_deeplink(session_id),
    }
