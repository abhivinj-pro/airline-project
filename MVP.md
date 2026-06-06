# AirWave AI Booking Recovery — MVP

An AI-powered system that detects booking abandonment in real-time and intervenes to recover lost conversions for airline websites.

## Problem

Thousands of users start booking flights online but abandon before payment — routing to offline agents. This leads to lost direct revenue, high commissions, and missed ancillary cross-sell.

## Solution: 3-Pillar AI Recovery System

### 1. Behavioral Abandonment Detection
A client-side tracker monitors 10+ behavioral signals in real-time:

| Signal | Weight | What it detects |
|--------|--------|-----------------|
| `idle_60s` | 0.35 | User distracted or indecisive |
| `back_button` | 0.25 | Reconsidering their choice |
| `idle_30s` | 0.20 | Hesitation |
| `mouse_leave` | 0.15 | About to leave the site |
| `tab_switch` | 0.12 | Comparison shopping |
| `form_delete` | 0.10 | Form fatigue |
| `scroll_to_top` | 0.08 | Reconsidering |
| `rapid_clicks` | 0.06 | UI frustration |
| `price_hover` | 0.05 | Price sensitivity |

Signals are weighted and multiplied by booking step (later steps = higher intent, higher recovery priority). The composite score triggers different intervention levels.

Assumption: The current signal weights, step multipliers, and intervention thresholds are heuristic MVP defaults. In a real deployment, we would train a supervised model on historical funnel data to predict abandonment probability, then calibrate both feature importance and trigger cutoffs using offline validation and A/B testing.

### 2. Proactive AI Chat Concierge
When risk score crosses thresholds, an Azure OpenAI-powered chat assistant proactively engages:

- **Score 0.45+** — Friendly nudge: "Need help finding the right flight?"
- **Score 0.65+** — Active assistance: "I noticed you're on the passenger details step — can I help?"
- **Score 0.80+** — Urgent save: "Your booking is saved! Want me to help you complete it?"

The AI is context-aware — it knows:
- Which flight they selected and the route/price
- What step they're on in the funnel
- Which signals triggered (price sensitivity vs. form fatigue vs. comparison shopping)
- And it adapts its tone and strategy accordingly

### 3. Smart Recovery Campaigns
For users who already left, the system generates personalized recovery messages:
- **Email** — "Your Dubai flight at 32,000INR is still available — 3 seats left"
- **SMS** — Short, urgent messages for high-risk abandoners
- Recovery previews include a deep link back to the user's saved session
- AI generates each message based on the specific customer journey
- Users can jump in to the session right with all their details filled in. 

## Additional AI-Powered Retention Solutions

These ideas are intentionally AI-led. They are not UI tricks, generic discounts, or random upsells.

### 1. Abandonment Reason Classification Engine
Instead of only predicting that a user may leave, an AI model can classify why they are likely to leave: price concern, schedule mismatch, policy confusion, trust concern, payment friction, or decision delay.

Why it helps:
- Retention is much stronger when the intervention matches the real reason for hesitation
- The system can route each user into the right recovery path instead of using one generic playbook

What the AI does:
- Combines clickstream behavior, search context, step reached, and chat text into a probable abandonment-reason label
- Chooses the next best intervention based on cause, not just risk score

### 2. AI Follow-Up Timing and Channel Optimizer
Not every user should get the same recovery message at the same time on the same channel. AI can decide when and where recovery has the highest probability of success.

Why it helps:
- Poorly timed outreach gets ignored and can reduce trust
- A smaller number of well-timed interventions usually outperforms blanket reminders

What the AI does:
- Predicts the best send time, cadence, and channel for each abandoner using prior response and conversion behavior
- Balances urgency against fatigue so the system does not over-contact customers

### 3. AI-Assisted Human Save Desk
When the model predicts a very high-value booking is at risk, AI can prepare a human support agent to intervene effectively instead of handing off raw session data.

Why it helps:
- Some bookings are too complex or high-value for pure automation
- AI increases human recovery efficiency by removing investigation time and improving intervention quality

What the AI does:
- Summarizes the session, likely intent, core objection, best talking points, and recommended recovery action
- Prioritizes which at-risk sessions deserve live outreach based on expected recoverable revenue


## Which of these are strongest for this problem?

If the goal is to maximize booking retention beyond the current MVP, the highest-value additions are usually:

1. **Abandonment reason classification** because it makes every other intervention more relevant.
2. **AI itinerary re-composer** because many users abandon the current option, not the trip itself.
3. **AI timing and channel optimizer** because recovery performance depends heavily on when and how the outreach happens.

## MVP Assumptions and Production Approach

1. **Risk scoring is heuristic today.**
	Assumption: Signal weights, step multipliers, and thresholds in the MVP are manually chosen heuristics.
	Real-world approach: Train a calibrated supervised model on historical session-level event data to predict abandonment probability, then tune intervention thresholds using backtesting and controlled experiments.

2. **A small browser-event set is enough to infer intent.**
	Assumption: Signals such as idle time, tab switches, mouse leave, rapid clicks, and form deletion are sufficient proxies for abandonment risk.
	Real-world approach: Build a richer event taxonomy with time-series features, device/channel context, payment errors, fare changes, and previous customer behavior, then evaluate which features are actually predictive.

3. **Flight inventory and ancillary pricing are static demo data.**
	Assumption: Search results and add-ons come from hardcoded sample objects in the frontend.
	Real-world approach: Integrate with the airline's booking engine or NDC/PSS APIs for live availability, fare rules, ancillary catalog, and price revalidation before payment.

