"""AI Engine powered by a LlamaIndex ReAct agent.

Provides:
- Tool-driven chat assistance with structured passenger extraction
- FAQ-backed support answers
- Human-agent handoff routing for eligible bookings
- Payment and booking status guidance
- Recovery and human-handoff message generation
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar, cast

from dotenv import load_dotenv
from llama_index.core import SimpleDirectoryReader
from llama_index.core.agent.workflow import ReActAgent
from llama_index.core.llms import ChatMessage
from llama_index.core.tools import FunctionTool
from llama_index.llms.openrouter import OpenRouter
from pydantic import BaseModel, Field

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
FAQ_PATH = ROOT_DIR / "data" / "customer_support_faq.md"

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
INTERNATIONAL_DESTINATION_CODES = {"DXB", "SIN", "BKK", "LHR"}
HUMAN_AGENT_TOOL_FALLBACK = "Handle the response through generic AI message."
HUMAN_AGENT_GREETING = "Hi, I am Tata Birla. How can I assist you?"
PRICE_LOCK_POLICY = (
    "In this demo, a price lock means holding the currently displayed fare for 4 hours. "
    "Do not mention any fee, charge, deposit, surcharge, or purchase requirement for price lock unless one is explicitly provided in the booking context or FAQ."
)

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class PassengerDraft(BaseModel):
    """Structured passenger fields that can be applied to the booking form."""

    firstName: str | None = Field(default=None, description="Passenger first name when provided")
    lastName: str | None = Field(default=None, description="Passenger last name when provided")
    email: str | None = Field(default=None, description="Passenger email address when provided")
    phone: str | None = Field(default=None, description="Passenger phone number when provided")
    dob: str | None = Field(default=None, description="Passenger date of birth in ISO format when provided")
    passport: str | None = Field(default=None, description="Passenger passport number when provided")


class RecoveryMessage(BaseModel):
    subject: str = Field(description="Email or notification subject line")
    body: str = Field(description="Warm recovery body copy")
    cta_text: str = Field(description="Recovery call to action label")


class HumanHandoff(BaseModel):
    assistant_message: str = Field(description="Customer-facing handoff message")
    agent_brief: str = Field(description="Internal brief for the human specialist")
    priority: Literal["high", "urgent"] = Field(description="Handoff priority")


class HumanAgentToolResult(BaseModel):
    eligible: bool = Field(description="Whether the traveler qualifies for a human specialist handoff")
    assistant_message: str = Field(description="Customer-facing message or internal fallback instruction")
    criteria: dict[str, Any] = Field(default_factory=dict, description="Eligibility context for the handoff decision")
    agent_brief: str | None = Field(default=None, description="Internal handoff brief for the specialist")
    priority: Literal["high", "urgent"] | None = Field(default=None, description="Priority when a handoff is created")


class ChatTurnResult(BaseModel):
    response: str
    passenger_draft: dict[str, str] | None = None
    review_required: bool = False
    human_handoff: dict[str, Any] | None = None


class ChatToolPlan(BaseModel):
    capture_passenger_details: bool = Field(
        default=False,
        description="True when the latest message provides or updates passenger form data.",
    )
    payment_guidance: bool = Field(
        default=False,
        description="True when the latest message is about payment, confirmation, booking completion, or confirmation emails.",
    )
    faq_lookup: bool = Field(
        default=False,
        description="True when the latest message is a policy or support question best answered from the FAQ.",
    )
    human_agent_tool: bool = Field(
        default=False,
        description="True when the latest message asks to connect with a human agent, specialist, or representative.",
    )


SYSTEM_PROMPT = f"""You are AirAssist, the airline booking assistant for AirWave.

Your job is to help travelers move through the booking flow accurately.

