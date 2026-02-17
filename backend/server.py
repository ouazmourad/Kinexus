"""ThoughtLink Backend Server — FastAPI app assembly."""

import asyncio
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api.websocket import router as ws_router, broadcast, set_control_loop as ws_set_loop, connected_clients
from .api.routes import router as api_router, set_control_loop as routes_set_loop, set_connected_clients
from .control_loop import ControlLoop

app = FastAPI(title="ThoughtLink", version="1.0.0")

# Wire up routers
app.include_router(ws_router)
app.include_router(api_router)

# Create control loop with broadcast callback
control_loop = ControlLoop(broadcast_fn=broadcast)

# Give routers access to the control loop and client list
ws_set_loop(control_loop)
routes_set_loop(control_loop)
set_connected_clients(connected_clients)

# --- Static Files ---

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


# Serve simulation scene files so frontend can parse the XML directly
scenes_dir = os.path.join(os.path.dirname(__file__), "..", "simulation", "scenes")
if os.path.exists(scenes_dir):
    app.mount("/scenes", StaticFiles(directory=scenes_dir), name="scenes")

# Mount static files after routes so API routes take priority
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir), name="frontend")


# --- Startup ---

@app.on_event("startup")
async def start_control_loop():
    asyncio.create_task(control_loop.run())
    print("[Server] Control loop started")
