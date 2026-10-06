# Hyperion Sentinel

**The edge-readiness engineer inside the HYPER-AI IDE** - Veles Hack 2026, Challenge 1 (HYPER-AI / Hyperion).

Hyperion is an agentic microservice for the HyperAI IDE. It answers questions about HYPER-AI (RAG over the official docs), turns natural language into IDE actions (create / edit / delete files, opened in the editor), keeps per-session memory, enforces guardrails, and asks for confirmation before destructive changes. **Sentinel** adds a deterministic Edge Readiness analyzer: it inspects the workspace (Dockerfile, Kubernetes, Compose, HYPER-AI application profiles, dependencies, secrets), explains findings with evidence, fixes what is safe, and re-verifies through the IDE.

- Source: https://github.com/TusharTechs/hyperion-sentinel
- Image: `linux/amd64`, non-root, docs baked in, no secrets in the image

## Run

```bash
docker run --rm -p 8000:8000 \
  -e API_KEY=<your LLM key> \
  --add-host host.docker.internal:host-gateway \
  tushartechs/hyperion:latest
```

The IDE talks to `http://localhost:8000/chat`. Quick test:

```bash
curl -N -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id": "123e4567-e89b-12d3-a456-426614174000", "text": "What is HyperAI?"}'
```

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `API_KEY` | none | key for the OpenAI-compatible LLM server (never baked into the image) |
| `LLM_BASE_URL` | `https://legion1.di.uoa.gr/v1` | LLM endpoint |
| `LLM_MODEL` | `llama3.1` | model name |
| `IDE_BACKEND_URL` | `http://host.docker.internal:3001/api` | where the IDE backend is reachable from the container |

Works without an IDE backend and without an API key too (deterministic features and documentation excerpts still answer).

License: Apache-2.0.
