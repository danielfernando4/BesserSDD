"""
CC-SDD WebSocket Server — Real-time communication between the frontend
and the SDD pipeline agents.

Runs on port 8766 (separate from the modeling agent on 8765).
Handles pipeline execution, vibe modeling, and file updates via WebSocket.
"""

import asyncio
import json
import logging
import os
import sys

# Ensure the BESSER package is importable
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import websockets
    from websockets.server import serve as ws_serve
except ImportError:
    # Fallback: try asyncio-based websockets
    websockets = None

from besser.utilities.ai_sdd.pipeline import SDDPipeline, SDDProject

logger = logging.getLogger(__name__)

# Active sessions: ws_id -> SDDProject
_sessions: dict[str, SDDProject] = {}
_pipelines: dict[str, SDDPipeline] = {}

SDD_WS_PORT = int(os.environ.get("SDD_WS_PORT", "8766"))


async def _send_json(ws, data: dict) -> None:
    """Send a JSON message to the WebSocket client."""
    try:
        await ws.send(json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"[SDD-WS] Failed to send message: {e}")


async def _handle_start_pipeline(ws, ws_id: str, msg: dict) -> None:
    """Handle a start_pipeline message — run the full SDD pipeline."""
    idea = msg.get("idea", "").strip()
    api_key = msg.get("apiKey", "").strip()

    if not idea:
        await _send_json(ws, {"type": "error", "message": "No idea provided.", "phase": ""})
        return

    if not api_key:
        await _send_json(ws, {"type": "error", "message": "No API key configured.", "phase": ""})
        return

    # Create pipeline and project
    pipeline = SDDPipeline(api_key)
    _pipelines[ws_id] = pipeline

    # Define async callbacks that forward events to the WebSocket client
    async def on_status(phase: str, status: str, message: str):
        await _send_json(ws, {
            "type": "pipeline_status",
            "phase": phase,
            "status": status,
            "message": message,
        })

    async def on_file(filename: str, content: str):
        await _send_json(ws, {
            "type": "file_update",
            "filename": filename,
            "content": content,
        })

    async def on_canvas(canvas_json: dict):
        await _send_json(ws, {
            "type": "canvas_update",
            "canvasJson": canvas_json,
        })

    async def on_message(phase: str, message: str):
        await _send_json(ws, {
            "type": "agent_message",
            "phase": phase,
            "message": message,
        })

    try:
        project = await pipeline.run_pipeline(
            idea=idea,
            on_status=on_status,
            on_file=on_file,
            on_canvas=on_canvas,
            on_message=on_message,
        )
        _sessions[ws_id] = project

        await _send_json(ws, {
            "type": "pipeline_complete",
            "projectName": project.name,
            "files": list(project.get_files().keys()),
        })

    except Exception as e:
        logger.error(f"[SDD-WS] Pipeline failed: {e}", exc_info=True)
        await _send_json(ws, {
            "type": "error",
            "message": f"Pipeline failed: {str(e)}",
            "phase": "pipeline",
        })


async def _handle_vibe_message(ws, ws_id: str, msg: dict) -> None:
    """Handle a vibe_message — modify the project via natural language."""
    instruction = msg.get("message", "").strip()

    if not instruction:
        await _send_json(ws, {"type": "error", "message": "No instruction provided.", "phase": "vibe"})
        return

    project = _sessions.get(ws_id)
    pipeline = _pipelines.get(ws_id)

    if not project or not pipeline:
        await _send_json(ws, {
            "type": "error",
            "message": "No active project. Please run the pipeline first.",
            "phase": "vibe",
        })
        return

    async def on_file(filename: str, content: str):
        await _send_json(ws, {"type": "file_update", "filename": filename, "content": content})

    async def on_canvas(canvas_json: dict):
        await _send_json(ws, {"type": "canvas_update", "canvasJson": canvas_json})

    async def on_message(phase: str, message: str):
        await _send_json(ws, {"type": "agent_message", "phase": phase, "message": message})

    await pipeline.handle_vibe_message(
        project=project,
        instruction=instruction,
        on_file=on_file,
        on_canvas=on_canvas,
        on_message=on_message,
    )


async def _handle_get_file(ws, ws_id: str, msg: dict) -> None:
    """Handle a get_file request — return a specific file's content."""
    filename = msg.get("filename", "")
    project = _sessions.get(ws_id)

    if not project:
        await _send_json(ws, {"type": "error", "message": "No active project.", "phase": ""})
        return

    files = project.get_files()
    content = files.get(filename, "")

    await _send_json(ws, {
        "type": "file_content",
        "filename": filename,
        "content": content,
    })


async def _handler(ws) -> None:
    """Main WebSocket handler for each connected client."""
    ws_id = str(id(ws))
    logger.info(f"[SDD-WS] Client connected: {ws_id}")

    await _send_json(ws, {
        "type": "connected",
        "message": "Connected to CC-SDD server.",
    })

    try:
        async for raw_message in ws:
            try:
                msg = json.loads(raw_message)
            except json.JSONDecodeError:
                await _send_json(ws, {"type": "error", "message": "Invalid JSON.", "phase": ""})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "start_pipeline":
                # Run pipeline in a task so we don't block the WS reader
                asyncio.create_task(_handle_start_pipeline(ws, ws_id, msg))

            elif msg_type == "vibe_message":
                asyncio.create_task(_handle_vibe_message(ws, ws_id, msg))

            elif msg_type == "get_file":
                await _handle_get_file(ws, ws_id, msg)

            elif msg_type == "ping":
                await _send_json(ws, {"type": "pong"})

            else:
                await _send_json(ws, {
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                    "phase": "",
                })

    except Exception as e:
        logger.info(f"[SDD-WS] Client disconnected: {ws_id} ({e})")
    finally:
        # Clean up session on disconnect
        _sessions.pop(ws_id, None)
        _pipelines.pop(ws_id, None)
        logger.info(f"[SDD-WS] Session cleaned up: {ws_id}")


async def _main():
    """Start the SDD WebSocket server."""
    if websockets is None:
        logger.error("[SDD-WS] 'websockets' package not installed. Run: pip install websockets")
        return

    logger.info(f"[SDD-WS] Starting CC-SDD WebSocket server on port {SDD_WS_PORT}...")
    async with ws_serve(_handler, "0.0.0.0", SDD_WS_PORT):
        logger.info(f"[SDD-WS] CC-SDD server running on ws://0.0.0.0:{SDD_WS_PORT}")
        await asyncio.Future()  # Run forever


def start_server():
    """Entry point for starting the SDD WebSocket server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(_main())


if __name__ == "__main__":
    start_server()
