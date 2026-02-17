/**
 * Voice Status — Browser Speech-to-Text using Web Speech API.
 */

class VoiceManager {
    constructor(onTranscript) {
        this.onTranscript = onTranscript;
        this.recognition = null;
        this.listening = false;
        this.supported = 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;

        if (this.supported) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = true;
            this.recognition.interimResults = false;
            this.recognition.lang = 'en-US';

            this.recognition.onresult = (event) => {
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    if (event.results[i].isFinal) {
                        const text = event.results[i][0].transcript.trim();
                        const confidence = event.results[i][0].confidence;
                        if (text && this.onTranscript) {
                            this.onTranscript(text, confidence);
                        }
                    }
                }
            };

            this.recognition.onerror = (event) => {
                console.warn('[Voice] Error:', event.error);
                if (event.error === 'not-allowed') {
                    this.listening = false;
                    this._updateUI(false);
                }
            };

            this.recognition.onend = () => {
                // Auto-restart if still supposed to be listening
                if (this.listening) {
                    try { this.recognition.start(); } catch (e) {}
                }
            };
        }
    }

    toggle() {
        if (!this.supported) {
            console.warn('[Voice] Speech recognition not supported in this browser');
            return false;
        }
        if (this.listening) {
            this.stop();
        } else {
            this.start();
        }
        return this.listening;
    }

    start() {
        if (!this.supported || this.listening) return;
        try {
            this.recognition.start();
            this.listening = true;
            this._updateUI(true);
        } catch (e) {
            console.warn('[Voice] Start error:', e);
        }
    }

    stop() {
        if (!this.supported || !this.listening) return;
        this.listening = false;
        try { this.recognition.stop(); } catch (e) {}
        this._updateUI(false);
    }

    _updateUI(active) {
        const indicator = document.getElementById('mic-indicator');
        const text = document.getElementById('mic-text');
        if (indicator) {
            indicator.classList.toggle('listening', active);
        }
        if (text) {
            text.textContent = active ? 'Listening...' : 'Mic off';
        }
    }
}
