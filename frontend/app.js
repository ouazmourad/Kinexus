/**
 * ThoughtLink Dashboard — Main Application
 * WebSocket client + UI state management + keyboard controls
 */

// --- WebSocket ---
let ws = null;
let wsReconnectTimer = null;
let connected = false;
let tickCount = 0;

// --- Components ---
let eegChart = null;
let robotView = null;
let voiceManager = null;

// --- State ---
let currentGear = 'NEUTRAL';
let currentAction = 'IDLE';
let brainEnabled = true;
let voiceEnabled = true;
let testModeActive = false;
let eegStreamEnabled = true;
let simBrainClass = null;  // null = off, 0-4 = simulated class
let controlMode = 'direct'; // 'direct' = explicit commands, 'bci' = gear-dependent brain schema
let currentToggledAction = null;
let selectedRobot = 'robot_0';
let allRobots = [];

// ========================
// WebSocket Connection
// ========================

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws`;

    try {
        ws = new WebSocket(wsUrl);
    } catch (e) {
        console.error('[WS] Connection error:', e);
        scheduleReconnect();
        return;
    }

    ws.onopen = () => {
        connected = true;
        updateConnectionStatus(true);
        console.log('[WS] Connected');
        if (wsReconnectTimer) {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = null;
        }
    };

    ws.onclose = () => {
        connected = false;
        updateConnectionStatus(false);
        console.log('[WS] Disconnected');
        scheduleReconnect();
    };

    ws.onerror = (err) => {
        console.error('[WS] Error:', err);
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleServerMessage(msg);
        } catch (e) {
            console.error('[WS] Parse error:', e);
        }
    };
}

function scheduleReconnect() {
    if (wsReconnectTimer) return;
    wsReconnectTimer = setTimeout(() => {
        wsReconnectTimer = null;
        connectWebSocket();
    }, 2000);
}

function updateConnectionStatus(isConnected) {
    const dot = document.getElementById('conn-dot');
    const text = document.getElementById('conn-text');
    if (dot) dot.classList.toggle('connected', isConnected);
    if (text) text.textContent = isConnected ? 'Connected' : 'Disconnected';
}

function wsSend(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
    }
}

// ========================
// Message Handlers
// ========================

function handleServerMessage(msg) {
    switch (msg.type) {
        case 'state_update':
            handleStateUpdate(msg);
            break;
        case 'eeg_data':
            handleEEGData(msg);
            break;
        case 'command_log':
            handleCommandLog(msg);
            break;
        case 'tts_request':
            handleTTSRequest(msg);
            break;
        case 'test_mode_update':
            testModeActive = msg.enabled;
            updateToggleButton('btn-test-mode', testModeActive);
            break;
        case 'input_toggle_update':
            brainEnabled = msg.brain_enabled;
            voiceEnabled = msg.voice_enabled;
            updateToggleButton('btn-brain', brainEnabled);
            updateToggleButton('btn-voice', voiceEnabled);
            break;
        case 'eeg_stream_update':
            eegStreamEnabled = msg.enabled;
            updateToggleButton('btn-eeg-stream', eegStreamEnabled);
            break;
        case 'nav_update':
            handleNavUpdate(msg);
            break;
        case 'sim_brain_update':
            simBrainClass = msg.class_index;
            updateSimBrainUI(simBrainClass);
            break;
        case 'robot_selected':
            selectedRobot = msg.robot_id;
            break;
        case 'cancel_confirm_prompt':
            showCancelConfirm(msg.description);
            break;
        case 'cancel_confirmed':
            hideCancelConfirm();
            addLogEntry('system', 'CANCELLED', 'Action cancelled', Date.now() / 1000);
            break;
        case 'cancel_confirm_dismiss':
            hideCancelConfirm();
            break;
        case 'full_reset_ack':
            if (robotView) robotView.reset();
            tickCount = 0;
            simBrainClass = null;
            currentToggledAction = null;
            updateSimBrainUI(null);
            updateToggleIndicator(null);
            eegStreamEnabled = true;
            updateToggleButton('btn-eeg-stream', true);
            hideCancelConfirm();
            addLogEntry('system', 'FULL_RESET', 'Full system reset', Date.now() / 1000);
            break;
        default:
            break;
    }
}

function handleStateUpdate(msg) {
    tickCount++;

    // Gear display
    updateGearDisplay(msg.gear);

    // Brain decode panel
    updateBrainPanel(msg.brain_class, msg.brain_confidence, msg.brain_gated, msg.action);

    // Action overlay
    updateActionOverlay(msg.action, msg.action_source);

    // Holding indicator
    updateHoldingIndicator(msg.holding_item);

    // Toggle indicator
    currentToggledAction = msg.toggled_action || null;
    updateToggleIndicator(currentToggledAction);

    // Multi-robot state
    selectedRobot = msg.selected_robot || 'robot_0';
    allRobots = msg.robots || [];

    // Robot view — pass all robots
    if (robotView) {
        robotView.updateState(msg.robot_state, msg.action, allRobots, selectedRobot);
    }

    // Orchestration overlay
    updateOrchestrationOverlay(msg.orchestration);

    // Metrics
    updateMetrics(msg.latency_ms, msg.action_source);

    currentAction = msg.action;
}

function handleEEGData(msg) {
    if (eegChart && msg.channels) {
        eegChart.pushData(msg.channels);
    }
}

function handleCommandLog(msg) {
    addLogEntry(msg.source, msg.action, msg.text, msg.timestamp);
}

function handleTTSRequest(msg) {
    if (!msg.text) return;

    // Prefer ElevenLabs audio if available (base64 mp3)
    if (msg.audio_base64) {
        try {
            const audio = new Audio('data:audio/mpeg;base64,' + msg.audio_base64);
            audio.play().catch(() => {
                // Autoplay blocked — fall back to browser speech
                speakBrowser(msg.text);
            });
            return;
        } catch (e) { /* fall through */ }
    }

    // Fallback: browser speech synthesis
    speakBrowser(msg.text);
}

function speakBrowser(text) {
    if ('speechSynthesis' in window && text) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.2;
        utterance.pitch = 0.9;
        speechSynthesis.speak(utterance);
    }
}

// ========================
// UI Updates
// ========================

function updateGearDisplay(gear) {
    if (gear === currentGear) return;
    currentGear = gear;

    const gearMap = { NEUTRAL: 'N', FORWARD: 'F', REVERSE: 'R', ORCHESTRATE: 'O' };
    const gearClasses = { NEUTRAL: 'neutral', FORWARD: 'forward', REVERSE: 'reverse', ORCHESTRATE: 'orchestrate' };

    ['N', 'F', 'R', 'O'].forEach(g => {
        const el = document.getElementById('gear-' + g);
        if (el) {
            const isActive = gearMap[gear] === g;
            el.className = 'gear-label' + (isActive ? ` active ${gearClasses[gear]}` : '');
        }
    });

    const gearText = document.getElementById('gear-text');
    if (gearText) {
        gearText.textContent = gear;
        gearText.className = 'gear-text ' + (gearClasses[gear] || '');
    }

    // Update BOTH button hint in BCI mode
    if (controlMode === 'bci') {
        var bothBtn = document.getElementById('btn-both');
        if (bothBtn) {
            var hint = bothBtn.querySelector('.key-hint');
            if (hint) hint.textContent = 'W — ' + getBothHint();
        }
    }
}

function updateBrainPanel(brainClass, confidence, gated, action) {
    const classEl = document.getElementById('brain-class');
    const fillEl = document.getElementById('confidence-fill');
    const valueEl = document.getElementById('confidence-value');
    const cmdEl = document.getElementById('brain-command');
    const badgeEl = document.getElementById('stable-badge');

    if (classEl) classEl.textContent = brainClass || '--';

    const pct = Math.round((confidence || 0) * 100);
    if (fillEl) fillEl.style.width = pct + '%';
    if (valueEl) valueEl.textContent = pct + '%';
    if (cmdEl) cmdEl.textContent = action || '--';

    if (badgeEl) {
        if (gated) {
            badgeEl.textContent = 'GATED';
            badgeEl.className = 'stable-badge gated';
        } else if (confidence > 0.7) {
            badgeEl.textContent = 'STABLE';
            badgeEl.className = 'stable-badge stable';
        } else {
            badgeEl.textContent = 'UNSTABLE';
            badgeEl.className = 'stable-badge unstable';
        }
    }
}

function updateToggleIndicator(toggledAction) {
    const el = document.getElementById('toggle-indicator');
    if (!el) return;
    if (toggledAction) {
        el.textContent = 'TOGGLE: ' + toggledAction;
        el.style.display = 'block';
    } else {
        el.textContent = '';
        el.style.display = 'none';
    }
}

function updateOrchestrationOverlay(orch) {
    const overlay = document.getElementById('orchestration-overlay');
    const hintEl = document.querySelector('.orch-hint');
    if (!overlay) return;

    if (!orch) {
        overlay.style.display = 'none';
        return;
    }

    overlay.style.display = 'block';
    const phaseEl = document.getElementById('orch-phase');
    const optionsEl = document.getElementById('orch-options');

    if (phaseEl) {
        if (orch.phase === 'SELECTING_ACTION') phaseEl.textContent = 'SELECT ACTION';
        else if (orch.phase === 'SELECTING_LANDMARK') phaseEl.textContent = 'SELECT LANDMARK';
        else if (orch.phase === 'SELECTING_ROBOT') phaseEl.textContent = 'SELECT ROBOTS';
    }

    if (hintEl) {
        if (orch.phase === 'SELECTING_ROBOT') {
            hintEl.textContent = 'L/R Fist: cycle | Both: toggle select | Hold Both 2s: confirm';
        } else {
            hintEl.textContent = 'L/R Fist: cycle | Both Fists 2s: confirm';
        }
    }

    if (optionsEl) {
        var html = '';
        if (orch.phase === 'SELECTING_ROBOT') {
            // Robot selection list with checkmarks
            var robotIds = orch.robot_ids || [];
            var cycleIdx = orch.robot_cycle_index || 0;
            var selectedIds = orch.selected_robot_ids || [];
            for (var i = 0; i < robotIds.length; i++) {
                var isCursor = i === cycleIdx;
                var isSelected = selectedIds.indexOf(robotIds[i]) >= 0;
                var cls = 'orch-option' + (isCursor ? ' selected' : '');
                var check = isSelected ? '\u2611 ' : '\u2610 ';
                html += '<div class="' + cls + '">' + check + robotIds[i] + '</div>';
            }
        } else {
            var items = orch.phase === 'SELECTING_ACTION' ? orch.actions : orch.landmarks;
            var selectedIdx = orch.phase === 'SELECTING_ACTION' ? orch.action_index : orch.landmark_index;
            for (var i = 0; i < items.length; i++) {
                var cls = i === selectedIdx ? 'orch-option selected' : 'orch-option';
                html += '<div class="' + cls + '">' + items[i] + '</div>';
            }
        }
        optionsEl.innerHTML = html;
    }
}

function updateActionOverlay(action, source) {
    const el = document.getElementById('action-overlay');
    if (!el) return;

    if (source === 'autopilot') {
        el.textContent = 'NAV: ' + (action || 'IDLE');
    } else {
        el.textContent = action || 'IDLE';
    }

    let cls = 'idle';
    if (source === 'autopilot') cls = 'navigating';
    else if (action === 'MOVE_FORWARD' || action === 'MOVE_BACKWARD') cls = 'moving';
    else if (action === 'ROTATE_LEFT' || action === 'ROTATE_RIGHT') cls = 'rotating';
    else if (action === 'GRAB' || action === 'RELEASE' || action === 'HOLD') cls = 'grabbing';
    else if (action === 'STOP' || action === 'EMERGENCY_STOP') cls = 'stopped';

    el.className = 'action-overlay ' + cls;
}

function updateHoldingIndicator(holding) {
    const icon = document.getElementById('holding-icon');
    const text = document.getElementById('holding-text');
    if (icon) icon.innerHTML = holding ? '&#9632;' : '&#9633;';
    if (text) {
        text.textContent = holding ? 'Holding item' : 'Not holding';
        text.style.color = holding ? '#a855f7' : '';
    }
}

function updateMetrics(latencyMs, source) {
    const latencyEl = document.getElementById('metric-latency');
    const fpsEl = document.getElementById('metric-fps');
    const ticksEl = document.getElementById('metric-ticks');
    const sourceEl = document.getElementById('metric-source');

    if (latencyEl) latencyEl.textContent = Math.round(latencyMs || 0);
    if (fpsEl) fpsEl.textContent = '10';
    if (ticksEl) ticksEl.textContent = tickCount;
    if (sourceEl) {
        sourceEl.textContent = (source || '--').toUpperCase();
        const colors = { brain_gesture: '#a855f7', brain_toggle: '#06b6d4', brain: '#06b6d4', voice: '#a855f7', idle: '#64748b', manual: '#eab308' };
        sourceEl.style.color = colors[source] || '#64748b';
    }
}

// ========================
// Command Log
// ========================

let logEntryCount = 0;
const MAX_LOG_ENTRIES = 100;

function addLogEntry(source, action, text, timestamp) {
    const log = document.getElementById('command-log');
    if (!log) return;

    const time = new Date((timestamp || Date.now() / 1000) * 1000);
    const timeStr = time.toLocaleTimeString('en-US', { hour12: false });

    const entry = document.createElement('div');
    entry.className = 'log-entry ' + (source || 'idle');
    entry.innerHTML = `
        <span class="log-time">${timeStr}</span>
        <span class="log-source ${source || ''}">[${(source || '?').toUpperCase()}]</span>
        <span class="log-action">${text || action || '?'}</span>
    `;

    log.appendChild(entry);
    logEntryCount++;

    // Trim old entries
    while (logEntryCount > MAX_LOG_ENTRIES && log.firstChild) {
        log.removeChild(log.firstChild);
        logEntryCount--;
    }

    // Auto-scroll
    log.scrollTop = log.scrollHeight;
}

// ========================
// Manual Controls
// ========================

function sendCommand(action) {
    wsSend({ type: 'manual_command', action: action });
}

function sendReset() {
    wsSend({ type: 'reset' });
}

function toggleControlMode() {
    // Clean up any held BCI key when switching modes
    if (_heldBCIKey !== null) {
        simBrainStop();
        _heldBCIKey = null;
    }
    controlMode = controlMode === 'direct' ? 'bci' : 'direct';
    renderManualControls();
}

function getBothHint() {
    if (currentGear === 'FORWARD') return 'FWD';
    if (currentGear === 'REVERSE') return 'BWD';
    if (currentGear === 'ORCHESTRATE') return 'Orch';
    return 'Hold';
}

function renderManualControls() {
    var grid = document.getElementById('manual-controls-grid');
    var badge = document.getElementById('control-mode-badge');
    if (!grid) return;

    if (controlMode === 'bci') {
        if (badge) {
            badge.textContent = 'BCI [M]';
            badge.classList.add('mode-bci');
        }
        grid.innerHTML =
            '<div class="ctrl-btn sim-btn" data-cls="1" onmousedown="simBrainStart(1)" onmouseup="simBrainStop()" onmouseleave="simBrainStop()" ontouchstart="simBrainStart(1)" ontouchend="simBrainStop()">L.FIST<span class="key-hint">A — Rot L</span></div>' +
            '<div class="ctrl-btn accent sim-btn" id="btn-both" data-cls="2" onmousedown="simBrainStart(2)" onmouseup="simBrainStop()" onmouseleave="simBrainStop()" ontouchstart="simBrainStart(2)" ontouchend="simBrainStop()">BOTH<span class="key-hint">W — ' + getBothHint() + '</span></div>' +
            '<div class="ctrl-btn sim-btn" data-cls="0" onmousedown="simBrainStart(0)" onmouseup="simBrainStop()" onmouseleave="simBrainStop()" ontouchstart="simBrainStart(0)" ontouchend="simBrainStop()">R.FIST<span class="key-hint">D — Rot R</span></div>' +
            '<div class="ctrl-btn sim-btn" data-cls="3" onmousedown="simBrainStart(3)" onmouseup="simBrainStop()" onmouseleave="simBrainStop()" ontouchstart="simBrainStart(3)" ontouchend="simBrainStop()">TONGUE<span class="key-hint">G — Shift</span></div>' +
            '<div class="ctrl-btn sim-btn" data-cls="4" onmousedown="simBrainStart(4)" onmouseup="simBrainStop()" onmouseleave="simBrainStop()" ontouchstart="simBrainStart(4)" ontouchend="simBrainStop()">RELAX<span class="key-hint">S — Idle</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'ORCH_CONFIRM\')">CONFIRM<span class="key-hint">Enter</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'ORCH_CANCEL\')">CANCEL<span class="key-hint">Esc</span></div>' +
            '<div class="ctrl-btn" onclick="sendReset()">RESET<span class="key-hint">R</span></div>';
    } else {
        if (badge) {
            badge.textContent = 'DIRECT [M]';
            badge.classList.remove('mode-bci');
        }
        grid.innerHTML =
            '<div class="ctrl-btn" onclick="sendCommand(\'ROTATE_LEFT\')">ROT L<span class="key-hint">A</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'MOVE_FORWARD\')">FWD<span class="key-hint">W</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'ROTATE_RIGHT\')">ROT R<span class="key-hint">D</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'GRAB\')">GRAB<span class="key-hint">E</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'STOP\')">STOP<span class="key-hint">S</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'RELEASE\')">REL<span class="key-hint">Q</span></div>' +
            '<div class="ctrl-btn accent" onclick="sendCommand(\'SHIFT_GEAR\')">SHIFT<span class="key-hint">G</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'BOTH_FISTS\')">BOTH<span class="key-hint">Space</span></div>' +
            '<div class="ctrl-btn" onclick="sendReset()">RESET<span class="key-hint">R</span></div>';
    }
}

// ========================
// Debug Controls
// ========================

function toggleBrain() {
    wsSend({ type: 'toggle_brain' });
}

function toggleVoice() {
    voiceEnabled = !voiceEnabled;
    if (!voiceEnabled && voiceManager) {
        voiceManager.stop();
    }
    wsSend({ type: 'toggle_voice' });
}

function toggleTestMode() {
    wsSend({ type: 'toggle_test_mode' });
}

function toggleEEGStream() {
    wsSend({ type: 'toggle_eeg_stream' });
}

function sendFullReset() {
    wsSend({ type: 'full_reset' });
    if (robotView) robotView.reset();
    // Clear command log
    var log = document.getElementById('command-log');
    if (log) { log.innerHTML = ''; logEntryCount = 0; }
    tickCount = 0;
    currentToggledAction = null;
    updateToggleIndicator(null);
}

function updateToggleButton(btnId, active) {
    var btn = document.getElementById(btnId);
    if (!btn) return;
    if (active) {
        btn.classList.add('active-toggle');
    } else {
        btn.classList.remove('active-toggle');
    }
    var hint = btn.querySelector('.key-hint');
    if (hint) hint.textContent = active ? 'On' : 'Off';
}

// ========================
// Brain Simulator (press-and-hold)
// ========================

let _simBrainActive = false;

function simBrainStart(classIndex) {
    if (_simBrainActive) return; // prevent duplicate
    _simBrainActive = true;
    wsSend({ type: 'sim_brain_start', class_index: classIndex });
}

function simBrainStop() {
    if (!_simBrainActive) return;
    _simBrainActive = false;
    wsSend({ type: 'sim_brain_stop' });
}

function updateSimBrainUI(activeClass) {
    document.querySelectorAll('.sim-btn').forEach(function(btn) {
        var cls = parseInt(btn.getAttribute('data-cls'));
        if (activeClass !== null && cls === activeClass) {
            btn.classList.add('sim-active');
        } else {
            btn.classList.remove('sim-active');
        }
    });
}

// ========================
// Voice
// ========================

function toggleMic() {
    if (voiceManager) {
        voiceManager.toggle();
    }
}

function handleVoiceTranscript(text, confidence) {
    // Update UI
    const lastEl = document.getElementById('last-transcript-text');
    if (lastEl) lastEl.textContent = `"${text}"`;

    // Add to transcript list
    const list = document.getElementById('transcript-list');
    if (list) {
        const entry = document.createElement('div');
        entry.className = 'transcript-entry';
        entry.textContent = text;
        list.appendChild(entry);
        list.scrollTop = list.scrollHeight;

        // Trim
        while (list.children.length > 20) {
            list.removeChild(list.firstChild);
        }
    }

    // Send to backend only if voice is enabled
    if (!voiceEnabled) return;
    wsSend({
        type: 'voice_transcript',
        text: text,
        confidence: confidence,
        timestamp: Date.now() / 1000,
    });
}

// ========================
// Navigation
// ========================

function handleNavUpdate(msg) {
    const overlay = document.getElementById('nav-overlay');
    const targetEl = document.getElementById('nav-target');
    const distEl = document.getElementById('nav-dist');

    if (!overlay) return;

    if (msg.active) {
        overlay.style.display = 'flex';
        if (targetEl) targetEl.textContent = 'NAV → ' + (msg.target_name || '?');
        if (distEl) distEl.textContent = (msg.distance || 0).toFixed(1) + 'm';
        // Pass target to robot view for marker drawing
        if (robotView) {
            robotView.navTarget = { x: msg.target_x, y: msg.target_y, name: msg.target_name };
        }
    } else {
        overlay.style.display = 'none';
        if (robotView) robotView.navTarget = null;
        if (msg.arrived && msg.target_name) {
            addLogEntry('system', 'ARRIVED', 'Arrived at ' + msg.target_name, Date.now() / 1000);
        }
    }
}

function cancelNav() {
    wsSend({ type: 'cancel_nav' });
}

// ========================
// Cancel Confirmation
// ========================

let _cancelConfirmTimer = null;

function showCancelConfirm(description) {
    var overlay = document.getElementById('cancel-confirm-overlay');
    var textEl = document.getElementById('cancel-confirm-text');
    var countdownEl = document.getElementById('cancel-confirm-countdown');
    if (!overlay) return;

    if (textEl) textEl.textContent = 'Cancel ' + (description || 'active task') + '?';
    overlay.style.display = 'flex';

    // Countdown timer (5 seconds)
    var remaining = 5;
    if (countdownEl) countdownEl.textContent = remaining + 's';
    if (_cancelConfirmTimer) clearInterval(_cancelConfirmTimer);
    _cancelConfirmTimer = setInterval(function() {
        remaining--;
        if (countdownEl) countdownEl.textContent = remaining + 's';
        if (remaining <= 0) {
            hideCancelConfirm();
        }
    }, 1000);
}

function hideCancelConfirm() {
    var overlay = document.getElementById('cancel-confirm-overlay');
    if (overlay) overlay.style.display = 'none';
    if (_cancelConfirmTimer) {
        clearInterval(_cancelConfirmTimer);
        _cancelConfirmTimer = null;
    }
}

// ========================
// Robot Selection (click on map)
// ========================

function selectRobot(robotId) {
    wsSend({ type: 'select_robot', robot_id: robotId });
}

// ========================
// Keyboard Controls
// ========================

// Reverse map: action -> button text for highlight matching
const ACTION_TO_BTN_TEXT = {
    'MOVE_FORWARD': ['FWD', 'BOTH'],
    'MOVE_BACKWARD': [],
    'ROTATE_LEFT': ['ROT L', 'L.FIST'],
    'ROTATE_RIGHT': ['ROT R', 'R.FIST'],
    'STOP': ['STOP', 'RELAX'],
    'GRAB': ['GRAB'],
    'RELEASE': ['REL'],
    'SHIFT_GEAR': ['SHIFT', 'TONGUE'],
    'BOTH_FISTS': ['BOTH'],
    'ORCH_CONFIRM': ['CONFIRM'],
    'ORCH_CANCEL': ['CANCEL'],
};

function highlightButton(action, active) {
    var grid = document.getElementById('manual-controls-grid');
    if (!grid) return;
    var labels = ACTION_TO_BTN_TEXT[action] || [];
    var buttons = grid.querySelectorAll('.ctrl-btn');
    for (var i = 0; i < buttons.length; i++) {
        var btnText = buttons[i].childNodes[0];
        if (!btnText) continue;
        var text = (btnText.textContent || '').trim();
        if (labels.indexOf(text) >= 0) {
            if (active) {
                buttons[i].classList.add('key-active');
            } else {
                buttons[i].classList.remove('key-active');
            }
        }
    }
}

const KEY_MAP_DIRECT = {
    'w': 'MOVE_FORWARD',
    'ArrowUp': 'MOVE_FORWARD',
    's': 'STOP',
    'ArrowDown': 'STOP',
    'a': 'ROTATE_LEFT',
    'ArrowLeft': 'ROTATE_LEFT',
    'd': 'ROTATE_RIGHT',
    'ArrowRight': 'ROTATE_RIGHT',
    'x': 'MOVE_BACKWARD',
    'e': 'GRAB',
    'q': 'RELEASE',
    'g': 'SHIFT_GEAR',
    ' ': 'BOTH_FISTS',
};

// BCI mode: keys map to brain class indices for press-and-hold via simBrainStart/Stop
const KEY_BCI_CLASS = {
    'w': 2,            // Both Fists
    'ArrowUp': 2,
    's': 4,            // Relax
    'ArrowDown': 4,
    'a': 1,            // Left Fist
    'ArrowLeft': 1,
    'd': 0,            // Right Fist
    'ArrowRight': 0,
    'g': 3,            // Tongue Tapping
    ' ': 2,            // Both Fists
};

// BCI one-shot commands (not press-and-hold)
const KEY_BCI_ONESHOT = {
    'Enter': 'ORCH_CONFIRM',
    'Escape': 'ORCH_CANCEL',
};

// Track held BCI key to prevent key-repeat spam
let _heldBCIKey = null;

document.addEventListener('keydown', (e) => {
    // Don't capture if typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    // Mode toggle
    if (e.key === 'm' || e.key === 'M') {
        e.preventDefault();
        toggleControlMode();
        return;
    }

    // Reset
    if (e.key === 'r') {
        e.preventDefault();
        sendReset();
        return;
    }

    if (controlMode === 'bci') {
        // BCI mode: press-and-hold → simBrainStart/Stop (like brain simulator)
        if (e.key in KEY_BCI_CLASS) {
            e.preventDefault();
            if (_heldBCIKey === e.key) return; // ignore key repeat
            // Release previous key if different
            if (_heldBCIKey !== null) {
                simBrainStop();
            }
            _heldBCIKey = e.key;
            simBrainStart(KEY_BCI_CLASS[e.key]);
            return;
        }
        // One-shot BCI commands (Enter/Escape for orch confirm/cancel)
        if (e.key in KEY_BCI_ONESHOT) {
            e.preventDefault();
            sendCommand(KEY_BCI_ONESHOT[e.key]);
            highlightButton(KEY_BCI_ONESHOT[e.key], true);
            return;
        }
    } else {
        // Direct mode: instant commands
        if (e.key in KEY_MAP_DIRECT) {
            e.preventDefault();
            var action = KEY_MAP_DIRECT[e.key];
            sendCommand(action);
            highlightButton(action, true);
        }
    }
});

document.addEventListener('keyup', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (controlMode === 'bci') {
        // Release BCI press-and-hold
        if (e.key in KEY_BCI_CLASS && _heldBCIKey === e.key) {
            _heldBCIKey = null;
            simBrainStop();
        }
        if (e.key in KEY_BCI_ONESHOT) {
            highlightButton(KEY_BCI_ONESHOT[e.key], false);
        }
    } else {
        if (e.key in KEY_MAP_DIRECT) {
            highlightButton(KEY_MAP_DIRECT[e.key], false);
        }
    }
});

// ========================
// Server Info / Footer
// ========================

function fetchServerInfo() {
    fetch('/api/server-info')
        .then(r => r.json())
        .then(info => {
            const footer = document.getElementById('deploy-footer');
            if (footer) {
                footer.textContent = `ThoughtLink v${info.version} — Edge Server: ${info.host}:${info.port} | Clients connected: ${info.clients_connected}`;
            }
        })
        .catch(() => {});
}

// ========================
// Initialization
// ========================

window.addEventListener('DOMContentLoaded', () => {
    // Initialize components
    eegChart = new EEGChart('eeg-canvas');
    robotView = new RobotView('robot-canvas');
    voiceManager = new VoiceManager(handleVoiceTranscript);

    // EEG panel always visible

    // Wire up robot click-to-select callback
    if (robotView) {
        robotView.onRobotClick = selectRobot;
    }

    // Set initial gear display
    updateGearDisplay('NEUTRAL');

    // Render manual controls for initial mode
    renderManualControls();

    // Connect WebSocket
    connectWebSocket();

    // Fetch server info for footer, refresh every 5s
    fetchServerInfo();
    setInterval(fetchServerInfo, 5000);

    console.log('[ThoughtLink] Dashboard initialized');
    addLogEntry('system', 'INIT', 'Dashboard initialized', Date.now() / 1000);
});
