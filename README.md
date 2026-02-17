# Telekinex — Brain-to-Robot Control for Factory Automation

Telekinex decodes non-invasive EEG brain signals into real-time humanoid robot commands for factory task automation. An operator can steer a Unitree G1 humanoid through pick-and-place, transport, and navigation tasks using brain signals, voice commands, or manual controls — all visualized on a live web dashboard.

Built in 18 hours for the **Kernel & Dimensional VC Track** hackathon.

## Architecture

```
Browser (Vanilla JS)  ──WebSocket──>  FastAPI Backend  ──>  SimulationBridge  ──>  MuJoCo
     │                                      │
     ├── Web Speech API (STT)               ├── Voice command parser
     ├── EEG waveform canvas                ├── EEG replay / ONNX BrainDecoder
     ├── Factory floor map canvas           ├── Command fusion (voice > brain > idle)
     └── Manual control pad (Direct/BCI)    └── Gear state machine (N/F/R)
```

**Three input channels to control the robot:**
1. **Brain signals (EEG)** — 5-class ONNX classifier decodes Right Fist, Left Fist, Both Fists, Tongue Tapping, Relax into gear-dependent robot actions
2. **Voice commands** — compound natural-language instructions (e.g., "take the box from the conveyor to pallet 2") parsed into multi-step autonomous sequences
3. **Manual controls** — keyboard (WASD) or dashboard buttons, with Direct and BCI control modes

## Setup

### Prerequisites

- Python 3.10+
- EEG dataset: 900 `.npz` files in `../robot_control/data/` (not included in repo)
- (Optional) ONNX model at `training/checkpoints/best_5class.onnx` for brain decoding
- (Optional) MuJoCo for simulation
- (Optional) Node.js 18+ for frontend dev server

### Installation

```bash
git clone https://github.com/ouazmourad/ThoughtLink.git
cd ThoughtLink
pip install -r requirements.txt
```

