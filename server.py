#!/usr/bin/env python3
"""
AgentsForImpact — Multi-Agent Orchestration Dashboard
NVIDIA Nemotron-powered multi-agent system for real-time task processing.

Architecture:
  1. Classifier  → categorizes the task (Nemotron-Nano)
  2. Researcher  → gathers context and facts (Nemotron-Super)
  3. Strategist  → plans the approach (Nemotron-Super)
  4. Executor    → produces the final output (Nemotron-Super)

Usage:
  pip install openai
  python server.py --port 8080
  Open http://localhost:8080/dashboard/
"""

import argparse, json, time, os, threading, re
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError
from concurrent.futures import ThreadPoolExecutor

# ── Config ──
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
NVIDIA_KEY = os.environ.get("NVIDIA_API_KEY", "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")

MODELS = {
    "nano": "nvidia/nemotron-3-nano-30b-a3b",
    "super": "nvidia/nemotron-3-super-120b-a12b",
}

AGENTS = {
    "classifier": {
        "name": "Classifier",
        "icon": "🏷️",
        "model": "nano",
        "color": "#38d9ff",
        "prompt": """You are a task Classifier agent. Analyze the user's request and categorize it.
Respond with ONLY a JSON object:
{"category":"<research|analysis|creative|technical|advisory>","complexity":"<simple|moderate|complex>","summary":"<1 sentence summary of what the user needs>","key_entities":["<entity1>","<entity2>"]}""",
        "max_tokens": 150,
    },
    "researcher": {
        "name": "Researcher",
        "icon": "🔍",
        "model": "super",
        "color": "#a78bfa",
        "prompt": """You are a Researcher agent. Given a classified task, gather relevant context, facts, and background information.
Be specific and factual. Focus on what's most relevant to solving the task.
Respond with ONLY a JSON object:
{"findings":["<finding1>","<finding2>","<finding3>"],"context":"<relevant background in 2-3 sentences>","confidence":0.0-1.0,"sources_needed":["<type of source that would help>"]}""",
        "max_tokens": 300,
    },
    "strategist": {
        "name": "Strategist",
        "icon": "🧠",
        "model": "super",
        "color": "#00e68a",
        "prompt": """You are a Strategist agent. Given the research findings, create a specific action plan.
Your plan should be concrete, actionable, and tailored to the specific task.
Respond with ONLY a JSON object:
{"approach":"<chosen strategy name>","reasoning":"<why this approach>","steps":["<step1>","<step2>","<step3>","<step4>"],"risks":["<risk1>"],"expected_outcome":"<what success looks like>"}""",
        "max_tokens": 350,
    },
    "executor": {
        "name": "Executor",
        "icon": "⚡",
        "model": "super",
        "color": "#ffb347",
        "prompt": """You are an Executor agent. Given the strategy and all prior context, produce the final comprehensive response.
Write a clear, well-structured, actionable response for the end user.
Do NOT use JSON — write in natural language with clear formatting.
Be specific, practical, and thorough.""",
        "max_tokens": 800,
    },
}

# ── State ──
PIPELINE_LOG = []  # list of pipeline runs
AGENT_STATS = {k: {"calls": 0, "total_ms": 0, "errors": 0, "last_active": None} for k in AGENTS}
CHAT_HISTORY = {}

# ── Node Registry (multi-instance swarm) ──
import uuid, socket
INSTANCE_ID = str(uuid.uuid4())[:8]
INSTANCE_NAME = os.environ.get("INSTANCE_NAME", socket.gethostname())
NODE_REGISTRY = {}  # id -> {name, url, role, status, agents, last_seen}

def strip_think(text):
    if not text:
        return ""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    if '<think>' in text:
        text = text.split('<think>')[0].strip()
    if '</think>' in text:
        text = text.split('</think>')[-1].strip()
    return text