Rules:
- Keep answers concise, warm, and grounded in the current booking context.
- Never claim a booking is confirmed, paid, ticketed, or emailed unless the payment guidance tool indicates the booking is completed.
- Whenever a user provides passenger details or asks to fill or update the passenger form, you must call capture_passenger_details.
- Whenever a user asks about payment, booking confirmation, booking completion, or confirmation emails, you must call payment_guidance.
- Whenever a user asks a policy or support question, prefer faq_lookup.
- Whenever a user asks to speak with a human agent, specialist, representative, or real person, you must call human_agent_tool.
- If human_agent_tool returns eligible=true, use its assistant_message as your final answer without paraphrasing.
- If human_agent_tool returns eligible=false and asks you to handle the response through generic AI message, continue helping yourself and do not expose that internal instruction.
- If passenger details are captured, explain that they were prepared for review in the passenger form.
- Do not invent airline policies or booking state.
- {PRICE_LOCK_POLICY}
- Keep responses under 3 sentences unless the user asks for more detail.
"""


def _format_inr(amount: Any) -> str:
    try:
        return f"INR {int(amount):,}"
    except (TypeError, ValueError):
        return str(amount)


def _load_json_field(value: Any) -> dict:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


def merge_passenger_draft(existing_draft: dict | None, new_draft: dict | None) -> dict:
    merged = dict(existing_draft or {})
    for key, value in (new_draft or {}).items():
        if value:
            merged[key] = value
    return merged


def _get_session_trip_context(session_data: dict) -> dict:
    search = _load_json_field(session_data.get("search_params"))
    flight = _load_json_field(session_data.get("selected_flight"))
    passengers_raw = search.get("passengers", 1)

    try:
        passenger_count = int(passengers_raw)
    except (TypeError, ValueError):
        passenger_count = 1

    per_traveler_price = flight.get("price")
    try:
        trip_value = int(per_traveler_price or 0) * passenger_count
    except (TypeError, ValueError):
        trip_value = per_traveler_price

    return {
        "search": search,
        "flight": flight,
        "passenger_count": passenger_count,
        "route": f"{search.get('from', '?')} -> {search.get('to', '?')}",
        "per_traveler_price": per_traveler_price,
        "trip_value": trip_value,
    }


def _extract_destination_code(destination: str | None) -> str:
    if not destination or "(" not in destination or ")" not in destination:
        return ""
    return destination.rsplit("(", 1)[-1].replace(")", "").strip().upper()


def get_human_save_desk_eligibility(session_context: dict) -> dict[str, Any]:
    search = _load_json_field(session_context.get("search_params"))
    flight = _load_json_field(session_context.get("selected_flight"))
    current_step = session_context.get("current_step")

    try:
        passenger_count = int(search.get("passengers", 0))
    except (TypeError, ValueError):
        passenger_count = 0

    destination = flight.get("to") or search.get("to") or ""
    destination_code = _extract_destination_code(destination)
    is_international = destination_code in INTERNATIONAL_DESTINATION_CODES

    reasons = []
    if current_step != "payment":
        reasons.append("not_on_payment_step")
    if passenger_count < 6:
        reasons.append("traveler_count_below_threshold")
    if not is_international:
        reasons.append("destination_not_international")

    return {
        "eligible": len(reasons) == 0,
        "current_step": current_step,
        "passenger_count": passenger_count,
        "destination": destination,
        "destination_code": destination_code,
        "is_international": is_international,
        "reasons": reasons,
    }


async def resolve_human_agent_request(session_context: dict) -> HumanAgentToolResult:
    criteria = get_human_save_desk_eligibility(session_context)
    if not criteria["eligible"]:
        return HumanAgentToolResult(
            eligible=False,
            assistant_message=HUMAN_AGENT_TOOL_FALLBACK,
            criteria=criteria,
        )

    handoff = await generate_human_handoff_summary(session_context)
    return HumanAgentToolResult(
        eligible=True,
        assistant_message=HUMAN_AGENT_GREETING,
        criteria=criteria,
        agent_brief=handoff.get("agent_brief", ""),
        priority=handoff.get("priority", "high"),
    )


def _response_text(response: Any) -> str:
    message = getattr(response, "message", None)
    content = getattr(message, "content", None) if message else None
    return content or str(response)


def _format_history(chat_history: list[dict], latest_user_message: str) -> str:
    history_slice = chat_history[-8:]
    if history_slice and history_slice[-1].get("role") == "user" and history_slice[-1].get("content") == latest_user_message:
        history_slice = history_slice[:-1]

    if not history_slice:
        return "No previous chat history."

    lines = []
    for message in history_slice:
        role = message.get("role", "assistant")
        content = message.get("content", "")
        lines.append(f"{role.title()}: {content}")
    return "\n".join(lines)


def _build_session_snapshot(session_context: dict) -> str:
    snapshot = {
        "status": session_context.get("status", "active"),
        "converted": bool(session_context.get("converted", 0)),
        "current_step": session_context.get("current_step", "search"),
        "search": _load_json_field(session_context.get("search_params")),
        "selected_flight": _load_json_field(session_context.get("selected_flight")),
        "passenger_details": _load_json_field(session_context.get("passenger_details")),
        "pending_passenger_draft": _load_json_field(session_context.get("passenger_draft")),
    }
    return json.dumps(snapshot, ensure_ascii=True)


def _payment_status_summary(session_context: dict) -> str:
    current_step = session_context.get("current_step", "search")
    is_completed = bool(session_context.get("converted")) or session_context.get("status") == "completed"

    if is_completed:
        return (
            "Booking status: completed. Payment has already been recorded, the booking is confirmed, and confirmation details can be shared with the traveler."
        )

    if current_step == "payment":
        return (
            "Booking status: not completed. The traveler is on the payment step, but the booking is only confirmed after they finish the payment form and click Pay & Confirm Booking. No confirmation email should be implied yet."
        )

    return (
        f"Booking status: not completed. The traveler is currently on the {current_step} step. Payment has not been completed, and the booking is not yet confirmed."
    )


def _field_summary(passenger_draft: dict[str, str]) -> str:
    field_names = []
    if passenger_draft.get("firstName") or passenger_draft.get("lastName"):
        field_names.append("name")
    if passenger_draft.get("email"):
        field_names.append("email")
    if passenger_draft.get("phone"):
        field_names.append("phone")
    if passenger_draft.get("dob"):
        field_names.append("date of birth")
    if passenger_draft.get("passport"):
        field_names.append("passport number")

    if not field_names:
        return "traveler details"
    if len(field_names) == 1:
        return field_names[0]
    return ", ".join(field_names[:-1]) + f" and {field_names[-1]}"


def _passenger_review_note(passenger_draft: dict[str, str]) -> str:
    return (
        f"I've prepared the {_field_summary(passenger_draft)} for review in the passenger form. "
        "Please check the fields there before you continue."
    )


def _apply_confirmation_guardrails(response_text: str, session_context: dict) -> str:
    is_completed = bool(session_context.get("converted")) or session_context.get("status") == "completed"
    if is_completed:
        return response_text

    lowered = response_text.lower()
    blocked_phrases = (
        "booking is confirmed",
        "flight is confirmed",
        "confirmation email",
        "email shortly",
        "payment complete",
        "payment processed",
        "you're booked",
        "you are booked",
    )
    if any(phrase in lowered for phrase in blocked_phrases):
        current_step = session_context.get("current_step", "search")
        if current_step == "payment":
            return "The booking is not confirmed yet. Please complete the payment form and click Pay & Confirm Booking to finish it."
        return "The booking is not confirmed yet. Please continue through the remaining form steps and complete payment to finalize it."

    return response_text


@lru_cache(maxsize=1)
def _get_llm() -> OpenRouter:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)

    return OpenRouter(
        api_key=api_key,
        model=model,
        temperature=0.2,
        max_tokens=4096,
        timeout=60.0,
    )


async def _text_completion(system_prompt: str, user_prompt: str) -> str:
    llm = _get_llm()
    response = await llm.achat(
        [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
    )
    return _response_text(response)


async def _structured_completion(output_cls: type[StructuredModel], system_prompt: str, user_prompt: str) -> StructuredModel:
    structured_llm = _get_llm().as_structured_llm(output_cls=output_cls)
    response = await structured_llm.achat(
        [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
    )
    return cast(StructuredModel, response.raw)


@lru_cache(maxsize=1)
def _faq_text() -> str:
    if not FAQ_PATH.exists():
        return "FAQ document unavailable."

    docs = SimpleDirectoryReader(input_files=[str(FAQ_PATH)]).load_data()
    return "\n\n".join(doc.text for doc in docs)


async def _plan_chat_tools(user_message: str, session_context: dict) -> ChatToolPlan:
    return await _structured_completion(
        ChatToolPlan,
        system_prompt=(
            "You decide which tools an airline booking agent must use for the latest user message. "
            "Mark capture_passenger_details true when the message gives or updates passenger fields like full name, first name, last name, email, phone, date of birth, or passport number. "
            "Mark payment_guidance true when the message is about payment, booking confirmation, finalization, or whether an email should be sent. "
            "Mark faq_lookup true for policy or support questions such as cancellation, baggage, seats, check-in, or fare rules. "
            "Mark human_agent_tool true when the traveler asks to speak with a human agent, representative, specialist, or real person. "
            "Multiple flags may be true at once."
        ),
        user_prompt=(
            f"Current booking step: {session_context.get('current_step', 'search')}\n"
            f"Booking status: {session_context.get('status', 'active')}\n"
            f"Converted: {bool(session_context.get('converted', 0))}\n"
            f"Latest user message: {user_message}"
        ),
    )


def _build_chat_agent(session_context: dict, required_tools: set[str] | None = None) -> ReActAgent:
    async def capture_passenger_details(
        message: Annotated[str, "The user's latest message that may contain passenger details for the booking form."],
    ) -> dict[str, str]:
        """Extract passenger details into structured booking fields."""

        passenger_draft = await _structured_completion(
            PassengerDraft,
            system_prompt=(
                "You extract passenger details for an airline booking form. "
                "Only return fields explicitly provided or clearly intended as form values. "
                "Leave missing fields null and do not invent data. "
                "When the user gives a full traveler name such as 'Name is Alex Gamma', map the first token to firstName and the remaining name tokens to lastName. "
                "When the user provides labeled values like email address, phone number, passport number, or date of birth, map them into the matching form fields."
            ),
            user_prompt=(
                "Extract structured passenger details from the following user message.\n\n"
                f"User message: {message}"
            ),
        )
        return passenger_draft.model_dump(exclude_none=True)

    def payment_guidance() -> str:
        """Return the current payment and booking confirmation rules for this session."""

        return _payment_status_summary(session_context)

    async def human_agent_tool() -> dict[str, Any]:
        """Check whether this booking qualifies for a human specialist and return the handoff payload."""

        tool_result = await resolve_human_agent_request(session_context)
        return tool_result.model_dump(exclude_none=True)

    async def faq_lookup(
        question: Annotated[str, "A traveler support question about policies, baggage, check-in, cancellation, seats, or fare rules."],
    ) -> str:
        """Answer support questions using the FAQ document only."""

        return await _text_completion(
            system_prompt=(
                "You answer traveler support questions using only the supplied FAQ document. "
                "If the FAQ does not cover the answer, say that it is not covered in the FAQ."
            ),
            user_prompt=(
                f"FAQ document:\n{_faq_text()}\n\n"
                f"Traveler question: {question}\n\n"
                "Answer directly from the FAQ."
            ),
        )

    tools_by_name = {
        "capture_passenger_details": FunctionTool.from_defaults(
            async_fn=capture_passenger_details,
            name="capture_passenger_details",
            description=(
                "Use this whenever the traveler provides passenger details or asks to fill or update the passenger form. "
                "It returns structured fields such as firstName, lastName, email, phone, dob, and passport."
            ),
        ),
        "payment_guidance": FunctionTool.from_defaults(
            fn=payment_guidance,
            name="payment_guidance",
            description=(
                "Use this for any payment, booking confirmation, booking completion, or confirmation-email question."
            ),
        ),
        "human_agent_tool": FunctionTool.from_defaults(
            async_fn=human_agent_tool,
            name="human_agent_tool",
            description=(
                "Use this when the traveler asks to speak with a human agent, specialist, representative, or real person. "
                "If it returns eligible=false, continue helping in chat yourself instead of exposing the internal fallback instruction."
            ),
        ),
        "faq_lookup": FunctionTool.from_defaults(
            async_fn=faq_lookup,
            name="faq_lookup",
            description=(
                "Use this for customer support or policy questions such as baggage, cancellations, check-in, seats, meals, or fare rules."
            ),
        ),
    }

    selected_tool_names = set(required_tools or tools_by_name.keys())
    selected_tool_names.add("human_agent_tool")
    tools = [
        tools_by_name[tool_name]
        for tool_name in ("capture_passenger_details", "payment_guidance", "human_agent_tool", "faq_lookup")
        if tool_name in selected_tool_names
    ]

    agent_system_prompt = SYSTEM_PROMPT
    if required_tools:
        ordered_tool_names = ", ".join(sorted(required_tools))
        agent_system_prompt += (
            f"\nFor this turn, you must call these tools before answering when they are available: {ordered_tool_names}."
        )

    return ReActAgent(
        tools=tools,
        llm=_get_llm(),
        system_prompt=agent_system_prompt,
        streaming=False,
        verbose=False,
    )


def _extract_passenger_tool_output(tool_calls: list[Any]) -> dict[str, str] | None:
    merged_draft: dict[str, str] | None = None
    for tool_call in tool_calls or []:
        if getattr(tool_call, "tool_name", "") != "capture_passenger_details":
            continue

        tool_output = getattr(tool_call, "tool_output", None)
        raw_output = getattr(tool_output, "raw_output", None)
        if isinstance(raw_output, PassengerDraft):
            candidate = raw_output.model_dump(exclude_none=True)
        elif isinstance(raw_output, dict):
            candidate = {key: value for key, value in raw_output.items() if value}
        else:
            candidate = {}

        if candidate:
            merged_draft = merge_passenger_draft(merged_draft, candidate)

    return merged_draft


def _extract_human_agent_tool_output(tool_calls: list[Any]) -> dict[str, Any] | None:
    for tool_call in tool_calls or []:
        if getattr(tool_call, "tool_name", "") != "human_agent_tool":
            continue

        tool_output = getattr(tool_call, "tool_output", None)
        raw_output = getattr(tool_output, "raw_output", None)
        if isinstance(raw_output, HumanAgentToolResult):
            return raw_output.model_dump(exclude_none=True)
        if isinstance(raw_output, dict):
            return raw_output

    return None


async def generate_proactive_message(intervention_context: dict) -> str:
    context_prompt = f"""The customer is currently on the '{intervention_context.get('step_cue', '')}' step.

