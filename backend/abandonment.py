"""Abandonment detection and risk scoring engine.

Analyzes user behavioral signals to compute a real-time abandonment risk score (0-1).
Different signals carry different weights based on empirical booking funnel data.
"""

from datetime import datetime, timezone

# Signal weights for abandonment risk scoring
SIGNAL_WEIGHTS = {
    "mouse_leave": 0.15,       # Mouse cursor left the browser window
    "tab_switch": 0.12,        # User switched to another tab
    "idle_30s": 0.20,          # User idle for 30+ seconds
    "idle_60s": 0.35,          # User idle for 60+ seconds
    "back_button": 0.25,       # Back button pressed during flow
    "scroll_to_top": 0.08,     # Scrolled back to top (reconsidering)
    "price_hover": 0.05,       # Hovered over price repeatedly (price sensitivity)
    "form_delete": 0.10,       # Deleted entered form data
    "rapid_clicks": 0.06,      # Frustration clicks
    "mobile_keyboard_dismiss": 0.12,  # Dismissed keyboard on mobile (form fatigue)
    "session_long_idle": 0.40, # Server-side: no events for 5+ minutes
}

# Step-based risk multipliers (later steps = higher intent, so abandonment is costlier)
STEP_MULTIPLIERS = {
    "search": 0.3,
    "results": 0.5,
    "passenger": 0.85,
    "ancillaries": 0.9,
    "payment": 1.0,
}

# Intervention thresholds
PROACTIVE_CHAT_THRESHOLD = 0.45    # Show chat bubble proactively
URGENT_INTERVENTION_THRESHOLD = 0.65  # Send urgent "Can I help?" message
ABANDONMENT_THRESHOLD = 0.80       # Mark session as likely abandoned


def compute_risk_score(signals: list[dict], current_step: str) -> dict:
    """Compute abandonment risk score from accumulated behavioral signals.

    Args:
        signals: List of signal dicts with 'type' and optional 'count'
        current_step: Current booking step (search/results/passenger/ancillaries/payment)

    Returns:
        Dict with score, level, recommended_action, and signal_breakdown
    """
    base_score = 0.0
    breakdown = {}

    for signal in signals:
        sig_type = signal.get("type", "")
        count = signal.get("count", 1)
        weight = SIGNAL_WEIGHTS.get(sig_type, 0.05)

        # Diminishing returns for repeated signals (log scale)
        import math
        effective_weight = weight * (1 + math.log(count) * 0.3) if count > 1 else weight
        base_score += effective_weight
        breakdown[sig_type] = round(effective_weight, 3)

    # Apply step multiplier
    step_mult = STEP_MULTIPLIERS.get(current_step, 0.5)
    final_score = min(base_score * step_mult, 1.0)

    # Determine risk level and action
    if final_score >= ABANDONMENT_THRESHOLD:
        level = "critical"
        action = "high_risk_monitor"
    elif final_score >= URGENT_INTERVENTION_THRESHOLD:
        level = "high"
        action = "urgent_chat_intervention"
    elif final_score >= PROACTIVE_CHAT_THRESHOLD:
        level = "medium"
        action = "proactive_chat_nudge"
    else:
        level = "low"
        action = "monitor"

    return {
        "score": round(final_score, 3),
        "level": level,
        "recommended_action": action,
        "signal_breakdown": breakdown,
        "step": current_step,
        "step_multiplier": step_mult,
    }


def get_intervention_context(risk_data: dict, session_data: dict) -> dict:
    """Generate context for the AI assistant based on risk assessment and session data.

    Returns a structured context dict that helps the AI craft relevant, timely responses.
    """
    step = risk_data.get("step", "search")
    score = risk_data.get("score", 0)
    signals = risk_data.get("signal_breakdown", {})

    # Identify primary concern based on dominant signals
    concerns = []
    if "idle_60s" in signals or "idle_30s" in signals:
        concerns.append("indecision_or_distraction")
    if "price_hover" in signals:
        concerns.append("price_sensitivity")
    if "back_button" in signals:
        concerns.append("reconsidering_choice")
    if "rapid_clicks" in signals:
        concerns.append("ui_frustration")
    if "form_delete" in signals:
        concerns.append("form_fatigue")
    if "mouse_leave" in signals or "tab_switch" in signals:
        concerns.append("comparison_shopping")

    # Step-aware messaging cues
    step_cues = {
        "search": "Help them find the right flight. Suggest flexible dates or alternative airports.",
        "results": "They're comparing options. Highlight value, fare differences, and flexibility.",
        "passenger": "They've committed to a flight. Make form-filling easy. Offer to help with details.",
        "ancillaries": "They're close! Gently suggest popular add-ons but don't overwhelm.",
        "payment": "Almost done! Address security concerns, offer price-lock, mention free cancellation.",
    }

    # Urgency calibration
    if score > 0.8:
        tone = "empathetic_urgent"
        approach = "Direct offer to help complete the booking. Mention saving their progress."
    elif score > 0.6:
        tone = "helpful_proactive"
        approach = "Acknowledge they might have questions. Offer specific help for their step."
    else:
        tone = "friendly_subtle"
        approach = "Light touch. Ask if they need any assistance without being pushy."

    return {
        "concerns": concerns,
        "step_cue": step_cues.get(step, ""),
        "tone": tone,
        "approach": approach,
        "flight_context": session_data.get("selected_flight"),
        "search_context": session_data.get("search_params"),
        "passenger_started": session_data.get("passenger_details") is not None,
    }
