/**
 * Behavioral Tracker — Client-side abandonment signal detection
 *
 * Monitors user interactions to detect abandonment intent:
 * - Mouse leaving window, tab switches, idle time
 * - Back button, scroll patterns, form behavior
 * - Sends signals to the backend for risk scoring
 */

const IDLE_SIGNAL_SHORT_MS = 8000;
const IDLE_SIGNAL_LONG_MS = 15000;
const IDLE_CHECK_INTERVAL_MS = 1000;
const RISK_ASSESSMENT_DEBOUNCE_MS = 500;

class AbandonmentTracker {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.signals = {};      // { signalType: count }
        this.idleTimer = null;
        this.idleStart = Date.now();
        this.lastActivity = Date.now();
        this.idle30Triggered = false;
        this.idle60Triggered = false;
        this.currentStep = 'search';
        this.riskScore = 0;
        this.onIntervention = null;  // Callback when AI should intervene
        this.assessmentPending = false;

        this._bindEvents();
        this._startIdleMonitor();
    }

    setStep(step) {
        this.currentStep = step;
        this._logEvent('step_change', { step });
    }

    _addSignal(type) {
        this.signals[type] = (this.signals[type] || 0) + 1;
        this._scheduleAssessment();
    }

    _bindEvents() {
        // Mouse leaving window
        document.addEventListener('mouseleave', (e) => {
            if (e.clientY <= 0) {
                this._addSignal('mouse_leave');
            }
        });

        // Tab visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this._addSignal('tab_switch');
            }
        });

        // Back button / popstate
        window.addEventListener('popstate', () => {
            this._addSignal('back_button');
        });

        // Track activity for idle detection
        const activityEvents = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
        activityEvents.forEach(evt => {
            document.addEventListener(evt, () => {
                this.lastActivity = Date.now();
                this.idle30Triggered = false;
                this.idle60Triggered = false;
            }, { passive: true });
        });

        // Scroll to top detection
        let lastScrollTop = 0;
        window.addEventListener('scroll', () => {
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            if (scrollTop === 0 && lastScrollTop > 200) {
                this._addSignal('scroll_to_top');
            }
            lastScrollTop = scrollTop;
        }, { passive: true });

        // Form field deletion
        document.addEventListener('input', (e) => {
            if (e.target.tagName === 'INPUT' && e.inputType === 'deleteContentBackward') {
                this._addSignal('form_delete');
            }
        });

        // Price hover detection (on elements with data-price attribute)
        document.addEventListener('mouseenter', (e) => {
            if (e.target.closest('[data-price]')) {
                this._addSignal('price_hover');
            }
        }, true);

        // Rapid frustration clicks
        let clickTimes = [];
        document.addEventListener('click', () => {
            const now = Date.now();
            clickTimes.push(now);
            clickTimes = clickTimes.filter(t => now - t < 2000);
            if (clickTimes.length > 5) {
                this._addSignal('rapid_clicks');
                clickTimes = [];
            }
        });
    }

    _startIdleMonitor() {
        setInterval(() => {
            const idleTime = Date.now() - this.lastActivity;
            if (idleTime > IDLE_SIGNAL_LONG_MS && !this.idle60Triggered) {
                this._addSignal('idle_60s');
                this.idle60Triggered = true;
            } else if (idleTime > IDLE_SIGNAL_SHORT_MS && !this.idle30Triggered) {
                this._addSignal('idle_30s');
                this.idle30Triggered = true;
            }
        }, IDLE_CHECK_INTERVAL_MS);
    }

    async _scheduleAssessment() {
        if (this.assessmentPending) return;
        this.assessmentPending = true;

        setTimeout(async () => {
            await this._assessRisk();
            this.assessmentPending = false;
        }, RISK_ASSESSMENT_DEBOUNCE_MS);
    }

    async _assessRisk() {
        const signalList = Object.entries(this.signals).map(([type, count]) => ({ type, count }));
        if (signalList.length === 0) return;

        try {
            const response = await fetch('/api/risk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    signals: signalList,
                    current_step: this.currentStep,
                }),
            });

            const data = await response.json();
            this.riskScore = data.risk.score;

            // Trigger intervention if backend says so
            if (data.intervention && this.onIntervention) {
                this.onIntervention(data.intervention);
            }

            return data;
        } catch (err) {
            console.warn('Risk assessment failed:', err);
        }
    }

    async _logEvent(eventType, eventData = {}) {
        try {
            await fetch('/api/event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    event_type: eventType,
                    event_data: eventData,
                }),
            });
        } catch (err) {
            // Silent fail for non-critical telemetry
        }
    }

    getRiskScore() {
        return this.riskScore;
    }

    getSignals() {
        return { ...this.signals };
    }
}