Detected concerns: {', '.join(intervention_context.get('concerns', ['general']))}
Recommended tone: {intervention_context.get('tone', 'friendly_subtle')}
Approach: {intervention_context.get('approach', 'Offer general help')}

Flight context: {json.dumps(intervention_context.get('flight_context')) if intervention_context.get('flight_context') else 'Not yet selected'}
Search context: {json.dumps(intervention_context.get('search_context')) if intervention_context.get('search_context') else 'Not yet searched'}
Has started passenger form: {intervention_context.get('passenger_started', False)}

Generate a single proactive chat message (1-2 sentences) appropriate for this situation.
If you mention any amount, use INR.
If you mention price lock, describe it only as a 4-hour hold of the current fare and do not mention any fee or charge unless it is explicitly provided.
Do not use generic greetings. Be specific to their situation."""

    return await _text_completion(SYSTEM_PROMPT, context_prompt)


async def chat_response(
    user_message: str,
    chat_history: list[dict],
    session_context: dict,
    intervention_context: dict | None = None,
) -> ChatTurnResult:
    tool_plan = await _plan_chat_tools(user_message, session_context)
    required_tools = {
        tool_name
        for tool_name, should_use in {
            "capture_passenger_details": tool_plan.capture_passenger_details,
            "payment_guidance": tool_plan.payment_guidance,
            "human_agent_tool": tool_plan.human_agent_tool,
            "faq_lookup": tool_plan.faq_lookup,
        }.items()
        if should_use
    }

    agent = _build_chat_agent(session_context, required_tools or None)

    context_parts = [
        "Booking session snapshot:",
        _build_session_snapshot(session_context),
        "",
        "Recent conversation:",
        _format_history(chat_history, user_message),
        "",
    ]
    if intervention_context:
        context_parts.extend(
            [
                "Intervention context:",
                json.dumps(intervention_context, ensure_ascii=True),
                "",
            ]
        )
    context_parts.extend(
        [
            "Latest user message:",
            user_message,
            "",
            f"Tool plan: {tool_plan.model_dump_json()}",
            "",
            "Help the traveler using tools when appropriate.",
        ]
    )

    agent_input = "\n".join(context_parts)
    response = await agent.run(agent_input)
    response_text = str(response).strip()
    passenger_draft = _extract_passenger_tool_output(getattr(response, "tool_calls", []))
    human_handoff = _extract_human_agent_tool_output(getattr(response, "tool_calls", []))

    if human_handoff and human_handoff.get("eligible"):
        response_text = str(human_handoff.get("assistant_message", response_text)).strip()
    elif response_text.strip().lower() == HUMAN_AGENT_TOOL_FALLBACK.lower():
        response_text = "I'm here to help with your booking in chat. Let me know if you want help with payment, fare rules, traveler details, or booking status."

    if passenger_draft:
        lowered = response_text.lower()
        if "passenger form" not in lowered and "review" not in lowered:
            response_text = (response_text + " " + _passenger_review_note(passenger_draft)).strip()

    response_text = _apply_confirmation_guardrails(response_text, session_context)

    return ChatTurnResult(
        response=response_text,
        passenger_draft=passenger_draft,
        review_required=bool(passenger_draft),
        human_handoff=human_handoff if human_handoff and human_handoff.get("eligible") else None,
    )


async def generate_recovery_message(session_data: dict, channel: str = "email") -> dict:
    search = _load_json_field(session_data.get("search_params"))
    flight = _load_json_field(session_data.get("selected_flight"))
    step = session_data.get("current_step", "search")

    recovery_message = await _structured_completion(
        RecoveryMessage,
        system_prompt=(
            "You write concise airline recovery outreach. Return structured recovery copy only and keep it mobile-friendly. "
            f"{PRICE_LOCK_POLICY}"
        ),
        user_prompt=(
            f"Channel: {channel}\n"
            f"Customer abandoned at step: {step}\n"
            f"Search details: {json.dumps(search) if search else 'Started but incomplete'}\n"
            f"Selected flight: {json.dumps(flight) if flight else 'Not yet selected'}\n"
            f"Selected fare display: {_format_inr(flight.get('price')) if flight else 'Not yet selected'}\n"
            "\n"
            "Write a recovery subject, body, and CTA. Mention saved progress, 4-hour price lock, and 24-hour cancellation when relevant. "
            "Do not imply or invent any separate fee for price lock unless one is explicitly provided."
        ),
    )
    return recovery_message.model_dump()


async def generate_human_save_desk_intro(session_data: dict) -> str:
    trip = _get_session_trip_context(session_data)

    prompt = f"""Generate a concise booking-assistance message for a customer who is on the payment step.

