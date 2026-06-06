/**
 * AI Chat Widget — Real-time conversational assistant
 *
 * Provides a chat interface powered by Claude that:
 * - Appears proactively when abandonment risk is detected
 * - Responds to user questions about flights, booking, payment
 * - Uses WebSocket for real-time communication with fallback to REST
 */

const NUDGE_AUTO_HIDE_MS = 8000;

class ChatWidget {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.isOpen = false;
        this.ws = null;
        this.messages = [];
        this.unreadCount = 0;
        this.onUserMessage = null;
        this.onAssistantPayload = null;

        this._createDOM();
        this._connectWebSocket();
    }

    _createDOM() {
        // Chat bubble (floating button)
        this.bubble = document.createElement('div');
        this.bubble.className = 'chat-bubble';
        this.bubble.innerHTML = `
            <span>&#x2708;</span>
            <div class="badge">0</div>
        `;
        this.bubble.onclick = () => this.toggle();

        // Nudge toast (proactive message preview)
        this.nudge = document.createElement('div');
        this.nudge.className = 'nudge-toast';
        this.nudge.innerHTML = `
            <button class="nudge-close" onclick="event.stopPropagation();">&times;</button>
            <div class="nudge-header">
                <div class="nudge-avatar">&#x2708;</div>
                <div class="nudge-name">AirAssist</div>
            </div>
            <div class="nudge-text"></div>
        `;
        this.nudge.onclick = () => {
            this.nudge.classList.remove('show');
            this.open();
        };
        this.nudge.querySelector('.nudge-close').onclick = (e) => {
            e.stopPropagation();
            this.nudge.classList.remove('show');
        };

        // Chat panel
        this.panel = document.createElement('div');
        this.panel.className = 'chat-widget';
        this.panel.innerHTML = `
            <div class="chat-header">
                <div class="avatar">&#x2708;</div>
                <div class="info">
                    <h4>AirAssist</h4>
                    <p>AI Booking Assistant</p>
                </div>
                <button class="close-chat">&times;</button>
            </div>
            <div class="chat-messages"></div>
            <div class="chat-input">
                <input type="text" placeholder="Ask me anything about your booking..." />
                <button>&#x27A4;</button>
            </div>
        `;

        this.panel.querySelector('.close-chat').onclick = () => this.close();
        this.inputEl = this.panel.querySelector('.chat-input input');
        this.sendBtn = this.panel.querySelector('.chat-input button');
        this.messagesEl = this.panel.querySelector('.chat-messages');

        this.sendBtn.onclick = () => this._sendMessage();
        this.inputEl.onkeydown = (e) => {
            if (e.key === 'Enter') this._sendMessage();
        };

        document.body.appendChild(this.nudge);
        document.body.appendChild(this.panel);
        document.body.appendChild(this.bubble);
    }

    _connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        try {
            this.ws = new WebSocket(`${protocol}://${window.location.host}/ws/chat/${this.sessionId}`);

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'chat_response') {
                    this._removeTypingIndicator();
                    this._addMessage('assistant', data.message);
                    this._emitAssistantPayload(data);
                }
            };

            this.ws.onclose = () => {
                // Will fall back to REST API
                this.ws = null;
            };
        } catch (e) {
            this.ws = null;
        }
    }

    toggle() {
        if (this.isOpen) this.close();
        else this.open();
    }

    open() {
        this.isOpen = true;
        this.panel.classList.add('open');
        this.nudge.classList.remove('show');
        this.unreadCount = 0;
        this._updateBadge();
        this.inputEl.focus();
    }

    close() {
        this.isOpen = false;
        this.panel.classList.remove('open');
    }

    /**
     * Show a proactive AI message (triggered by abandonment detection)
     */
    showProactiveMessage(message) {
        // Add to chat history
        this._addMessage('assistant', message);

        // Show nudge toast if chat is closed
        if (!this.isOpen) {
            this.nudge.querySelector('.nudge-text').textContent = message;
            this.nudge.classList.add('show');
            this.unreadCount++;
            this._updateBadge();

            setTimeout(() => {
                this.nudge.classList.remove('show');
            }, NUDGE_AUTO_HIDE_MS);
        }
    }

    async _sendMessage() {
        const text = this.inputEl.value.trim();
        if (!text) return;

        this.inputEl.value = '';

        this._addMessage('user', text);

        if (typeof this.onUserMessage === 'function') {
            try {
                const handled = await this.onUserMessage(text);
                if (handled) {
                    return;
                }
            } catch (err) {
                console.warn('Chat pre-send handler failed', err);
            }
        }

        this._showTypingIndicator();

        // Try WebSocket first, fall back to REST
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ message: text }));
        } else {
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: this.sessionId,
                        message: text,
                    }),
                });
                const data = await response.json();
                this._removeTypingIndicator();
                this._addMessage('assistant', data.response);
                this._emitAssistantPayload(data);
            } catch (err) {
                this._removeTypingIndicator();
                this._addMessage('assistant', "I'm having trouble connecting. Please try again in a moment!");
            }
        }
    }

    _addMessage(role, content) {
        this.messages.push({ role, content });

        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.textContent = content;
        this.messagesEl.appendChild(div);
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }

    addLocalAssistantMessage(content) {
        this._addMessage('assistant', content);
    }

    _showTypingIndicator() {
        const div = document.createElement('div');
        div.className = 'message typing';
        div.id = 'typing-indicator';
        div.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
        this.messagesEl.appendChild(div);
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }

    _removeTypingIndicator() {
        const typing = document.getElementById('typing-indicator');
        if (typing) typing.remove();
    }

    _updateBadge() {
        const badge = this.bubble.querySelector('.badge');
        badge.textContent = this.unreadCount;
        badge.classList.toggle('show', this.unreadCount > 0);
    }

    _emitAssistantPayload(payload) {
        if (typeof this.onAssistantPayload === 'function') {
            this.onAssistantPayload(payload);
        }
    }
}
