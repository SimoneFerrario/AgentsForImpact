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

## License

MIT
