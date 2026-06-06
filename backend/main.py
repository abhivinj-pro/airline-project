"""AirWave Airlines — AI Booking Recovery MVP

FastAPI application providing:
- REST API for session tracking and event logging
- WebSocket endpoint for real-time AI chat
- Abandonment detection and scoring
- Recovery campaign management
- Analytics dashboard
"""

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.database import (
    init_db, create_session, update_session, get_session,
    log_event, save_chat_message, get_chat_history, get_dashboard_metrics,
    get_last_intervention, get_latest_step_change,
)
from backend.abandonment import compute_risk_score, get_intervention_context
from backend.ai_engine import (
    generate_proactive_message,
    chat_response,
    generate_human_save_desk_intro,
    get_human_save_desk_eligibility,
    resolve_human_agent_request,
    merge_passenger_draft,
)
from backend.recovery import process_abandoned_sessions, get_recovery_preview


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="AirWave AI Booking Recovery",
    description="AI-powered booking abandonment detection and recovery system",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

DISABLE_HTTP_CACHE = os.getenv("DISABLE_HTTP_CACHE", "0").lower() in {"1", "true", "yes", "on"}
INTERVENTION_COOLDOWN_SECONDS = 120


@app.middleware("http")
async def disable_http_cache_for_dev(request: Request, call_next):
    response = await call_next(request)

    if not DISABLE_HTTP_CACHE:
        return response

    if request.method in {"GET", "HEAD"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


# ─── Pydantic Models ──────────────────────────────────────────────

class SessionCreate(BaseModel):
    session_id: str | None = None

class EventLog(BaseModel):
    session_id: str
    event_type: str
    event_data: dict = {}

class SessionUpdate(BaseModel):
    session_id: str
    current_step: str | None = None
    search_params: dict | None = None
    selected_flight: dict | None = None
    passenger_details: dict | None = None
    passenger_draft: dict | None = None
    ancillaries: dict | None = None
    email: str | None = None
    phone: str | None = None

class SessionAbandon(BaseModel):
    session_id: str
    current_step: str | None = None
    reason: str = "explicit_exit"

class RiskAssessment(BaseModel):
    session_id: str
    signals: list[dict]
    current_step: str

class ChatMessage(BaseModel):
    session_id: str
    message: str


class HumanAssistRequest(BaseModel):
    session_id: str


# ─── Pages ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def booking_page():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    with open("static/dashboard.html", "r") as f:
        return HTMLResponse(content=f.read())


# ─── Session APIs ─────────────────────────────────────────────────

@app.post("/api/session")
async def create_new_session(data: SessionCreate):
    session_id = data.session_id or str(uuid.uuid4())
    await create_session(session_id)
    return {"session_id": session_id, "status": "created"}

@app.put("/api/session")
async def update_booking_session(data: SessionUpdate):
    kwargs = {k: v for k, v in data.model_dump().items() if k != "session_id" and v is not None}
    await update_session(data.session_id, **kwargs)
    return {"status": "updated"}


@app.post("/api/session/abandon")
async def abandon_booking_session(data: SessionAbandon):
    session = await get_session(data.session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "session_not_found"})

    if bool(session.get("converted")) or session.get("status") == "completed":
        return {"status": "ignored", "reason": "already_completed"}

    current_step = data.current_step or session.get("current_step") or "search"
    await update_session(data.session_id, status="abandoned", current_step=current_step)
    await log_event(
        data.session_id,
        "session_abandoned",
        {
            "reason": data.reason,
            "step": current_step,
        },
    )
    return {
        "status": "abandoned",
        "session_id": data.session_id,
        "current_step": current_step,
    }


# ─── Event Tracking ──────────────────────────────────────────────

@app.post("/api/event")
async def track_event(data: EventLog):
    await log_event(data.session_id, data.event_type, data.event_data)
    return {"status": "logged"}


# ─── Abandonment Risk Scoring ────────────────────────────────────