**For training (GPU):**
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install scikit-learn matplotlib onnxruntime-gpu
```

**For simulation:**
```bash
pip install mujoco>=3.4 onnxruntime
```

### Environment Variables

Create a `.env` file in the project root (optional, for voice TTS):
```
ELEVENLABS_API_KEY=       # Required for ElevenLabs TTS. Without it, voice feedback is text-only.
ELEVENLABS_VOICE_ID=      # Optional. Defaults to "Rachel".
```

### Running

**Full app (backend + frontend on port 8000):**
```bash
PYTHONPATH="." python run.py
# Open http://localhost:8000
```

**Training pipeline:**
```bash
python -m training.data_exploration
python -m training.train_eegnet
python -m training.export_onnx
```

**Standalone simulation demo:**
```bash
python simulation/demo.py
```

## Dependencies

### Python (`requirements.txt`)

| Package | Role |
|---------|------|
| `fastapi` | REST API + WebSocket server |
| `uvicorn` | ASGI server |
| `websockets` | WebSocket protocol |
| `numpy`, `scipy` | Signal processing, array ops |
| `requests` | ElevenLabs TTS API calls |
| `python-dotenv` | Environment variable loading |

### Training (additional)

| Package | Role |
|---------|------|
| `torch` | EEGNet model training (CUDA) |
| `scikit-learn` | Baseline classifiers, metrics |
| `onnxruntime` / `onnxruntime-gpu` | ONNX inference |
| `matplotlib` | Training plots |

### Simulation (additional)

| Package | Role |
|---------|------|
| `mujoco>=3.4` | Physics engine, Unitree G1 humanoid |

### Frontend

Vanilla JS — no build step required. Served statically by the FastAPI backend.

## Dashboard Controls

### Control Modes (toggle with `M` key)

**Direct mode** — explicit commands, 9 buttons:
| Key | Action |
|-----|--------|
| W / Up | Move forward |
| S / Down | Stop |
| A / Left | Rotate left |
| D / Right | Rotate right |
| X | Move backward |
| E | Grab |
| Q | Release |
| G | Shift gear |
| Space | Both Fists (gear-dependent) |
| R | Reset |

**BCI mode** — mirrors the 5 brain signal classes, gear-dependent:
| Key | Brain Class | Action |
|-----|-------------|--------|
| A | Left Fist | Rotate left |
| D | Right Fist | Rotate right |
| W / Space | Both Fists | Forward (F gear) / Backward (R gear) / Grab-Release (N gear) |
| G | Tongue Tapping | Shift gear (N -> F -> R -> N) |
| S | Relax | Idle |

### Gear State Machine
- **Neutral (N)** — Both Fists toggles grab/release
- **Forward (F)** — Both Fists moves forward
- **Reverse (R)** — Both Fists moves backward
- Right/Left Fist always rotates regardless of gear

### Voice Commands

**Direct override (immediate):**
- `stop`, `halt`, `emergency stop`
- `move forward`, `go forward`
- `turn left`, `rotate left` / `turn right`, `rotate right`
- `grab`, `pick up` / `release`, `drop`
- `shift gear`, `set gear forward/reverse/neutral`

**Compound navigation (multi-step):**
- `walk to shelf A`, `go to the conveyor`, `navigate to pallet 2`
- `take the box from the conveyor to pallet 2` (navigate + grab + navigate + release)
- `go to shelf A and grab the box` (navigate + grab)
- `pick up the box at the table and bring it to shelf B`

### Debug Panel
- **BRAIN** toggle — enable/disable brain predictions
- **VOICE** toggle — enable/disable voice input
- **TEST EEG** — swap to synthetic EEG through the real classifier
- **FULL RESET** — reset all subsystems
- **Brain Simulator** — inject a specific brain class directly

## Project Structure

```
Telekinex/
├── run.py                # Entry point: uvicorn backend.server:app
├── constants.py          # Shared constants (all modules import from here)
├── requirements.txt      # Python dependencies
├── training/             # ML pipeline
│   ├── preprocessing.py  # EEGPreprocessor, DatasetBuilder
│   ├── model.py          # EEGNet architecture
│   ├── train_eegnet.py   # Training loop
│   ├── realtime.py       # TemporalStabilizer (vote buffer, hysteresis)
│   ├── export_onnx.py    # ONNX export
│   ├── predict.py        # BrainDecoder (public inference API)
│   └── checkpoints/      # .pt and .onnx model files
├── simulation/           # MuJoCo bridge
│   ├── bridge.py         # SimulationBridge class
│   ├── factory_controller.py  # Factory features (waypoints, pick & place, safety)
│   ├── demo.py           # Standalone closed-loop demo
│   └── scenes/           # MuJoCo XML scene files (factory_scene.xml)
├── voice/                # Voice command layer
│   ├── command_parser.py # Compound command parsing (regex templates + conjunction splitting)
│   ├── voice_input.py    # Voice command listener
│   └── tts_feedback.py   # ElevenLabs TTS with cooldown
├── backend/              # FastAPI server
│   ├── server.py         # App assembly, static file serving
│   ├── control_loop.py   # 10Hz orchestration loop + action queue
│   ├── autopilot.py      # Waypoint navigation (turn-then-walk steering)
│   ├── state_machine.py  # Gear state machine (N/F/R)
│   ├── command_fusion.py # Brain + voice merging (priority: voice > brain)
│   ├── eeg_source.py     # EEGReplaySource + TestEEGSource
│   └── api/
│       ├── routes.py     # REST endpoints
│       └── websocket.py  # WebSocket endpoint + broadcast
├── frontend/             # Vanilla JS dashboard (served by FastAPI)
│   ├── index.html        # Dashboard layout
│   ├── app.js            # WebSocket client, UI state, keyboard controls
│   ├── style.css         # Dark theme + responsive breakpoints
│   └── components/
│       ├── eeg_chart.js  # Canvas 6-channel EEG waveform
│       ├── robot_view.js # Canvas 2D factory floor map
│       └── voice_status.js # Web Speech API mic wrapper
└── docs/                 # Technical report (LaTeX + figures)
```

## API

### REST Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | State machine snapshot, sim status, client count |
| GET | `/api/metrics` | Average latency, tick count, loop rate |
| GET | `/api/server-info` | Version, host IP, port, client count |
| GET | `/api/map` | Parsed 2D factory map from MuJoCo scene XML |
| POST | `/api/reset` | Reset state machine only |
| POST | `/api/full-reset` | Full system reset |
| POST | `/api/set-gear/{gear}` | Set gear directly (NEUTRAL/FORWARD/REVERSE) |

### WebSocket (`/ws`)

**Client -> Server:**
```json
{"type": "voice_transcript", "text": "take the box from shelf A to pallet 2", "confidence": 0.95}
{"type": "manual_command", "action": "MOVE_FORWARD"}
{"type": "simulate_brain", "class_index": 0}
{"type": "toggle_brain"}
{"type": "toggle_voice"}
{"type": "toggle_test_mode"}
{"type": "full_reset"}
```

**Server -> Client:**
```json
{"type": "state_update", "gear": "FORWARD", "action": "MOVE_FORWARD", "brain_class": "Both Fists", ...}
{"type": "eeg_data", "channels": [[...], ...], "sample_rate": 50}
{"type": "command_log", "source": "voice", "action": "NAVIGATE", "target": "Shelf A", ...}
{"type": "input_toggle_update", "brain_enabled": true, "voice_enabled": true}
{"type": "full_reset_ack"}
```

## Team

| Person | Role | Owns |
|--------|------|------|
| **Joshua Law** | ML Engineer | `training/` — preprocessing, EEGNet, ONNX export, BrainDecoder |
| **Mourad Ouazghire** | Simulation Engineer | `simulation/` — MuJoCo bridge, factory scene, closed-loop demo |
| **Dmitry Fadeev** | Full-Stack Developer | `backend/` + `frontend/` + `voice/` |

## Tech Stack

- **ML:** PyTorch, EEGNet (12.6K params), ONNX Runtime
- **Simulation:** MuJoCo, Unitree G1 humanoid
- **Backend:** FastAPI, WebSocket, uvicorn
- **Voice:** ElevenLabs TTS, Web Speech API (browser STT)
- **Frontend:** Vanilla JavaScript, HTML5 Canvas
