/**
 * AirWave Airlines — Booking Flow Application
 *
 * Simulates a multi-step airline booking process:
 * 1. Search → 2. Results → 3. Passenger Details → 4. Ancillaries → 5. Payment
 *
 * Integrates with AbandonmentTracker and ChatWidget for AI-powered recovery.
 */

// ─── Sample Flight Data ──────────────────────────────────────────

const SAMPLE_FLIGHTS = [
    {
        id: 'SW101',
        flight_no: 'SW 101',
        airline: 'AirWave',
        from: 'Bengaluru (BLR)',
        to: 'Dubai (DXB)',
        depart: '06:45',
        arrive: '09:10',
        duration: '4h 55m',
        stops: 'Non-stop',
        price: 32999,
        class: 'Economy',
        tags: ['Lowest fare', 'Early departure'],
    },
    {
        id: 'SW205',
        flight_no: 'SW 205',
        airline: 'AirWave',
        from: 'Bengaluru (BLR)',
        to: 'Dubai (DXB)',
        depart: '11:20',
        arrive: '13:55',
        duration: '5h 05m',
        stops: 'Non-stop',
        price: 36499,
        class: 'Economy',
        tags: ['Popular', 'Prime timing'],
    },
    {
        id: 'SW312',
        flight_no: 'SW 312',
        airline: 'AirWave',
        from: 'Bengaluru (BLR)',
        to: 'Dubai (DXB)',
        depart: '18:40',
        arrive: '21:15',
        duration: '5h 05m',
        stops: 'Non-stop',
        price: 34199,
        class: 'Economy',
        tags: ['Best value', 'Evening flight'],
    },
    {
        id: 'SW418',
        flight_no: 'SW 418',
        airline: 'AirWave',
        from: 'Bengaluru (BLR)',
        to: 'Dubai (DXB)',
        depart: '20:55',
        arrive: '00:40+1',
        duration: '6h 45m',
        stops: '1 stop (BOM)',
        price: 28499,
        class: 'Economy',
        tags: ['Budget smart'],
    },
];

const ANCILLARIES = [
    { id: 'baggage', icon: '🧳', name: 'Extra Baggage', desc: '+23kg checked bag', price: 3800 },
    { id: 'seat', icon: '💺', name: 'Seat Selection', desc: 'Choose your preferred seat', price: 2100 },
    { id: 'meal', icon: '🍽️', name: 'In-flight Meal', desc: 'Premium meal service', price: 1500 },
    { id: 'lounge', icon: '✨', name: 'Lounge Access', desc: 'Pre-departure lounge', price: 4600 },
    { id: 'insurance', icon: '🛡️', name: 'Travel Insurance', desc: 'Full trip protection', price: 2700 },
    { id: 'wifi', icon: '📶', name: 'Wi-Fi Pass', desc: 'Full-flight internet', price: 900 },
];

const inrFormatter = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
});

const HUMAN_SAVE_DESK_RESPONSE_WINDOW_MS = 8000;
const PRICE_LOCK_DELAY_MS = 10000;

const ROUTE_PRICE_ADJUSTMENTS = {
    'Bengaluru (BLR)|Dubai (DXB)': 0,
    'Bengaluru (BLR)|Singapore (SIN)': 1800,
    'Bengaluru (BLR)|Bangkok (BKK)': 2400,
    'Bengaluru (BLR)|Goa (GOX)': -11400,
    'Bengaluru (BLR)|London (LHR)': 21500,
    'Mumbai (BOM)|Dubai (DXB)': -1600,
    'Mumbai (BOM)|Singapore (SIN)': 900,
    'Mumbai (BOM)|Bangkok (BKK)': 1500,
    'Mumbai (BOM)|Goa (GOX)': -12500,
    'Mumbai (BOM)|London (LHR)': 19800,
    'Delhi (DEL)|Dubai (DXB)': -900,
    'Delhi (DEL)|Singapore (SIN)': 2200,
    'Delhi (DEL)|Bangkok (BKK)': 1900,
    'Delhi (DEL)|Goa (GOX)': -12000,
    'Delhi (DEL)|London (LHR)': 18600,
    'Hyderabad (HYD)|Dubai (DXB)': 700,
    'Hyderabad (HYD)|Singapore (SIN)': 1700,
    'Hyderabad (HYD)|Bangkok (BKK)': 2100,
    'Hyderabad (HYD)|Goa (GOX)': -11700,
    'Hyderabad (HYD)|London (LHR)': 20800,
    'Chennai (MAA)|Dubai (DXB)': 500,
    'Chennai (MAA)|Singapore (SIN)': -1200,
    'Chennai (MAA)|Bangkok (BKK)': 600,
    'Chennai (MAA)|Goa (GOX)': -11000,
    'Chennai (MAA)|London (LHR)': 22300,
};