def call_agent(role, user_msg, timeout_s=60):
    """Call a single agent via NVIDIA API."""
    cfg = AGENTS[role]
    model = MODELS[cfg["model"]]
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": cfg["prompt"]},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.7 if role == "executor" else 0.3,
        "max_tokens": cfg["max_tokens"],
        "top_p": 0.95,
    }
    
    # Enable thinking for super model
    if cfg["model"] == "super":
        payload["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": cfg["max_tokens"]
        }
    
    req = Request(
        f"{NVIDIA_BASE}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {NVIDIA_KEY}"
        }
    )
    
    t0 = time.time()
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read())
            msg = body.get("choices", [{}])[0].get("message", {})
            content = (msg.get("content") or "").strip()
            reasoning = (msg.get("reasoning_content") or "").strip()
            
            # Use content if available, fall back to reasoning
            text = content or reasoning
            text = strip_think(text)
            
            elapsed = round((time.time() - t0) * 1000)
            
            # Update stats
            AGENT_STATS[role]["calls"] += 1
            AGENT_STATS[role]["total_ms"] += elapsed
            AGENT_STATS[role]["last_active"] = time.strftime("%H:%M:%S")
            
            print(f"  [{role}] {elapsed}ms | {len(text)} chars | model={model}")
            
            # Try JSON parse for structured agents
            if role != "executor":
                try:
                    # Find JSON in text
                    start = text.find('{')
                    end = text.rfind('}') + 1
                    if start >= 0 and end > start:
                        parsed = json.loads(text[start:end])
                        return {"data": parsed, "raw": text, "latency_ms": elapsed, "model": model, "thinking": strip_think(reasoning) if reasoning != content else ""}
                except:
                    pass
            
            return {"data": text, "raw": text, "latency_ms": elapsed, "model": model, "thinking": strip_think(reasoning) if reasoning != content else ""}
    
    except Exception as e:
        elapsed = round((time.time() - t0) * 1000)
        AGENT_STATS[role]["errors"] += 1
        print(f"  [{role}] ERROR ({elapsed}ms): {e}")
        return {"data": None, "raw": str(e), "latency_ms": elapsed, "model": model, "error": str(e)}


def run_pipeline(task):
    """Run the full 4-agent pipeline."""
    print(f"\n{'='*60}")
    print(f"  PIPELINE: {task[:80]}")
    print(f"{'='*60}")
    
    pipeline = {"task": task, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "agents": [], "status": "running"}
    total_t0 = time.time()
    
    # Step 1: Classifier (fast, nano model)
    print("\n[1/4] Classifier...")
    cls_result = call_agent("classifier", f"Task: {task}")
    pipeline["agents"].append({"role": "classifier", **cls_result})
    
    cls_data = cls_result.get("data", {})
    if isinstance(cls_data, dict):
        category = cls_data.get("category", "general")
        summary = cls_data.get("summary", task)
        entities = cls_data.get("key_entities", [])
    else:
        category = "general"
        summary = task
        entities = []
    
    # Step 2+3: Researcher + Strategist in PARALLEL
    print("\n[2-3/4] Researcher + Strategist (parallel)...")
    
    research_msg = f"""Task: {task}
Category: {category}
Summary: {summary}
Key entities: {', '.join(entities) if entities else 'none identified'}

Research this topic and provide relevant facts and context."""

    strategy_msg = f"""Task: {task}
Category: {category}
Summary: {summary}
Key entities: {', '.join(entities) if entities else 'none identified'}

Create a strategy to address this task effectively."""

    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_research = ex.submit(call_agent, "researcher", research_msg, 45)
        fut_strategy = ex.submit(call_agent, "strategist", strategy_msg, 45)
        res_result = fut_research.result()
        str_result = fut_strategy.result()
    
    pipeline["agents"].append({"role": "researcher", **res_result})
    pipeline["agents"].append({"role": "strategist", **str_result})
    
    # Step 4: Executor (uses all prior context)
    print("\n[4/4] Executor...")
    
    research_text = json.dumps(res_result.get("data", "")) if isinstance(res_result.get("data"), dict) else str(res_result.get("data", ""))
    strategy_text = json.dumps(str_result.get("data", "")) if isinstance(str_result.get("data"), dict) else str(str_result.get("data", ""))
    
    exec_msg = f"""ORIGINAL TASK: {task}

CLASSIFICATION:
Category: {category}
Summary: {summary}

RESEARCH FINDINGS:
{research_text}

STRATEGY:
{strategy_text}

Now produce the final comprehensive response for the user. Be specific, actionable, and thorough."""

    exec_result = call_agent("executor", exec_msg, 90)
    pipeline["agents"].append({"role": "executor", **exec_result})
    
    pipeline["total_ms"] = round((time.time() - total_t0) * 1000)
    pipeline["status"] = "complete"
    pipeline["final_answer"] = exec_result.get("data", "No response generated.")
    
    PIPELINE_LOG.append(pipeline)
    if len(PIPELINE_LOG) > 50:
        PIPELINE_LOG.pop(0)
    
    print(f"\n{'='*60}")
    print(f"  DONE in {pipeline['total_ms']}ms")
    print(f"{'='*60}\n")
    
    return pipeline


