# Q&A Questions for the Airline Booking Abandonment MVP

## Success & Data

1. **Success Definition & Targets**
   - What does "success" look like for this MVP? Is there a target metric — e.g., recover X% of abandoned sessions, or revenue targets based on recovery — and over what timeframe?
   - **Answer:** No specific metric. 50% leacving

2. **Analytics Instrumentation**
   - Do you have event-level clickstream/analytics data (e.g., Google Analytics) already being captured for the booking flow, or can I build my simple instrumentation for this MVP? I am currently looking at the following - Mouse leaving window, tab switches, idle time, Back button, scroll patterns, form behavior like mouse pointer close to price.
   - **Answer:** 

3. **Abandonment Rate & Funnel Dropoff**
   - What is the current abandonment rate, and at which specific steps in the funnel is the drop-off highest? (flight selection → traveller details → payment → confirmation)
   - **Answer:** 

4. **User Authentication Status**
   - What percentage of abandoners are authenticated (logged-in) vs. guest users? This changes what re-engagement channels (email, SMS, push, on-site) are viable.
   - **Answer:** 

5. **Agent Bookings**
   - How do we know that they are completing the booking using an agent? What metrics or sources do we have for this? 
   - **Answer:** 

6. **Interface Target**
   - Can I scope the MVP to the web app only?
   - **Answer:** 

## Customer & Channel

1. **Consent & Legal Constraints**
   - Do I have the right for for re-engagement (email, SMS, WhatsApp, push notifications) from users who abandon? What are the legal/GDPR/DPDP constraints on contacting them?
   - **Answer:** 

2. **Customer Data Platform**
   - Is there an existing customer data platform (CDP) that links a user's website session to their contact info and past booking history?
   - **Answer:** 

3. **Known Pain Points**
   - Are there known pricing/UX pain points — e.g., price changes between search and checkout, mandatory sign-up walls, payment gateway failures — that have already been identified through user research or support tickets?
   - **Answer:** 

## Technical Landscape

1. **Current Tech Stack**
    - What is the current tech stack of the booking engine and website?
   - **Answer:** 

2. **Incomplete Booking State API**
    - Are there existing APIs to retrieve an incomplete booking's state (selected flights, traveller details entered so far) so the MVP can reconstruct the session for the user? Also, is this allowed for unsuccessful bookings since we save Passport details etc.?
   - **Answer:** 

3. **Integration Constraints**
    - What are the integration constraints? Can I embed a widget into the existing booking pages? What about focused pop-ups?
   - **Answer:** 

4. **Existing Chat/Engagement Solutions**
    - Is there an existing chatbot, live-chat, or co-browse solution on the website today? Should I ideally be extending that, or for the MVP build a sample chatbot on my own?
   - **Answer:** 

5. **Pricing API**
    - Is there an API or webhook for real-time fare availability and price-lock? 
   - **Answer:** 

## AI & Personalisation

1. **Historical Recovery Intervention Data**
    - Do you have historical data on which recovery interventions worked? (e.g., discount codes, reminders, agent callbacks) — or is this greenfield with no prior A/B testing?
   - **Answer:** 

2. **Dynamic Pricing & Fare Locking**
    - How do you handle dynamic pricing? If the AI offers to hold a fare or nudges with "price may increase," do we have backend support for temporary price locks or fare caching?
   - **Answer:** 

3. **Fare Availability & Price Locking**
    - If a user abandoned due to indecision, can we guarantee the same price when we re-engage them? Am I allowed to give any discounts/coupons, if yes, what are the constraints here?
   - **Answer:** 




   If Production - Highlight whats and why?
   Assume anything and write clearly. What will the impact be of the assumption?
   Create a presentation. Demo of the code.