function formatPrice(amount) {
    return inrFormatter.format(amount);
}

function getRouteAdjustment(from, to) {
    return ROUTE_PRICE_ADJUSTMENTS[`${from}|${to}`] ?? 0;
}

function buildFlightsForSearch(search) {
    const routeAdjustment = getRouteAdjustment(search.from, search.to);

    return SAMPLE_FLIGHTS.map((flight, index) => ({
        ...flight,
        id: `${flight.id}-${search.from}-${search.to}-${index}`,
        from: search.from,
        to: search.to,
        price: Math.max(4999, flight.price + routeAdjustment),
    }));
}

// ─── App State ───────────────────────────────────────────────────

let sessionId = null;
let tracker = null;
let chatWidget = null;
let currentStep = 'search';
let selectedFlight = null;
let selectedAncillaries = new Set();
let passengerData = {};
let pendingPassengerDraft = null;
let lastPassengerDraftNoticeKey = null;
let autoFilledPassengerDraftFields = new Set();
let priceLockTimer = null;
let latestSearchParams = null;
let humanSaveDeskTimer = null;
let humanSaveDeskState = {
    prompted: false,
    active: false,
    responded: false,
    escalated: false,
};
let bookingCompleted = false;
let abandonmentFinalized = false;

// ─── Initialization ──────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    // Create session
    sessionId = 'sess_' + Math.random().toString(36).substr(2, 12);
    try {
        await fetch('/api/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
        });
    } catch (e) {
        console.warn('Session creation failed, continuing offline');
    }

    // Initialize tracker and chat
    tracker = new AbandonmentTracker(sessionId);
    chatWidget = new ChatWidget(sessionId);
    chatWidget.onUserMessage = handleHumanSaveDeskUserResponse;
    chatWidget.onAssistantPayload = handleAssistantPayload;

    // Wire up tracker → chat interventions
    tracker.onIntervention = (intervention) => {
        if (intervention.message) {
            chatWidget.showProactiveMessage(intervention.message);
        }
    };

    // Set initial step
    showStep('search');

    // Set default date to tomorrow
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 7);
    const dateInput = document.getElementById('travel-date');
    if (dateInput) {
        dateInput.value = tomorrow.toISOString().split('T')[0];
    }
});

// ─── Step Navigation ─────────────────────────────────────────────