Trip route: {trip['route']}
Traveler count: {trip['passenger_count']}
Per traveler fare: {_format_inr(trip['per_traveler_price'])}
Estimated total trip value: {_format_inr(trip['trip_value'])}
Current step: {session_data.get('current_step', 'payment')}

Requirements:
- This is a large international booking, so sound confident and premium.
- Offer immediate help with payment, fare rules, traveler details, or booking confirmation concerns.
- Mention that a human group travel specialist can be brought in if needed.
- Keep it to 2 sentences max.
- Any amount references must be in INR."""

    return await _text_completion(SYSTEM_PROMPT, prompt)


async def generate_human_handoff_summary(session_data: dict) -> dict:
    trip = _get_session_trip_context(session_data)
    passenger = _load_json_field(session_data.get("passenger_details"))

    handoff = await _structured_completion(
        HumanHandoff,
        system_prompt="You prepare concise airline support handoffs for human specialists.",
        user_prompt=(
            f"Trip route: {trip['route']}\n"
            f"Traveler count: {trip['passenger_count']}\n"
            f"Per traveler fare: {_format_inr(trip['per_traveler_price'])}\n"
            f"Estimated total trip value: {_format_inr(trip['trip_value'])}\n"
            f"Current step: {session_data.get('current_step', 'payment')}\n"
            f"Lead traveler: {passenger.get('firstName', '')} {passenger.get('lastName', '')}\n"
            f"Email: {session_data.get('email') or passenger.get('email') or 'unknown'}\n"
            f"Phone: {session_data.get('phone') or passenger.get('phone') or 'unknown'}\n\n"
            "Return a customer-facing handoff message, an internal agent brief, and a priority of high or urgent."
        ),
    )
    return handoff.model_dump()