4. **The session is treated as the customer identity.**
	Assumption: A single browser session is enough to personalize chat and recovery, and the contact details entered later in the flow belong to the same recoverable customer.
	Real-world approach: Use server-generated session tokens, authenticated identity stitching, consent-aware CRM/CDP joins, and cross-device matching where policy allows.

5. **The AI can mention actions that are not yet backed by APIs.**
	Assumption: The assistant references capabilities such as saved progress, price lock, promo support, and free cancellation even though those promises are not enforced through downstream systems in the MVP.
	Real-world approach: Put the model behind a policy and tool-calling layer so it can only promise actions that are available through verified booking, servicing, loyalty, and offer-management APIs.

6. **High risk is treated as abandonment.**
	Assumption: The MVP flags sessions based mainly on score thresholds, and the recovery query uses a simplified rule rather than a full inactivity- and state-based abandonment definition.
	Real-world approach: Define abandonment with explicit business rules that combine inactivity windows, step reached, payment failures, fare expiry, agent-booking attribution, and suppression rules to avoid premature outreach.

7. **Recovery orchestration is simulated.**
	Assumption: Triggering recovery currently generates copy and logs the campaign in SQLite instead of sending real email or SMS.
	Real-world approach: Integrate with ESP/SMS providers, queue outbound jobs, track delivery/open/click/conversion events, honor unsubscribe preferences, and measure attributed recovery revenue.

8. **A 4-hour price lock can actually be honored.**
	Assumption: For targeted high-intent, price-sensitive users, the airline can hold the quoted fare for 4 hours after abandonment without breaking fare rules, inventory controls, or downstream pricing logic.
	Real-world approach: Implement a real offer-hold or fare-lock capability with the airline's pricing and inventory systems, including eligibility rules, expiry handling, exposure limits, fee/refund policy, and revalidation before ticketing.

9. **Checkout completion is simulated.**
	Assumption: Completing payment marks the session as converted and returns a generated booking reference, but there is no real payment authorization, PNR creation, or ticketing flow.
	Real-world approach: Integrate with the payment gateway and booking engine for authorization, fraud checks, 3DS where required, reservation creation, ticket issuance, and reconciliation.

10. **PII handling is simplified for the MVP.**
	Assumption: Passenger details, email, and phone are stored in the local application database without production-grade consent, retention, encryption, or access-control workflows.
	Real-world approach: Minimize stored PII, encrypt sensitive fields, tokenize where possible, capture channel consent explicitly, define retention policies, and enforce auditability and least-privilege access.

## Estimated Revenue Impact (Illustrative)

The following is a rough business estimate using simple assumptions, intended only to show relative magnitude.

### Assumptions used for estimation

- Monthly booking sessions started: 100,000
- Booking abandonment rate: 50% -> 50,000 abandoned sessions
- Average booking value: INR 12,000
- Gross booking value is used as the revenue proxy for MVP estimation
- Recovery campaigns only target contactable, high-intent abandoners
- Price lock is offered only to a smaller subset of price-sensitive, high-intent users

### 1. Estimated impact of a 4-hour price lock

Assume:

- 20% of abandoners are strong candidates for a 4-hour fare hold -> 10,000 users/month
- 8% of those users accept or meaningfully respond to the price-lock offer -> 800 users
- Baseline conversion for this high-intent subgroup without a price lock is 20% -> 160 bookings
- The price lock improves final conversion by 12 percentage points -> treated conversion becomes 32% -> 256 bookings
- Incremental recovered bookings from the price lock = 800 x 12% = 96
- Average booking value = INR 12,000
- For downside risk, assume 15% of bookings that would have happened anyway would have faced an average fare increase of INR 1,000 during the 4-hour hold window

Expected-value calculation:

$$
E(\text{RevenueChange}) = E(\text{Revenue Increase from recovered bookings}) - E(\text{Loss from keeping price locked})
$$

1. Expected revenue increase from recovered bookings:

$$
96 \times 12{,}000 = \text{INR }1{,}152{,}000
$$

2. Expected loss from keeping the fare locked:

- Bookings that would likely have converted anyway without the lock = 160
- Expected loss per such booking from foregone fare movement = 15% x INR 1,000 = INR 150

$$
160 \times 150 = \text{INR }24{,}000
$$

3. Net expected monthly revenue change:

$$
E(\text{RevenueChange}) = 1{,}152{,}000 - 24{,}000 = \text{INR }1{,}128{,}000
$$

Interpretation: under these assumptions, the 4-hour price lock still has a strongly positive expected value. The upside from 96 incremental recovered bookings materially outweighs the expected revenue foregone from honoring the locked fare for users who would likely have booked anyway.

### 2. Estimated impact of booking-recovery campaigns

Assume:

- 30% of abandoned sessions are both high-intent and contactable -> 15,000 users/month
- Email/SMS/chat recovery journeys recover 3% of those abandoned bookings -> 450 recovered bookings

Estimated monthly revenue impact:

- Incremental recovered bookings from campaigns: 450
- Estimated gross booking value recovered: 450 x INR 12,000 = INR 5,400,000 per month

### Comparison

- 4-hour price lock net expected revenue change: about INR 1.13M/month
- Booking recovery campaigns: about INR 5.40M/month
- Recovery campaigns generate about 4.8x more revenue in this estimate

Why the gap is reasonable:

- Price lock is relevant only for a subset of users whose main barrier is fare volatility
- Recovery campaigns address a much larger pool of abandonment causes: distraction, form fatigue, comparison shopping, payment hesitation, and delayed decision-making
- Price lock is best treated as one tactic inside the larger recovery system, not as the primary revenue lever

If you want a concise takeaway for a presentation: a 4-hour price lock is a useful conversion aid, but the larger revenue upside comes from recovering abandoned bookings at scale through proactive chat and post-abandonment outreach.