function showStep(step) {
    currentStep = step;

    resetPriceLockNotice();

    if (step !== 'payment') {
        stopHumanSaveDeskTimer();
        humanSaveDeskState.active = false;
    }

    // Update tracker
    if (tracker) tracker.setStep(step);

    // Update stepper UI
    const steps = ['search', 'results', 'passenger', 'ancillaries', 'payment'];
    const stepIndex = steps.indexOf(step);

    document.querySelectorAll('.step').forEach((el, i) => {
        el.classList.remove('active', 'completed');
        if (i === stepIndex) el.classList.add('active');
        else if (i < stepIndex) el.classList.add('completed');
    });

    // Show/hide sections
    document.querySelectorAll('.booking-step').forEach(el => {
        el.style.display = 'none';
    });
    const target = document.getElementById(`step-${step}`);
    if (target) target.style.display = 'block';

    if (step === 'passenger') {
        renderPassengerDraftReview();
    }

    if (step === 'passenger' || step === 'payment') {
        startPriceLockTimer();
    }

    // Update session on server
    let sessionUpdatePromise = Promise.resolve();
    if (sessionId) {
        sessionUpdatePromise = fetch('/api/session', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, current_step: step }),
        }).catch(() => {});
    }

    if (step === 'payment') {
        sessionUpdatePromise.finally(() => {
            triggerHumanSaveDeskIfEligible();
        });
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function handleAssistantPayload(payload) {
    if (!payload || !payload.passenger_draft) {
        return;
    }

    pendingPassengerDraft = payload.passenger_draft;
    autofillPassengerDraft();
    renderPassengerDraftReview();

    lastPassengerDraftNoticeKey = JSON.stringify(payload.passenger_draft);

    if (currentStep === 'passenger') {
        const review = document.getElementById('passenger-draft-review');
        if (review) {
            review.style.display = 'block';
            review.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
}

function autofillPassengerDraft() {
    if (!pendingPassengerDraft) {
        return;
    }

    const fieldMap = getPassengerFieldMap();
    Object.entries(pendingPassengerDraft).forEach(([key, value]) => {
        const field = fieldMap[key];
        if (!field || !value) {
            return;
        }

        const currentValue = field.value.trim();
        if (!currentValue) {
            field.value = value;
            autoFilledPassengerDraftFields.add(key);
        }
    });
}

function getPassengerFieldMap() {
    return {
        firstName: document.getElementById('first-name'),
        lastName: document.getElementById('last-name'),
        email: document.getElementById('pax-email'),
        phone: document.getElementById('pax-phone'),
        dob: document.getElementById('pax-dob'),
        passport: document.getElementById('pax-passport'),
    };
}

function getPassengerDraftLabel(key) {
    const labels = {
        firstName: 'First name',
        lastName: 'Last name',
        email: 'Email',
        phone: 'Phone',
        dob: 'Date of birth',
        passport: 'Passport number',
    };
    return labels[key] || key;
}

function renderPassengerDraftReview() {
    const review = document.getElementById('passenger-draft-review');
    const fields = document.getElementById('passenger-draft-fields');
    if (!review || !fields) {
        return;
    }

    if (!pendingPassengerDraft || Object.keys(pendingPassengerDraft).length === 0) {
        review.style.display = 'none';
        fields.innerHTML = '';
        return;
    }

    const fieldMap = getPassengerFieldMap();
    const conflictingEntries = Object.entries(pendingPassengerDraft)
        .filter(([key, value]) => {
            if (!value) {
                return false;
            }

            const currentValue = fieldMap[key]?.value?.trim() || '';
            return currentValue && currentValue !== value;
        });

    const items = conflictingEntries
        .map(([key, value]) => {
            const currentValue = fieldMap[key]?.value?.trim() || '';
            return `
                <div class="passenger-draft-item">
                    <span class="draft-label">${getPassengerDraftLabel(key)}</span>
                    <strong>Chat: ${value}</strong>
                    <small>Form currently shows: ${currentValue}</small>
                </div>
            `;
        })
        .join('');

    fields.innerHTML = items;
    const copy = review.querySelector('.passenger-draft-copy p');
    if (copy) {
        copy.textContent = items
            ? 'Some fields already had values, so chat suggestions are waiting here for your confirmation before replacing them.'
            : 'Detected details were added into empty fields in the form. Review and edit anything before you continue.';
    }
    review.style.display = 'block';
    const actions = review.querySelector('.passenger-draft-actions');
    if (actions) {
        actions.style.display = items ? 'flex' : 'none';
    }
}

function applyPassengerDraft() {
    if (!pendingPassengerDraft) {
        return;
    }

    const fieldMap = getPassengerFieldMap();
    Object.entries(pendingPassengerDraft).forEach(([key, value]) => {
        if (fieldMap[key] && value) {
            fieldMap[key].value = value;
        }
    });

    pendingPassengerDraft = null;
    lastPassengerDraftNoticeKey = null;
    autoFilledPassengerDraftFields.clear();
    renderPassengerDraftReview();

    fetch('/api/session', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, passenger_draft: {} }),
    }).catch(() => {});
}

function dismissPassengerDraft() {
    const fieldMap = getPassengerFieldMap();
    Object.entries(pendingPassengerDraft || {}).forEach(([key, value]) => {
        const field = fieldMap[key];
        if (!field || !value) {
            return;
        }

        if (autoFilledPassengerDraftFields.has(key) && field.value.trim() === value) {
            field.value = '';
        }
    });

    pendingPassengerDraft = null;
    lastPassengerDraftNoticeKey = null;
    autoFilledPassengerDraftFields.clear();
    renderPassengerDraftReview();

    fetch('/api/session', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, passenger_draft: {} }),
    }).catch(() => {});
}