class Handler(SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/pipeline":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            task = body.get("task", "")
            if not task:
                self._json(400, {"error": "task required"})
                return
            result = run_pipeline(task)
            self._json(200, result)
            return

        if self.path == "/api/agent":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            role = body.get("role", "")
            message = body.get("message", "")
            if role not in AGENTS or not message:
                self._json(400, {"error": "role and message required"})
                return
            result = call_agent(role, message)
            self._json(200, {"role": role, **result})
            return

        if self.path == "/api/nodes/register":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            nid = body.get("id", str(uuid.uuid4())[:8])
            NODE_REGISTRY[nid] = {
                "name": body.get("name", "unknown"),
                "url": body.get("url", ""),
                "role": body.get("role", "slave"),
                "status": "online",
                "agents": body.get("agents", []),
                "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
            self._json(200, {"status": "registered", "node_id": nid})
            return

        if self.path == "/api/nodes/heartbeat":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            nid = body.get("id", "")
            if nid in NODE_REGISTRY:
                NODE_REGISTRY[nid]["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                NODE_REGISTRY[nid]["status"] = "online"
                if "agents" in body:
                    NODE_REGISTRY[nid]["agents"] = body["agents"]
            self._json(200, {"status": "ok"})
            return

        if self.path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            msg = body.get("message", "")
            session = body.get("session_id", "default")
            if not msg:
                self._json(400, {"error": "message required"})
                return
            
            if session not in CHAT_HISTORY:
                CHAT_HISTORY[session] = []
            CHAT_HISTORY[session].append({"role": "user", "content": msg})
            
            messages = [{"role": "system", "content": "You are a helpful AI assistant powered by NVIDIA Nemotron. Be concise and helpful."}] + CHAT_HISTORY[session][-10:]
            
            payload = {
                "model": MODELS["super"],
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 600,
                "top_p": 0.95,
            }
            req = Request(
                f"{NVIDIA_BASE}/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {NVIDIA_KEY}"}
            )
            try:
                t0 = time.time()
                with urlopen(req, timeout=90) as resp:
                    body = json.loads(resp.read())
                    content = (body["choices"][0]["message"].get("content") or body["choices"][0]["message"].get("reasoning_content") or "")
                    content = strip_think(content)
                    elapsed = round((time.time() - t0) * 1000)
                CHAT_HISTORY[session].append({"role": "assistant", "content": content})
                self._json(200, {"reply": content, "latency_ms": elapsed, "model": MODELS["super"]})
            except Exception as e:
                self._json(200, {"reply": f"Error: {e}", "latency_ms": 0, "model": MODELS["super"]})
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            self._json(200, {
                "status": "online",
                "instance_id": INSTANCE_ID,
                "instance_name": INSTANCE_NAME,
                "agents": {k: {**AGENTS[k], "stats": AGENT_STATS[k], "model_id": MODELS[AGENTS[k]["model"]]} for k in AGENTS},
                "pipeline_count": len(PIPELINE_LOG),
                "models": MODELS,
                "nodes": NODE_REGISTRY
            })
            return

        if self.path == "/api/nodes":
            self._json(200, {"nodes": NODE_REGISTRY, "self": {"id": INSTANCE_ID, "name": INSTANCE_NAME}})
            return

        if self.path == "/api/history":
            self._json(200, {"pipelines": PIPELINE_LOG[-20:]})
            return

        # Serve dashboard
        if self.path == "/" or self.path == "/dashboard" or self.path == "/dashboard/":
            self.path = "/dashboard/index.html"
        
        return super().do_GET()

    def _json(self, code, data):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="AgentsForImpact Server")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    print(f"""
╔═══════════════════════════════════════════════════╗
║   🚀 AgentsForImpact — Multi-Agent Dashboard      ║
║   NVIDIA Nemotron-powered orchestration            ║
╠═══════════════════════════════════════════════════╣
║   Dashboard:  http://localhost:{args.port}/dashboard/    ║
║   API:        http://localhost:{args.port}/api/status     ║
╠═══════════════════════════════════════════════════╣
║   Agents:                                          ║
║     🏷️  Classifier  → {MODELS['nano']:<28s} ║
║     🔍  Researcher  → {MODELS['super']:<28s} ║
║     🧠  Strategist  → {MODELS['super']:<28s} ║
║     ⚡  Executor    → {MODELS['super']:<28s} ║
╚═══════════════════════════════════════════════════╝
""")
    server.serve_forever()


if __name__ == "__main__":
    main()
