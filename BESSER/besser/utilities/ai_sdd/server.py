"""
CC-SDD WebSocket Server — Real-time communication between the frontend
and the interactive SDD pipeline.

Runs on port 8766 (separate from the modeling agent on 8765).

Supports:
- Pipeline start with phase-by-phase execution
- Approve / iterate / reject phases
- Vibe modeling (natural language modifications)
- Manual diagram update → bidirectional traceability sync
"""

import asyncio
import json
import logging
import os
import sys

try:
    import websockets
    from websockets.server import serve as ws_serve
except ImportError:
    websockets = None

from .pipeline import SDDPipeline

logger = logging.getLogger(__name__)

# Active pipelines per WebSocket connection
_pipelines: dict[str, SDDPipeline] = {}

SDD_WS_PORT = int(os.environ.get("SDD_WS_PORT", "8766"))


async def _send_json(ws, data: dict) -> None:
    """Send a JSON message to the WebSocket client."""
    try:
        await ws.send(json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"[SDD-WS] Failed to send message: {e}")


def _make_sender(ws):
    """Create a send callback bound to a specific WebSocket connection."""
    async def sender(msg: dict) -> None:
        await _send_json(ws, msg)
    return sender


# ── Message Handlers ───────────────────────────────────────────────────

async def _handle_start_pipeline(ws, ws_id: str, msg: dict) -> None:
    """Handle start_pipeline — begin interactive SDD flow."""
    idea = msg.get("idea", "").strip()
    api_key = msg.get("apiKey", "").strip()
    output_dir = msg.get("outputDir", "").strip() or None

    if not idea:
        await _send_json(ws, {"type": "error", "message": "No idea provided."})
        return
    if not api_key:
        await _send_json(ws, {"type": "error", "message": "No API key configured."})
        return

    pipeline = SDDPipeline(api_key=api_key, send_message=_make_sender(ws), output_dir=output_dir)
    _pipelines[ws_id] = pipeline

    try:
        await pipeline.start_pipeline(idea)
    except Exception as e:
        logger.error(f"[SDD-WS] Pipeline start failed: {e}", exc_info=True)
        await _send_json(ws, {"type": "error", "message": f"Pipeline failed: {e}"})


async def _handle_user_message(ws, ws_id: str, msg: dict) -> None:
    """Handle user_message — the pipeline agent decides what to do."""
    pipeline = _pipelines.get(ws_id)
    if not pipeline:
        await _send_json(ws, {"type": "error", "message": "No active project."})
        return

    message = msg.get("message", "").strip()
    if not message:
        await _send_json(ws, {"type": "error", "message": "No message provided."})
        return

    try:
        await pipeline.handle_user_message(message)
    except Exception as e:
        logger.error(f"[SDD-WS] User message failed: {e}", exc_info=True)
        await _send_json(ws, {"type": "error", "message": f"Error: {e}"})


async def _handle_diagram_update(ws, ws_id: str, msg: dict) -> None:
    """Handle update_diagram — manual diagram changes from the canvas."""
    pipeline = _pipelines.get(ws_id)
    if not pipeline:
        await _send_json(ws, {"type": "error", "message": "No active project."})
        return

    canvas_json = msg.get("canvasJson")
    if not canvas_json:
        await _send_json(ws, {"type": "error", "message": "No diagram data provided."})
        return

    try:
        await pipeline.handle_diagram_update(canvas_json)
    except Exception as e:
        logger.error(f"[SDD-WS] Diagram update failed: {e}", exc_info=True)
        await _send_json(ws, {"type": "error", "message": f"Diagram sync failed: {e}"})


# ── WebSocket Handler ──────────────────────────────────────────────────

_MESSAGE_HANDLERS = {
    "start_pipeline": _handle_start_pipeline,
    "vibe_message": _handle_user_message,       # All user messages → agent router
    "user_message": _handle_user_message,        # Alias
    "update_diagram": _handle_diagram_update,
}


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
                await _send_json(ws, {"type": "error", "message": "Invalid JSON."})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await _send_json(ws, {"type": "pong"})
                continue

            handler = _MESSAGE_HANDLERS.get(msg_type)
            if handler:
                asyncio.create_task(handler(ws, ws_id, msg))
            else:
                await _send_json(ws, {
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except Exception as e:
        logger.info(f"[SDD-WS] Client disconnected: {ws_id} ({e})")
    finally:
        _pipelines.pop(ws_id, None)
        logger.info(f"[SDD-WS] Session cleaned up: {ws_id}")


# ── Server Entry ───────────────────────────────────────────────────────

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