function stopHumanSaveDeskTimer() {
    if (humanSaveDeskTimer) {
        clearTimeout(humanSaveDeskTimer);
        humanSaveDeskTimer = null;
    }
}

function resetHumanSaveDeskState() {
    stopHumanSaveDeskTimer();
    humanSaveDeskState = {
        prompted: false,
        active: false,
        responded: false,
        escalated: false,
    };
}

function isHumanSaveDeskIntent(message) {
    const normalized = message.trim().toLowerCase().replace(/\s+/g, ' ');
    if (!normalized) {
        return false;
    }

    const explicitHumanPhrases = [
        'human agent',
        'human specialist',
        'group travel specialist',
        'real person',
        'someone from support',
        'support agent',
        'representative',
    ];
    if (explicitHumanPhrases.some(phrase => normalized.includes(phrase))) {
        return true;
    }

    const handoffPhrases = [
        'connect me',
        'put me through',
        'transfer me',
        'speak to',
        'talk to',
        'chat with',
        'reach a human',
        'reach someone',
        'bring in',
    ];
    if (handoffPhrases.some(phrase => normalized.includes(phrase))) {
        return true;
    }

    return [
        'yes',
        'yes please',
        'yeah',
        'yep',
        'sure',
        'sure please',
        'ok',
        'okay',
        'please do',
        'do that',
        'that would help',
        'i do',
        'please connect me',
    ].includes(normalized);
}

function logHumanSaveDeskResponse(message, requestedHuman) {
    return fetch('/api/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            event_type: 'human_save_desk_user_responded',
            event_data: {
                step: currentStep,
                requested_human: requestedHuman,
                message,
            },
        }),
    }).catch(() => {});
}

async function handleHumanSaveDeskUserResponse(message) {
    if (!humanSaveDeskState.active || humanSaveDeskState.escalated) {
        return false;
    }

    const requestedHuman = isHumanSaveDeskIntent(message);
    humanSaveDeskState.responded = true;
    humanSaveDeskState.active = false;
    stopHumanSaveDeskTimer();
    await logHumanSaveDeskResponse(message, requestedHuman);
    return false;
}

async function triggerHumanSaveDeskIfEligible() {
    if (!sessionId || humanSaveDeskState.prompted || humanSaveDeskState.escalated) {
        return;
    }

    try {
        const response = await fetch('/api/human-save-desk/engage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
        });

        const data = await response.json();
        if (!data.eligible || !data.message || currentStep !== 'payment') {
            return;
        }

        humanSaveDeskState.prompted = true;
        humanSaveDeskState.active = true;
        humanSaveDeskState.responded = false;
        chatWidget.showProactiveMessage(data.message);

        stopHumanSaveDeskTimer();
        humanSaveDeskTimer = window.setTimeout(() => {
            escalateHumanSaveDesk();
        }, HUMAN_SAVE_DESK_RESPONSE_WINDOW_MS);
    } catch (err) {
        console.warn('Human save desk AI prompt failed', err);
    }
}

async function escalateHumanSaveDesk(force = false) {
    humanSaveDeskTimer = null;

    if (humanSaveDeskState.escalated || currentStep !== 'payment') {
        return false;
    }

    if (!force && (!humanSaveDeskState.active || humanSaveDeskState.responded)) {
        return false;
    }

    try {
        const response = await fetch('/api/human-save-desk/escalate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
        });

        const data = await response.json();
        if (!data.connected || !data.message) {
            return false;
        }

        humanSaveDeskState.active = false;
        humanSaveDeskState.responded = true;
        humanSaveDeskState.escalated = true;
        chatWidget.showProactiveMessage(data.message);
        chatWidget.open();
        return true;
    } catch (err) {
        console.warn('Human save desk escalation failed', err);
        return false;
    }
}

function getPassengerCount() {
    const rawPassengers = latestSearchParams?.passengers ?? 1;
    const count = Number.parseInt(rawPassengers, 10);
    return Number.isNaN(count) ? 1 : count;
}

