"""
OpenClaw Bridge - FastAPI server that bridges Omi to local OpenClaw.

This service runs on the user's local machine and:
1. Receives tool invocation requests from the Omi OpenClaw App
2. Verifies the request token
3. Forwards the request to local OpenClaw via WebSocket
4. Returns the response (or acknowledgment for long-running tasks)

Long-running task handling:
- If OpenClaw responds within the quick timeout, returns result directly
- If timeout passes with no response, returns acknowledgment and
  continues in background, then calls the callback_url with the result

Embedded agent handling:
- After returning the initial response, a follow-up listener stays active
- If OpenClaw's embedded agents produce additional results (posted back
  to the same session), they are sent via callback_url

Usage:
    python -m bridge

    Or with uvicorn:
    uvicorn bridge.main:app --host 0.0.0.0 --port 8081
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Set

import httpx
from dotenv import load_dotenv

load_dotenv()  # Load .env file before importing config

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Connected WebSocket clients for live streaming
ws_clients: Set[WebSocket] = set()


async def broadcast(msg: dict):
    """Broadcast a message to all connected WebSocket clients."""
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)

from .config import BRIDGE_HOST, BRIDGE_PORT, OMI_SECRET_TOKEN, QUICK_RESPONSE_TIMEOUT
from .openclaw_client import openclaw_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="OpenClaw Bridge",
    description="Bridge service connecting Omi to local OpenClaw AI assistant",
    version="1.0.0",
)

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ToolRequest(BaseModel):
    """Request model for tool invocation."""

    request: str
    uid: str
    callback_url: Optional[str] = None


class ToolResponse(BaseModel):
    """Response model for tool invocation."""

    result: str
    is_background: bool = False


def verify_token(token: str) -> bool:
    """
    Verify the token from the Omi OpenClaw App.

    Args:
        token: The X-Omi-Token header value

    Returns:
        True if token is valid, False otherwise
    """
    if not OMI_SECRET_TOKEN:
        # No token configured - skip verification (development mode)
        logger.warning("OMI_SECRET_TOKEN not set - skipping token verification (NOT SECURE)")
        return True

    if not token:
        return False

    # Constant-time comparison to prevent timing attacks
    return len(token) == len(OMI_SECRET_TOKEN) and all(a == b for a, b in zip(token, OMI_SECRET_TOKEN))


async def send_callback(callback_url: str, uid: str, result: str, x_omi_token: str):
    """
    Send the result to the callback URL when a background task completes.

    Args:
        callback_url: The URL to POST the result to
        uid: The user ID
        result: The result from OpenClaw
        x_omi_token: Token to include in callback for verification
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                callback_url,
                json={"uid": uid, "result": result},
                headers={"X-Omi-Token": x_omi_token or ""},
            )
            logger.info(f"Callback sent, status: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to send callback: {e}")


async def background_task_handler(continuation_task: asyncio.Task, callback_url: str, uid: str, x_omi_token: str):
    """
    Handle a background task - wait for it to complete and send callback.

    Args:
        continuation_task: The task waiting for OpenClaw response
        callback_url: URL to call with the result
        uid: User ID
        x_omi_token: Token for callback verification
    """
    try:
        result = await continuation_task
        logger.info(f"Background task completed for user {uid}")
        await send_callback(callback_url, uid, result, x_omi_token)
    except Exception as e:
        logger.error(f"Background task failed for user {uid}: {e}")
        await send_callback(callback_url, uid, f"Error: {str(e)}", x_omi_token)


