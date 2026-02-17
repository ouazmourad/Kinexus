"""WebSocket endpoint — connection management + real-time protocol."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# Connected WebSocket clients
connected_clients: list[WebSocket] = []

# Module-level reference to ControlLoop — set by server.py during setup
_control_loop = None


def set_control_loop(loop) -> None:
    """Called once at startup to wire the control loop into the WS handler."""
    global _control_loop
    _control_loop = loop


async def broadcast(message: dict) -> None:
    """Send a message to all connected frontend clients."""
    text = json.dumps(message, default=str)
    disconnected = []
    for client in connected_clients:
        try:
            await client.send_text(text)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        if client in connected_clients:
            connected_clients.remove(client)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"[Server] Client connected ({len(connected_clients)} total)")

    # Send initial state
    sm = _control_loop.state_machine
    await websocket.send_text(json.dumps({
        "type": "state_update",
        "gear": sm.state.gear.value,
        "action": "IDLE",
        "action_source": "idle",
        "brain_class": None,
        "brain_confidence": 0,
        "brain_gated": True,
        "holding_item": sm.state.holding_item,
        "robot_state": _control_loop.sim.get_state(),
        "latency_ms": 0,
        "timestamp": time.time(),
        "toggled_action": None,
        "selected_robot": _control_loop.robot_manager.selected_robot.id,
        "robots": _control_loop.robot_manager.get_all_states(),
        "orchestration": sm.get_orchestration_state(),
    }))

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await _handle_client_message(message, websocket)
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        print(f"[Server] Client disconnected ({len(connected_clients)} total)")
    except Exception as e:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        print(f"[Server] WebSocket error: {e}")


async def _handle_client_message(message: dict, websocket: WebSocket):
    """Handle incoming messages from frontend clients."""
    msg_type = message.get("type", "")

    if msg_type == "voice_transcript":
        text = message.get("text", "")
        confidence = message.get("confidence", 1.0)
        if text:
            await _control_loop.push_voice_command(text, confidence)
            await broadcast({
                "type": "command_log",
                "source": "voice",
                "text": text,
                "action": "VOICE_INPUT",
                "timestamp": time.time(),
            })

    elif msg_type == "manual_command":
        action = message.get("action", "")
        if action:
            await _control_loop.push_manual_command(action)
            await broadcast({
                "type": "command_log",
                "source": "manual",
                "action": action,
                "timestamp": time.time(),
            })

    elif msg_type == "reset":
        _control_loop.state_machine.reset()
        await broadcast({
            "type": "state_update",
            "gear": "NEUTRAL",
            "action": "IDLE",
            "action_source": "idle",
            "brain_class": None,
            "brain_confidence": 0,
            "brain_gated": True,
            "holding_item": False,
            "robot_state": _control_loop.sim.get_state(),
            "latency_ms": 0,
            "timestamp": time.time(),
            "toggled_action": None,
            "selected_robot": _control_loop.robot_manager.selected_robot.id,
            "robots": _control_loop.robot_manager.get_all_states(),
            "orchestration": None,
        })

    elif msg_type == "toggle_test_mode":
        _control_loop.set_test_mode(not _control_loop._test_mode)
        await broadcast({
            "type": "test_mode_update",
            "enabled": _control_loop._test_mode,
            "timestamp": time.time(),
        })

    elif msg_type == "toggle_brain":
        _control_loop.brain_enabled = not _control_loop.brain_enabled
        await broadcast({
            "type": "input_toggle_update",
            "brain_enabled": _control_loop.brain_enabled,
            "voice_enabled": _control_loop.voice_enabled,
            "timestamp": time.time(),
        })

    elif msg_type == "toggle_voice":
        _control_loop.voice_enabled = not _control_loop.voice_enabled
        await broadcast({
            "type": "input_toggle_update",
            "brain_enabled": _control_loop.brain_enabled,
            "voice_enabled": _control_loop.voice_enabled,
            "timestamp": time.time(),
        })

    elif msg_type == "full_reset":
        _control_loop.full_reset()
        await broadcast({
            "type": "full_reset_ack",
            "timestamp": time.time(),
        })
        await broadcast({
            "type": "state_update",
            "gear": "NEUTRAL",
            "action": "IDLE",
            "action_source": "idle",
            "brain_class": None,
            "brain_confidence": 0,
            "brain_gated": True,
            "holding_item": False,
            "robot_state": _control_loop.sim.get_state(),
            "latency_ms": 0,
            "timestamp": time.time(),
            "toggled_action": None,
            "selected_robot": _control_loop.robot_manager.selected_robot.id,
            "robots": _control_loop.robot_manager.get_all_states(),
            "orchestration": None,
        })

    elif msg_type == "sim_brain_start":
        # Press-and-hold: mousedown starts simulation
        class_index = message.get("class_index")
        _control_loop.set_sim_brain(class_index)
        await broadcast({
            "type": "sim_brain_update",
            "class_index": _control_loop._sim_brain_class,
            "timestamp": time.time(),
        })

    elif msg_type == "sim_brain_stop":
        # Press-and-hold: mouseup stops simulation
        _control_loop.set_sim_brain(None)
        await broadcast({
            "type": "sim_brain_update",
            "class_index": None,
            "timestamp": time.time(),
        })

    elif msg_type == "simulate_brain":
        # Legacy toggle-style (backward compat)
        class_index = message.get("class_index")
        _control_loop.set_sim_brain(class_index)
        await broadcast({
            "type": "sim_brain_update",
            "class_index": _control_loop._sim_brain_class,
            "timestamp": time.time(),
        })

    elif msg_type == "toggle_eeg_stream":
        _control_loop.eeg_stream_enabled = not _control_loop.eeg_stream_enabled
        await broadcast({
            "type": "eeg_stream_update",
            "enabled": _control_loop.eeg_stream_enabled,
            "timestamp": time.time(),
        })

    elif msg_type == "select_robot":
        robot_id = message.get("robot_id", "")
        if robot_id:
            _control_loop.robot_manager.select_by_id(robot_id)
            await broadcast({
                "type": "robot_selected",
                "robot_id": _control_loop.robot_manager.selected_robot.id,
                "timestamp": time.time(),
            })

    elif msg_type == "cancel_nav":
        _control_loop.cancel_nav()
        await broadcast({
            "type": "nav_update",
            "active": False,
            "target_name": None,
            "target_x": 0,
            "target_y": 0,
            "distance": 0,
            "arrived": False,
        })

    elif msg_type == "set_gear":
        from backend.state_machine import Gear
        gear_str = message.get("gear", "NEUTRAL")
        try:
            gear = Gear(gear_str)
            _control_loop.state_machine.set_gear(gear)
        except ValueError:
            pass