@app.post("/api/risk")
async def assess_risk(data: RiskAssessment):
    risk = compute_risk_score(data.signals, data.current_step)

    # Update session with latest score
    await update_session(data.session_id, abandonment_score=risk["score"])

    # Generate intervention if needed
    intervention = None
    if risk["recommended_action"] in ("proactive_chat_nudge", "urgent_chat_intervention"):
        session = await get_session(data.session_id)
        if session:
            ctx = get_intervention_context(risk, session)
            last_intervention = await get_last_intervention(data.session_id)
            latest_step_change = await get_latest_step_change(data.session_id, data.current_step)
            current_step_started_at = latest_step_change["timestamp"] if latest_step_change else None
            try:
                if not _is_intervention_on_cooldown(last_intervention, step_started_at=current_step_started_at):
                    message = await generate_proactive_message(ctx)
                    await save_chat_message(data.session_id, "assistant", message, trigger_type=risk["recommended_action"])
                    intervention = {"message": message, "trigger": risk["recommended_action"]}
            except Exception as e:
                if not _is_intervention_on_cooldown(last_intervention, step_started_at=current_step_started_at):
                    intervention = {"message": _get_fallback_message(risk, data.current_step), "trigger": "fallback"}
                    await save_chat_message(data.session_id, "assistant", intervention["message"], trigger_type="fallback")

    return {
        "risk": risk,
        "intervention": intervention,
    }


def _get_fallback_message(risk: dict, step: str) -> str:
    """Fallback messages when AI is unavailable."""
    fallbacks = {
        "search": "Need help finding the perfect flight? I'm here to help! 🛫",
        "results": "I can help you compare these options — just ask!",
        "passenger": "Almost there! Need help with the passenger details?",
        "ancillaries": "Great choices! Want me to suggest popular add-ons for your route?",
        "payment": "You're one step away! I can help if you have any concerns about completing your booking.",
    }
    return fallbacks.get(step, "Hi there! Can I help you with your booking?")


def _is_intervention_on_cooldown(last_intervention: dict | None, step_started_at: str | None = None) -> bool:
    if not last_intervention:
        return False

    timestamp = last_intervention.get("timestamp")
    if not timestamp:
        return False

    try:
        sent_at = datetime.fromisoformat(timestamp)
    except ValueError:
        return False

    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)

    if step_started_at:
        try:
            step_started = datetime.fromisoformat(step_started_at)
        except ValueError:
            step_started = None

        if step_started is not None:
            if step_started.tzinfo is None:
                step_started = step_started.replace(tzinfo=timezone.utc)
            if sent_at < step_started:
                return False

    elapsed = (datetime.now(timezone.utc) - sent_at).total_seconds()
    return elapsed < INTERVENTION_COOLDOWN_SECONDS


def _load_json_field(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


async def _record_human_handoff(session_id: str, handoff: dict):
    criteria = handoff.get("criteria") or {}
    await log_event(
        session_id,
        "human_save_desk_escalated",
        {
            **criteria,
            "priority": handoff.get("priority", "high"),
            "agent_brief": handoff.get("agent_brief", ""),
        },
    )


# ─── Chat API (REST fallback) ───────────────────────────────────

@app.post("/api/chat")
async def chat_endpoint(data: ChatMessage):
    # Save user message
    await save_chat_message(data.session_id, "user", data.message)

    # Get context
    session = await get_session(data.session_id)
    history = await get_chat_history(data.session_id)

    if not session:
        return {"response": "I'd be happy to help! Could you start a new search?"}

    passenger_draft = None
    human_handoff = None

    try:
        chat_result = await chat_response(
            user_message=data.message,
            chat_history=history,
            session_context=session,
        )
        response_text = chat_result.response
        human_handoff = chat_result.human_handoff
        if chat_result.passenger_draft:
            existing_draft = _load_json_field(session.get("passenger_draft"))
            passenger_draft = merge_passenger_draft(existing_draft, chat_result.passenger_draft)
            await update_session(data.session_id, passenger_draft=passenger_draft)
        if human_handoff:
            await _record_human_handoff(data.session_id, human_handoff)
    except Exception:
        response_text = "I'm here to help with your booking! What questions do you have?"

    # Save assistant response
    await save_chat_message(
        data.session_id,
        "assistant",
        response_text,
        trigger_type="human_save_handoff" if human_handoff else None,
    )

    return {
        "response": response_text,
        "passenger_draft": passenger_draft,
        "review_required": bool(passenger_draft),
        "human_handoff": human_handoff,
    }


@app.post("/api/human-save-desk/engage")
async def engage_human_save_desk(data: HumanAssistRequest):
    session = await get_session(data.session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "session_not_found"})

    eligibility = get_human_save_desk_eligibility(session)
    if not eligibility["eligible"]:
        return {"eligible": False, "criteria": eligibility}

    message = await generate_human_save_desk_intro(session)
    await save_chat_message(data.session_id, "assistant", message, trigger_type="human_save_ai_intro")
    await log_event(data.session_id, "human_save_desk_prompted", eligibility)

    return {
        "eligible": True,
        "message": message,
        "criteria": eligibility,
    }