@app.post("/tools/ask", response_model=ToolResponse)
async def ask_openclaw(
    data: ToolRequest,
    x_omi_token: str = Header(None, alias="X-Omi-Token"),
):
    """
    Main tool endpoint - receives requests from Omi OpenClaw App and forwards to OpenClaw.

    Long-running task handling:
    - If OpenClaw responds within QUICK_RESPONSE_TIMEOUT, returns result directly
    - If timeout with no response, returns acknowledgment with is_background=True
    - Background task continues and calls callback_url when complete

    Embedded agent handling:
    - After returning the initial response, a follow-up listener catches
      additional results from OpenClaw's embedded agents
    - Those results are sent via callback_url
    """
    # Verify token
    if not verify_token(x_omi_token):
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    # Detect pipeline trigger keywords
    trigger_keywords = ["start", "run pipeline", "analyze", "process", "execute task"]
    if any(keyword in data.request.lower() for keyword in trigger_keywords):
        logger.info(f"Detected pipeline trigger: {data.request}")

        # Get orchestrator URL
        orchestrator_url = os.getenv("ORCHESTRATOR_URL", "http://localhost:8080")

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Trigger main orchestrator pipeline
                response = await client.post(
                    f"{orchestrator_url}/api/pipeline",
                    json={"task": data.request}
                )

                if response.status_code == 200:
                    pipeline_result = response.json()
                    final_answer = pipeline_result.get("final_answer", "No response")

                    # Broadcast to dashboard
                    await broadcast({
                        "type": "pipeline",
                        "result": final_answer,
                        "ts": datetime.now().strftime("%H:%M:%S"),
                        "agents": pipeline_result.get("agents", [])
                    })

                    # Send callback to Omi if provided
                    if data.callback_url:
                        await send_callback(data.callback_url, data.uid, final_answer, x_omi_token)
                        return ToolResponse(result="Pipeline complete, result sent.", is_background=False)
                    else:
                        return ToolResponse(result=final_answer, is_background=False)
                else:
                    error_msg = f"Pipeline failed: {response.status_code}"
                    logger.error(error_msg)
                    return ToolResponse(result=error_msg, is_background=False)

        except Exception as e:
            logger.error(f"Pipeline trigger failed: {e}")
            return ToolResponse(result=f"Error: {str(e)}", is_background=False)

    # If not a pipeline trigger, proceed with normal OpenClaw forwarding
    # Create follow-up callback for embedded agent results
    followup_callback = None
    if data.callback_url:

        async def followup_callback(result: str):
            logger.info(f"Sending follow-up result for user {data.uid}")
            await send_callback(data.callback_url, data.uid, result, x_omi_token)

    try:
        # Forward request to OpenClaw with quick timeout support
        result, continuation_task = await openclaw_client.send_message_with_quick_timeout(
            data.request,
            followup_callback=followup_callback,
        )

        if result is not None:
            # Got response within quick timeout
            await broadcast({"type": "agent", "text": result, "ts": datetime.now().strftime("%H:%M:%S")})
            return ToolResponse(result=result, is_background=False)
        else:
            # Quick timeout expired, task is running in background
            if continuation_task and data.callback_url:
                # Spawn background handler to wait for result and send callback
                asyncio.create_task(
                    background_task_handler(continuation_task, data.callback_url, data.uid, x_omi_token)
                )
                return ToolResponse(
                    result="OpenClaw is working on this task and will send the result directly when complete. No further action needed.",
                    is_background=True,
                )
            elif continuation_task:
                # No callback URL provided, wait for the full result (blocks)
                result = await continuation_task
                return ToolResponse(result=result, is_background=False)
            else:
                return ToolResponse(result="Error: No response from OpenClaw", is_background=False)

    except Exception as e:
        return ToolResponse(result=f"Error: {str(e)}", is_background=False)


class TranscriptSegment(BaseModel):
    text: Optional[str] = None
    transcript: Optional[str] = None
    segments: Optional[list] = None


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint — push live transcript + agent events to UI."""
    await websocket.accept()
    ws_clients.add(websocket)
    logger.info(f"WebSocket client connected ({len(ws_clients)} total)")
    try:
        while True:
            await websocket.receive_text()  # keep-alive ping handling
    except WebSocketDisconnect:
        ws_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected ({len(ws_clients)} remaining)")


@app.post("/transcript")
async def receive_transcript(request: Request):
    """Live transcript webhook — prints and broadcasts Omi transcript chunks."""
    try:
        data = await request.json()
    except Exception:
        raw = await request.body()
        data = {"raw": raw.decode()}

    ts = datetime.now().strftime("%H:%M:%S")

    # Extract text from Omi segment format
    text = ""
    if "segments" in data and isinstance(data["segments"], list):
        text = " ".join(s.get("text", "") for s in data["segments"] if s.get("text"))
    if not text:
        text = data.get("text") or data.get("transcript") or str(data)

    text = text.strip()
    logger.info(f"[TRANSCRIPT {ts}] 🎙️  {text}")
    print(f"\n[{ts}] 🎙️  {text}", flush=True)
    await broadcast({"type": "transcript", "text": text, "ts": ts})
    return {"status": "ok"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    openclaw_ok = await openclaw_client.health_check()
    token_configured = bool(OMI_SECRET_TOKEN)
    return {
        "status": "ok",
        "service": "openclaw-bridge",
        "openclaw_connected": openclaw_ok,
        "token_configured": token_configured,
    }


@app.get("/api/nemoclaw-status")
async def nemoclaw_status():
    """Poll each Brev instance's /api/status endpoint and return live health."""
    nodes = [
        {"name": "nemoclaw-1", "url": "https://reveal-woods-jill-yamaha.trycloudflare.com"},
        {"name": "nemoclaw-2", "url": "https://recording-acer-what-hereby.trycloudflare.com"},
    ]
    results = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for node in nodes:
            try:
                r = await client.get(f"{node['url']}/api/status")
                data = r.json()
                results.append({
                    "name": node["name"],
                    "status": "online",
                    "detail": {
                        "instance_name": data.get("instance_name"),
                        "pipeline_count": data.get("pipeline_count", 0),
                        "agents": list(data.get("agents", {}).keys()),
                    }
                })
            except Exception as e:
                results.append({"name": node["name"], "status": "offline", "error": str(e)})
    return {"nodes": results, "checked_at": datetime.utcnow().isoformat() + "Z"}


