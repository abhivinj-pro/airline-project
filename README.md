# AirWave AI Booking Recovery — MVP

An AI-powered system that detects booking abandonment in real-time and intervenes to recover lost conversions for airline websites.

The MVP business context, assumptions, and revenue estimates now live in [MVP.md](MVP.md).

## Tech Stack Rationale

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Backend Framework** | **FastAPI (Python)** | Async-native for WebSocket chat + REST APIs. Fast development speed. Excellent AI library ecosystem (OpenAI SDK). Pydantic for automatic validation. |
| **AI Engine** | **Azure OpenAI (GPT-4o)** | Enterprise-grade managed AI service with SLA guarantees. Strong reasoning for nuanced, empathetic booking conversations. Integrates with existing Azure infrastructure. Data residency and compliance controls built-in. |
| **Database** | **SQLite (aiosqlite)** | Zero infrastructure for MVP. Async driver for non-blocking I/O. Trivial to swap to PostgreSQL for production. |
| **Real-time Communication** | **WebSocket** | Low-latency bidirectional chat. Instant delivery of proactive AI messages. Graceful REST fallback included. |
| **Frontend** | **Vanilla HTML/CSS/JS** | No build step — instant demo-ability. Easy to embed as a widget in any existing airline website. No framework lock-in. |
| **Behavioral Tracking** | **Custom event system** | Lightweight (<3KB). Privacy-respecting (no PII in signals). Captures intent signals without heavy analytics SDKs. |

**Why not React/Next.js?** For an MVP, eliminating the build step makes the solution instantly deployable and demo-able. The chat widget is designed as a drop-in script that works on any site.

**Why Azure OpenAI?** Enterprise-grade with SLA, data residency controls, and seamless integration with Azure ecosystem (App Service, Key Vault, Monitor). GPT-4o provides strong reasoning for nuanced, empathetic booking conversations with fast response times.

## Project Structure

```
airline-booking-recovery/
├── backend/
│   ├── main.py              # FastAPI app — routes, WebSocket, API endpoints
│   ├── ai_engine.py         # Azure OpenAI-powered AI: proactive messages, chat, recovery copy
│   ├── abandonment.py       # Risk scoring engine with weighted signals
│   ├── recovery.py          # Recovery campaign orchestration
│   └── database.py          # SQLite async database layer
├── static/
│   ├── index.html           # 5-step airline booking flow
│   ├── dashboard.html       # Analytics & recovery management dashboard
│   ├── css/styles.css       # Complete UI styling
│   └── js/
│       ├── tracker.js       # Client-side behavioral signal tracker
│       ├── chat-widget.js   # AI chat widget with WebSocket + REST fallback
│       └── app.js           # Booking flow logic and state management
├── MVP.md                   # Problem statement, solution, assumptions, and revenue estimates
├── requirements.txt
└── README.md
```

## Setup & Run

```bash
# 1. Clone and enter the project
cd airline-booking-recovery

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure Azure OpenAI (uses Entra ID / DefaultAzureCredential)
cp .env.example .env
# Edit .env with your ENDPOINT_URL and DEPLOYMENT_NAME
# Ensure you are logged in via `az login` for Entra ID token auth

# 5. Run the server
python -m backend.main
```

Open http://localhost:8000 for the booking page and http://localhost:8000/dashboard for analytics.

## How It Works — User Flow

For the current MVP demo, the proactive timing is intentionally compressed so nudges appear within seconds instead of production-style waiting windows.

1. **User visits booking page** → Session created, tracker begins monitoring
2. **User searches & selects a flight** → Session data saved (route, price, flight)
3. **User slows down / switches tabs / hovers on price** → Signals accumulate, risk score rises
4. **Score hits 0.45** → AI chat bubble appears with a contextual nudge
5. **User engages with chat** → AI assistant helps resolve their concern (price, flexibility, form help)
6. **User completes booking** → Conversion tracked, ancillaries captured
7. **OR traveler explicitly exits on passenger or payment** → Session is saved as abandoned, appears in the dashboard, and can be recovered later if contact details were already captured

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/session` | Create a new booking session |
| PUT | `/api/session` | Update session data (step, flight, passenger) |
| POST | `/api/session/abandon` | Mark the current booking session as explicitly abandoned |
| POST | `/api/event` | Log a behavioral event |
| POST | `/api/risk` | Submit signals for risk assessment; returns score + AI intervention |
| POST | `/api/chat` | Send a chat message; get AI response (REST fallback) |
| POST | `/api/human-save-desk/engage` | Start AI-first assistance for eligible large international payment-step bookings |
| POST | `/api/human-save-desk/escalate` | Escalate eligible silent payment-step bookings to a simulated human specialist handoff |
| WS | `/ws/chat/{session_id}` | Real-time WebSocket chat |
| POST | `/api/recovery/trigger` | Trigger recovery campaigns for abandoned sessions |
| GET | `/api/recovery/preview/{id}` | Preview recovery messages for a session |
| GET | `/api/metrics` | Dashboard analytics data |
| POST | `/api/booking/complete` | Mark booking as completed |

## Key Design Decisions

1. **Proactive, not reactive**: The AI reaches out first based on behavioral signals — most chatbots wait for users to initiate, losing the window of opportunity.

2. **Context-aware tone**: The AI doesn't send generic "Can I help?" messages. It knows if the user is price-sensitive (offer value), confused (simplify), or impatient (be brief).

3. **Explicit abandonment for recovery**: Dashboard abandonments come from an explicit Exit during passenger or payment, so recovery campaigns only target real unfinished checkouts instead of inferred high-risk sessions.

4. **Graceful degradation**: If the Azure OpenAI API is unavailable, fallback messages are served. If WebSocket fails, REST API takes over. The booking flow works without the AI layer.

5. **Privacy-first tracking**: Behavioral signals are aggregated counts (e.g., "3 tab switches"), not raw events or PII. No cookies or fingerprinting beyond the session.
