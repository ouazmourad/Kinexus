"""REST API routes for ThoughtLink."""

import socket

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config import PORT
from ..state_machine import Gear
from ..scene_parser import get_default_map

router = APIRouter()

# Module-level reference to ControlLoop — set by server.py during setup
_control_loop = None

# Module-level reference to connected_clients list
_connected_clients = None


def set_control_loop(loop) -> None:
    """Called once at startup to wire the control loop into the route handlers."""
    global _control_loop
    _control_loop = loop


def set_connected_clients(clients) -> None:
    """Called once at startup to give routes access to the client list."""
    global _connected_clients
    _connected_clients = clients


@router.get("/api/status")
async def get_status():
    return JSONResponse({
        "state": _control_loop.state_machine.get_state_snapshot(),
        "sim_running": _control_loop.sim.is_running(),
        "clients_connected": len(_connected_clients),
        "tick_count": _control_loop.tick_count,
    })


@router.post("/api/reset")
async def reset_state():
    _control_loop.state_machine.reset()
    return JSONResponse({"status": "ok", "message": "State machine reset"})


@router.post("/api/full-reset")
async def full_reset():
    _control_loop.full_reset()
    return JSONResponse({"status": "ok", "message": "Full system reset"})


@router.post("/api/set-gear/{gear}")
async def set_gear(gear: str):
    try:
        g = Gear(gear.upper())
        _control_loop.state_machine.set_gear(g)
        return JSONResponse({"status": "ok", "gear": g.value})
    except ValueError:
        return JSONResponse({"status": "error", "message": f"Invalid gear: {gear}"}, status_code=400)


@router.get("/api/metrics")
async def get_metrics():
    return JSONResponse(_control_loop.get_metrics())


def _get_local_ip() -> str:
    """Get the local network IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostbyname(socket.gethostname())


@router.get("/api/server-info")
async def get_server_info():
    return JSONResponse({
        "version": "0.1",
        "host": _get_local_ip(),
        "port": PORT,
        "clients_connected": len(_connected_clients),
    })


@router.get("/api/map")
async def get_map():
    """Return parsed 2D map data from the MuJoCo scene XML."""
    return JSONResponse(get_default_map())