@app.get("/api/nodes")
async def get_nodes():
    """Return known agent nodes for auto-registration in the swarm UI."""
    return {"nodes": [
        {"name": "nemoclaw-1", "url": "https://reveal-woods-jill-yamaha.trycloudflare.com", "role": "slave", "ttydUrl": "https://broken-partly-principles-nicole.trycloudflare.com"},
        {"name": "nemoclaw-2", "url": "https://recording-acer-what-hereby.trycloudflare.com", "role": "slave", "ttydUrl": "https://extra-milan-types-dependent.trycloudflare.com"},
        {"name": "nemoclaw-joe", "url": "https://administrators-trading-like-shanghai.trycloudflare.com", "role": "slave", "ttydUrl": "https://correctly-rock-produces-accessory.trycloudflare.com"},
    ]}


@app.get("/api/brev/list")
async def list_brev_instances():
    """List all Brev instances by parsing `brev ls` output."""
    import subprocess
    try:
        result = subprocess.run(
            ["brev", "ls"],
            capture_output=True, text=True, timeout=30
        )
        # Parse the text table output into structured data
        lines = result.stdout.strip().split('\n')
        instances = []
        for line in lines[2:]:  # skip header rows
            parts = line.split()
            if len(parts) >= 6:
                instances.append({
                    "name": parts[0],
                    "status": parts[1],
                    "build": parts[2],
                    "shell": parts[3],
                    "id": parts[4],
                    "machine": parts[5],
                    "ready": parts[3] == "READY" and parts[1] == "RUNNING"
                })
        return {"instances": instances}
    except Exception as e:
        return {"instances": [], "error": str(e)}


@app.post("/api/brev/connect")
async def connect_brev_instance(request: Request):
    """Start a cloudflared tunnel on a Brev instance and return the public URL."""
    import asyncio
    data = await request.json()
    name = data.get("instanceName", "").strip()
    if not name:
        return {"error": "instanceName required"}

    # Start cloudflared tunnel
    proc = await asyncio.create_subprocess_exec(
        "brev", "exec", name,
        "nohup /tmp/cloudflared tunnel --url http://localhost:8080 --no-autoupdate > /tmp/cf-8080.log 2>&1 &",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()

    # Wait and get URL
    await asyncio.sleep(8)
    url_proc = await asyncio.create_subprocess_exec(
        "brev", "exec", name,
        "grep -o 'https://[a-z0-9-]*.trycloudflare.com' /tmp/cf-8080.log | head -1",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await url_proc.communicate()
    url = stdout.decode().strip().split('\n')[0].strip()

    if url and url.startswith('https://'):
        return {"url": url, "instanceName": name}
    return {"error": "Could not get tunnel URL", "instanceName": name}


@app.post("/api/deploy")
async def deploy_app(request: Request):
    """Deploy a v0 app from a prompt — proxies to nemoclaw-1."""
    data = await request.json()
    task = data.get("task", data.get("prompt", ""))
    if not task:
        return {"error": "task required"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.post(
                "https://reveal-woods-jill-yamaha.trycloudflare.com/api/deploy",
                json={"task": task}
            )
            return r.json()
        except Exception as e:
            return {"error": str(e), "success": False}


@app.get("/")
async def root():
    """Serve the 4-panel demo UI."""
    import os
    ui_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui.html")
    try:
        with open(ui_path) as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        token_configured = bool(OMI_SECRET_TOKEN)
        return {
            "service": "OpenClaw Bridge",
            "version": "1.0.0",
            "endpoints": {"/tools/ask": "POST", "/health": "GET", "/ws": "WebSocket", "/transcript": "POST"},
        }


@app.on_event("startup")
async def startup_event():
    """Connect to OpenClaw on startup for persistent connection."""
    try:
        await openclaw_client.connect()
    except Exception as e:
        logger.warning(f"Could not connect to OpenClaw on startup: {e} (will retry on first request)")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    await openclaw_client.disconnect()


def main():
    """Run the bridge server."""
    import uvicorn

    logger.info(f"Starting OpenClaw Bridge on {BRIDGE_HOST}:{BRIDGE_PORT}")
    logger.info("Make sure OpenClaw is running at ws://127.0.0.1:18789")

    if not OMI_SECRET_TOKEN:
        logger.warning("=" * 60)
        logger.warning("WARNING: OMI_SECRET_TOKEN is not set!")
        logger.warning("Set it to the token shown when you configured the Omi app.")
        logger.warning("Without it, anyone can send requests to this bridge.")
        logger.warning("=" * 60)
    else:
        logger.info("Token verification enabled")

    logger.info("Expose this server via ngrok: ngrok http 8081")

    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT)


if __name__ == "__main__":
    main()
