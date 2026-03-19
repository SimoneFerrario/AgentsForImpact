#!/usr/bin/env python3
"""
NemoClaw Executor Node Server
Lightweight FastAPI server for distributed agent execution with load-based routing.

Runs on Brev instances and registers with main orchestrator.
"""

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment
load_dotenv("/root/.nemoclaw.env")

# Config
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8080")
NODE_ID = os.getenv("NODE_ID", str(uuid.uuid4())[:8])
NODE_NAME = os.getenv("NODE_NAME", socket.gethostname())
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
PORT = int(os.getenv("PORT", 9000))
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
EXECUTOR_MODEL = "nvidia/nemotron-3-super-120b-a12b"

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="NemoClaw Executor Node", version="1.0.0")

# Load metrics
ACTIVE_REQUESTS = 0
LATENCY_HISTORY = deque(maxlen=20)  # Keep last 20 latencies
REQUEST_QUEUE: asyncio.Queue = None  # Will be initialized in startup


class ExecuteRequest(BaseModel):
    """Request to execute an agent task."""
    task: str
    context: dict = {}


class ExecuteResponse(BaseModel):
    """Response from task execution."""
    result: str
    latency_ms: int
    model: str
    node_id: str


class HealthResponse(BaseModel):
    """Health and load metrics."""
    status: str
    node_id: str
    node_name: str
    active_requests: int
    queue_depth: int
    avg_latency_ms: float
    load_score: float


def calculate_load_score() -> float:
    """
    Calculate load score (lower is better).
    Formula: (queue_depth * 0.5) + (active_requests * 0.3) + (avg_latency_ms / 1000 * 0.2)
    """
    queue_depth = REQUEST_QUEUE.qsize() if REQUEST_QUEUE else 0
    avg_latency = sum(LATENCY_HISTORY) / len(LATENCY_HISTORY) if LATENCY_HISTORY else 0

    score = (queue_depth * 0.5) + (ACTIVE_REQUESTS * 0.3) + (avg_latency / 1000 * 0.2)
    return round(score, 3)


async def call_nvidia_executor(task: str, context: dict) -> str:
    """Call NVIDIA Nemotron API to execute the task."""
    model = context.get("model", EXECUTOR_MODEL)
    temperature = context.get("temperature", 0.7)
    max_tokens = context.get("max_tokens", 800)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an Executor agent. Given context and strategy, produce a comprehensive final response."},
            {"role": "user", "content": task}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 0.95,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": max_tokens
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {NVIDIA_API_KEY}"
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{NVIDIA_BASE}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()

            body = response.json()
            msg = body.get("choices", [{}])[0].get("message", {})
            content = (msg.get("content") or msg.get("reasoning_content") or "").strip()

            # Strip <think> tags if present
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

            return content

    except Exception as e:
        logger.error(f"NVIDIA API call failed: {e}")
        raise HTTPException(status_code=500, detail=f"Executor failed: {str(e)}")


async def worker():
    """Process queued executor tasks."""
    global ACTIVE_REQUESTS

    logger.info(f"Worker started for node {NODE_ID}")

    while True:
        task_data, future = await REQUEST_QUEUE.get()
        ACTIVE_REQUESTS += 1

        try:
            t0 = time.time()
            result = await call_nvidia_executor(task_data["task"], task_data["context"])
            latency = round((time.time() - t0) * 1000)

            LATENCY_HISTORY.append(latency)

            logger.info(f"Task completed in {latency}ms | Queue: {REQUEST_QUEUE.qsize()}")

            future.set_result({
                "result": result,
                "latency_ms": latency,
                "model": EXECUTOR_MODEL,
                "node_id": NODE_ID
            })

        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            future.set_exception(e)

        finally:
            ACTIVE_REQUESTS -= 1


async def heartbeat_loop():
    """Send periodic heartbeat to orchestrator."""
    logger.info(f"Heartbeat loop started for node {NODE_ID}")

    # Initial registration
    await register_with_orchestrator()

    # Periodic heartbeat
    while True:
        try:
            await asyncio.sleep(10)

            metrics = {
                "active_requests": ACTIVE_REQUESTS,
                "queue_depth": REQUEST_QUEUE.qsize(),
                "avg_latency_ms": sum(LATENCY_HISTORY) / len(LATENCY_HISTORY) if LATENCY_HISTORY else 0,
                "load_score": calculate_load_score()
            }

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{ORCHESTRATOR_URL}/api/nodes/heartbeat",
                    json={
                        "id": NODE_ID,
                        "metrics": metrics,
                        "status": "online"
                    }
                )

                if response.status_code == 200:
                    logger.debug(f"Heartbeat sent | Load: {metrics['load_score']:.2f}")
                else:
                    logger.warning(f"Heartbeat failed: {response.status_code}")

        except Exception as e:
            logger.error(f"Heartbeat error: {e}")


async def register_with_orchestrator():
    """Register this node with the orchestrator."""
    # Get local IP or hostname
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        node_url = f"http://{local_ip}:{PORT}"
    except:
        node_url = f"http://{NODE_NAME}:{PORT}"

    registration = {
        "id": NODE_ID,
        "name": NODE_NAME,
        "url": node_url,
        "role": "executor",
        "status": "online",
        "agents": ["executor"],
        "metrics": {
            "active_requests": 0,
            "queue_depth": 0,
            "avg_latency_ms": 0,
            "load_score": 0.0
        }
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{ORCHESTRATOR_URL}/api/nodes/register",
                json=registration
            )

            if response.status_code == 200:
                logger.info(f"✅ Registered with orchestrator: {NODE_ID} @ {node_url}")
            else:
                logger.error(f"Registration failed: {response.status_code} {response.text}")

    except Exception as e:
        logger.error(f"Registration error: {e}")


@app.on_event("startup")
async def startup():
    """Initialize worker and heartbeat tasks."""
    global REQUEST_QUEUE

    logger.info(f"Starting NemoClaw Executor Node {NODE_ID} ({NODE_NAME})")
    logger.info(f"Orchestrator: {ORCHESTRATOR_URL}")

    # Initialize queue
    REQUEST_QUEUE = asyncio.Queue()

    # Start worker and heartbeat
    asyncio.create_task(worker())
    asyncio.create_task(heartbeat_loop())


@app.get("/", response_model=dict)
async def root():
    """Root endpoint."""
    return {
        "service": "NemoClaw Executor Node",
        "node_id": NODE_ID,
        "node_name": NODE_NAME,
        "status": "online",
        "version": "1.0.0"
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Return health and load metrics."""
    return HealthResponse(
        status="online",
        node_id=NODE_ID,
        node_name=NODE_NAME,
        active_requests=ACTIVE_REQUESTS,
        queue_depth=REQUEST_QUEUE.qsize(),
        avg_latency_ms=sum(LATENCY_HISTORY) / len(LATENCY_HISTORY) if LATENCY_HISTORY else 0,
        load_score=calculate_load_score()
    )


@app.post("/execute", response_model=ExecuteResponse)
async def execute_task(request: ExecuteRequest):
    """Execute an agent task."""
    logger.info(f"Received task | Queue: {REQUEST_QUEUE.qsize()} | Active: {ACTIVE_REQUESTS}")

    # Create future for result
    result_future = asyncio.Future()

    # Queue the request
    await REQUEST_QUEUE.put(({
        "task": request.task,
        "context": request.context
    }, result_future))

    # Wait for result
    try:
        result = await result_future
        return ExecuteResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting server on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
