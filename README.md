# 🚀 AgentsForImpact

**Multi-Agent Orchestration Dashboard** powered by NVIDIA Nemotron models.

Built for [Hack for Impact at GTC 2026](https://nvidia.com/gtc) — Human Impact category.

## Architecture

Four specialized AI agents work together in a pipeline:

```
User Task → [🏷️ Classifier] → [🔍 Researcher ⟦parallel⟧ 🧠 Strategist] → [⚡ Executor] → Final Response
```

| Agent | Role | Model |
|-------|------|-------|
| 🏷️ Classifier | Categorizes the task (type, complexity, entities) | Nemotron-Nano-30B |
| 🔍 Researcher | Gathers relevant facts and context | Nemotron-Super-120B |
| 🧠 Strategist | Creates an actionable plan | Nemotron-Super-120B |
| ⚡ Executor | Produces the final comprehensive response | Nemotron-Super-120B |

**Researcher and Strategist run in parallel** for faster pipeline execution.

## Quick Start

```bash
pip install openai
python server.py --port 8080
# Open http://localhost:8080/dashboard/
```

## Features

- **Real-time agent node monitoring** — see calls, latency, errors per agent
- **Pipeline flow visualization** — watch each agent activate in sequence
- **Decision trace** — inspect each agent's reasoning, thinking process, and output
- **Individual agent testing** — test any single agent in isolation
- **Pipeline history** — replay and compare previous runs
- **6 pre-built test scenarios** — climate, emergency response, IoT, food waste, mental health, public safety

## NVIDIA AI Ecosystem

- **Nemotron-Nano-30B** (`nvidia/nemotron-3-nano-30b-a3b`) — fast classification
- **Nemotron-Super-120B** (`nvidia/nemotron-3-super-120b-a12b`) — deep reasoning with thinking enabled
- **NVIDIA Inference API** (`integrate.api.nvidia.com`)

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipeline` | POST | Run full 4-agent pipeline |
| `/api/agent` | POST | Test individual agent |
| `/api/chat` | POST | Free-form chat |
| `/api/status` | GET | Agent status and stats |
| `/api/history` | GET | Pipeline run history |

## Omi Voice Integration

The dashboard supports hands-free voice dispatch via an [Omi](https://www.omi.me/) wearable device and the included bridge server.

### How it works

```
Omi device → POST /transcript → bridge (port 8081) → WebSocket /ws → Dashboard Omi Mode toggle
```

1. Start the bridge: `python -m uvicorn bridge.main:app --host 0.0.0.0 --port 8081`
2. Expose it: `ngrok http 8081`
3. Configure the Omi app webhook to `POST https://<your-ngrok>/transcript`
4. Open the dashboard and click **🎙️ Omi Mode** — button turns green when connected
5. Say **"Hey OpenClaw, \<your task\>"** — the command auto-fills and runs the pipeline

### Transcript endpoint (ngrok)

```
POST https://unleased-unambiguously-jenice.ngrok-free.dev/transcript
Content-Type: application/json
{"text": "Hey OpenClaw, run a climate analysis"}
```

### Test scripts

```bash
# Smoke-test the ngrok endpoint
./test-omi-transcription.sh --test-send

# Stream live transcripts from bridge via WebSocket (requires websocat)
./test-omi-transcription.sh
```

## License

MIT