function getPriceLockNotice(step = currentStep) {
    const noticeIdByStep = {
        passenger: 'passenger-price-lock',
        payment: 'payment-price-lock',
    };

    const noticeId = noticeIdByStep[step];
    return noticeId ? document.getElementById(noticeId) : null;
}

function resetPriceLockNotice() {
    if (priceLockTimer) {
        clearTimeout(priceLockTimer);
        priceLockTimer = null;
    }

    ['passenger', 'payment'].forEach((step) => {
        const notice = getPriceLockNotice(step);
        if (notice) {
            notice.style.display = 'none';
        }
    });
}

function startPriceLockTimer() {
    const step = currentStep;
    const notice = getPriceLockNotice(step);
    if (!notice) {
        return;
    }

    priceLockTimer = window.setTimeout(() => {
        if (currentStep === step) {
            notice.style.display = 'block';
        }
        priceLockTimer = null;
    }, PRICE_LOCK_DELAY_MS);
}

// ─── Search ──────────────────────────────────────────────────────

function searchFlights() {
    const from = document.getElementById('from-city').value;
    const to = document.getElementById('to-city').value;
    const date = document.getElementById('travel-date').value;
    const passengers = document.getElementById('passengers').value;

    if (!from || !to || !date) {
        alert('Please fill in all search fields');
        return;
    }

    const searchParams = { from, to, date, passengers };
    latestSearchParams = searchParams;

    resetHumanSaveDeskState();

    // Update session with search params
    fetch('/api/session', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, search_params: searchParams }),
    }).catch(() => {});

    // Render results
    renderFlightResults(searchParams);
    showStep('results');
}