@app.post("/api/human-save-desk/escalate")
async def escalate_human_save_desk(data: HumanAssistRequest):
    session = await get_session(data.session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "session_not_found"})

    handoff = await resolve_human_agent_request(session)
    if not handoff.eligible:
        return {"eligible": False, "connected": False, "criteria": handoff.criteria}

    assistant_message = handoff.assistant_message

    await save_chat_message(data.session_id, "assistant", assistant_message, trigger_type="human_save_handoff")
    await _record_human_handoff(data.session_id, handoff.model_dump(exclude_none=True))

    return {
        "eligible": True,
        "connected": True,
        "mode": "simulated_handoff",
        "message": assistant_message,
        "agent_brief": handoff.agent_brief or "",
        "priority": handoff.priority or "high",
        "criteria": handoff.criteria,
    }


# ─── WebSocket Chat ──────────────────────────────────────────────

@app.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            user_message = msg.get("message", "")
            await save_chat_message(session_id, "user", user_message)

            session = await get_session(session_id)
            history = await get_chat_history(session_id)
            passenger_draft = None
            human_handoff = None

            try:
                chat_result = await chat_response(
                    user_message=user_message,
                    chat_history=history,
                    session_context=session or {},
                )
                response_text = chat_result.response
                human_handoff = chat_result.human_handoff
                if session and chat_result.passenger_draft:
                    existing_draft = _load_json_field(session.get("passenger_draft"))
                    passenger_draft = merge_passenger_draft(existing_draft, chat_result.passenger_draft)
                    await update_session(session_id, passenger_draft=passenger_draft)
                if human_handoff:
                    await _record_human_handoff(session_id, human_handoff)
            except Exception:
                response_text = "I'm here to help! Could you rephrase your question?"

            await save_chat_message(
                session_id,
                "assistant",
                response_text,
                trigger_type="human_save_handoff" if human_handoff else None,
            )

            await websocket.send_text(json.dumps({
                "type": "chat_response",
                "message": response_text,
                "passenger_draft": passenger_draft,
                "review_required": bool(passenger_draft),
                "human_handoff": human_handoff,
            }))

    except WebSocketDisconnect:
        pass


# ─── Recovery APIs ───────────────────────────────────────────────

@app.post("/api/recovery/trigger")
async def trigger_recovery():
    """Manually trigger recovery campaign processing."""
    results = await process_abandoned_sessions()
    return results

@app.get("/api/recovery/preview/{session_id}")
async def preview_recovery(session_id: str):
    """Preview recovery messages for a specific session."""
    preview = await get_recovery_preview(session_id)
    return preview


# ─── Dashboard API ───────────────────────────────────────────────

@app.get("/api/metrics")
async def get_metrics():
    metrics = await get_dashboard_metrics()
    return metrics


# ─── Booking Completion ─────────────────────────────────────────

@app.post("/api/booking/complete")
async def complete_booking(data: dict):
    """Mark a session as converted (booking completed)."""
    session_id = data.get("session_id")
    if session_id:
        await update_session(session_id, status="completed", converted=1)
        await log_event(session_id, "booking_completed", {})
    return {"status": "completed", "booking_ref": f"SW-{uuid.uuid4().hex[:8].upper()}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