function renderFlightResults(search) {
    const container = document.getElementById('flight-list');
    container.innerHTML = '';
    const routeFlights = buildFlightsForSearch(search);

    document.getElementById('route-display').textContent =
        `${search.from} → ${search.to} | ${search.date} | ${search.passengers} passenger(s)`;

    routeFlights.forEach(flight => {
        const card = document.createElement('div');
        card.className = 'flight-card';
        card.setAttribute('data-price', flight.price);
        card.onclick = () => selectFlight(flight, card);
        card.innerHTML = `
            <div>
                <div class="flight-time">${flight.depart}</div>
                <div class="flight-city">${flight.from}</div>
                <div class="flight-meta">
                    <span>${flight.flight_no}</span>
                </div>
            </div>
            <div class="flight-duration">
                <span>${flight.duration}</span>
            </div>
            <div>
                <div class="flight-time">${flight.arrive}</div>
                <div class="flight-city">${flight.to}</div>
                <div class="flight-meta">
                    <span class="tag">${flight.stops}</span>
                </div>
            </div>
            <div class="flight-price">
                <div class="amount">${formatPrice(flight.price)}</div>
                <div class="per">per person</div>
                <div class="flight-meta" style="justify-content: flex-end; margin-top:6px;">
                    ${flight.tags.map(t => `<span class="tag">${t}</span>`).join('')}
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function selectFlight(flight, card) {
    selectedFlight = flight;

    // Update UI
    document.querySelectorAll('.flight-card').forEach(el => el.classList.remove('selected'));
    card.classList.add('selected');

    // Enable continue button
    document.getElementById('continue-to-passenger').disabled = false;

    // Update session
    fetch('/api/session', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, selected_flight: flight }),
    }).catch(() => {});
}

function continueToPassenger() {
    if (!selectedFlight) {
        alert('Please select a flight first');
        return;
    }
    showStep('passenger');
}

// ─── Passenger Details ───────────────────────────────────────────

function continueToAncillaries() {
    const firstName = document.getElementById('first-name').value;
    const lastName = document.getElementById('last-name').value;
    const email = document.getElementById('pax-email').value;
    const phone = document.getElementById('pax-phone').value;
    const dob = document.getElementById('pax-dob').value;
    const passport = document.getElementById('pax-passport').value;

    if (!firstName || !lastName || !email) {
        alert('Please fill in required passenger details');
        return;
    }

    passengerData = { firstName, lastName, email, phone, dob, passport };
    pendingPassengerDraft = null;
    lastPassengerDraftNoticeKey = null;
    autoFilledPassengerDraftFields.clear();
    renderPassengerDraftReview();

    // Save email/phone for recovery + passenger details
    fetch('/api/session', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            passenger_details: passengerData,
            passenger_draft: {},
            email: email,
            phone: phone || null,
        }),
    }).catch(() => {});

    renderAncillaries();
    showStep('ancillaries');
}

// ─── Ancillaries ─────────────────────────────────────────────────

function renderAncillaries() {
    const grid = document.getElementById('ancillary-grid');
    grid.innerHTML = '';

    ANCILLARIES.forEach(anc => {
        const card = document.createElement('div');
        card.className = 'ancillary-card';
        card.onclick = () => toggleAncillary(anc.id, card);
        card.innerHTML = `
            <div class="icon">${anc.icon}</div>
            <div class="name">${anc.name}</div>
            <div class="desc" style="font-size:12px;color:var(--text-light);margin-bottom:8px;">${anc.desc}</div>
            <div class="price">+${formatPrice(anc.price)}</div>
        `;
        grid.appendChild(card);
    });
}

function toggleAncillary(id, card) {
    if (selectedAncillaries.has(id)) {
        selectedAncillaries.delete(id);
        card.classList.remove('selected');
    } else {
        selectedAncillaries.add(id);
        card.classList.add('selected');
    }
}

function continueToPayment() {
    renderPaymentSummary();
    showStep('payment');
}

async function abandonSession(step = currentStep, reason = 'explicit_exit') {
    if (!sessionId || bookingCompleted || abandonmentFinalized) {
        return false;
    }

    try {
        const response = await fetch('/api/session/abandon', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                current_step: step,
                reason,
            }),
        });

        if (!response.ok) {
            return false;
        }

        abandonmentFinalized = true;
        return true;
    } catch (err) {
        console.warn('Failed to mark session as abandoned', err);
        return false;
    }
}

async function exitBooking(step = currentStep) {
    const marked = await abandonSession(step, 'exit_button');
    if (!marked) {
        alert('Unable to exit the session right now. Please try again.');
        return;
    }

    window.location.href = '/dashboard';
}

// ─── Payment ─────────────────────────────────────────────────────

function renderPaymentSummary() {
    const container = document.getElementById('payment-summary');
    const passengerCount = getPassengerCount();
    const baseFareTotal = selectedFlight.price * passengerCount;
    let total = baseFareTotal;

    let html = `
        <div class="summary-row">
            <span>${selectedFlight.flight_no}: ${selectedFlight.from} → ${selectedFlight.to} x ${passengerCount} traveler(s)</span>
            <span>${formatPrice(baseFareTotal)}</span>
        </div>
    `;

    html += `
        <div class="summary-row">
            <span>Fare per traveler</span>
            <span>${formatPrice(selectedFlight.price)}</span>
        </div>
    `;

    ANCILLARIES.filter(a => selectedAncillaries.has(a.id)).forEach(anc => {
        total += anc.price;
        html += `
            <div class="summary-row">
                <span>${anc.icon} ${anc.name}</span>
                <span>${formatPrice(anc.price)}</span>
            </div>
        `;
    });

    html += `
        <div class="summary-row total">
            <span>Total</span>
            <span>${formatPrice(total)}</span>
        </div>
    `;

    container.innerHTML = html;
}

async function completeBooking() {
    resetHumanSaveDeskState();
    bookingCompleted = true;

    const btn = document.getElementById('pay-btn');
    btn.disabled = true;
    btn.textContent = 'Processing...';

    try {
        const response = await fetch('/api/booking/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
        });

        const data = await response.json();

        // Show confirmation
        document.getElementById('step-payment').style.display = 'none';
        const conf = document.getElementById('step-confirmation');
        conf.style.display = 'block';
        document.getElementById('booking-ref').textContent = data.booking_ref;
        document.getElementById('conf-name').textContent =
            `${passengerData.firstName} ${passengerData.lastName}`;
        document.getElementById('conf-flight').textContent =
            `${selectedFlight.flight_no}: ${selectedFlight.from} → ${selectedFlight.to}`;

        // Update stepper
        document.querySelectorAll('.step').forEach(el => el.classList.add('completed'));
    } catch (err) {
        bookingCompleted = false;
        btn.disabled = false;
        btn.textContent = 'Pay & Confirm';
        alert('Payment failed. Please try again.');
    }
}
