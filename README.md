# Hyperion Sentinel

**Hyperion** is the agentic assistant of the [HyperAI IDE](https://ide.hyperai.di.uoa.gr/). **Sentinel** is its
differentiator: a deterministic *Edge Readiness* analyzer that inspects the workspace, explains concrete problems,
fixes what is safe (asking before anything risky), re-analyzes, and shows a before/after.

> Deterministic code produces the **facts** (findings, score, file edits). The LLM produces **conversation**
> (HYPER-AI Q&A grounded in the docs, free-form file generation). The LLM never invents findings or scores.

Built on the official `hyperion-starter` (FastAPI, `POST /chat` on port 8000, Server-Sent Events). The starter's
`/chat` contract, CORS middleware and `helpers.py` are preserved.

## What it does

| Capability | How |
|---|---|
| `/chat` microservice (:8000, SSE) | `main.py` — request `{user_id, text}`; frames `data: {"response": "<increment>"}` … `data: [DONE]` |
| HYPER-AI Q&A + **RAG** | `hyperion/rag.py` — BM25 over paragraph chunks of the official HYPER-AI docs in `knowledge/` (baked into the image); answers cite sources; says so when the docs don't cover a question |
| **IDE actions** (create / edit / delete, open in editor) | `hyperion/actions.py` — emits `{"action": "create_file" \| "edit_file" \| "delete_file" \| …}` SSE events that the IDE executes (see *Protocol*) |
| **Guardrails** | `hyperion/guard.py` — deterministic scope check + prompt-injection patterns; LLM classifier only for ambiguous text and **fails closed** |
| **Memory** | `hyperion/memory.py` — bounded per-`user_id` session: history, last report, numbered findings, plan, pending confirmation, change log |
| **Human-in-the-loop** | Conversational confirmation held in session state (the IDE protocol has no confirm event): every delete, every overwrite of an existing file, and every remediation plan waits for “yes” |
| **Edge Readiness analyzer** | `hyperion/analyzer/` — Dockerfile, Kubernetes, Compose, **HYPER-AI application profiles** (native + device, plus the IDE's own validator), dependencies, secrets/config, project completeness |
| **Remediation engine** | `hyperion/remediation.py` — comment-preserving YAML edits (ruamel), minimal Dockerfile edits; every result re-parsed; re-analysis reads the workspace back from the IDE |

### Findings and score

Each finding has `severity` (CRITICAL/HIGH/MEDIUM/LOW/GOOD), `category`, `file`, `line`, `finding`, `evidence`,
`why_it_matters`, `recommended_fix` and `automation_safety` (`SAFE_AUTO` / `CONFIRM_REQUIRED` / `MANUAL_ONLY`).
Discovered secrets are **never printed** (evidence says `KEY=<redacted>`).

Score = 100 − penalties (CRITICAL 25, HIGH 15, MEDIUM 7, LOW 3); repeats of one rule count 100/50/25%, each severity
tier is capped (50/36/20/9), floor 0. It is **Sentinel's own heuristic, not an official HYPER-AI metric or certification**.
Image pinning is only offered for well-known images (`KNOWN_TAGS`); an unknown image is never auto-pinned.

## Protocol (what the IDE actually does)

Reverse-engineered from the `ide-gui` bundle and `ide-backend` source (the starter does not document it):

* The chat panel `POST`s `{user_id, text}` to `http://localhost:8000/chat` and reads SSE `data:` events.
* An event whose JSON has an **`action`** key is executed by the IDE (not shown as text): `create_file`
  (writes via the backend **and opens it in the editor**; fails if the file exists), `edit_file` (overwrite + open),
  `delete_file`, `create_folder`, `delete_folder`, `write_yaml_to_editor`. Text goes in `{"response": …}`.
* The IDE performs the file writes itself (through `ide-backend`), asynchronously — so after emitting actions Hyperion
  polls the backend until the writes land, then re-analyzes what is *really* in the workspace.
* The workspace is the backend's `helm-charts/` tree (HYPER-AI application profiles + whatever you create). Hyperion
  reads it with `GET /api/files`, `GET /api/file` and the starter helper `validate_file`.

## Run locally

```bash
# 1. IDE (macOS: port 5000 is taken by AirPlay Receiver — serve the GUI on another port, e.g. 5050:80)
docker run --rm -p 3001:3001 -e AUTH_ENABLED=false --name ide-backend donmichael/ide-backend:latest
docker run --rm -p 5050:80 --name ide-gui donmichael/ide-gui:latest      # Apple Silicon: add --platform linux/amd64

# 2. LLM key (ask the HyperAI team for your team's key) — never commit it
cp .env.example .env   # then set API_KEY=...

# 3. Hyperion
uv run main.py          # or: docker compose up --build

# 4. Load the imperfect demo app into the IDE workspace (folder `demo/`) and open http://localhost:5050
uv run python demo/seed_workspace.py
```

Open **Hyperion** from the robot icon in the IDE sidebar. Without the IDE:

```bash
curl -N -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id": "123e4567-e89b-12d3-a456-426614174000", "text": "Prepare this application for edge deployment."}'
uv run python demo/analyze_dir.py demo/hero      # run the analyzer on a local folder
```

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `API_KEY` | *(none)* | Key for the OpenAI-compatible LLM server. **Not baked into the image.** Without it, deterministic features and RAG excerpts still work |
| `LLM_BASE_URL` | `https://legion1.di.uoa.gr/v1` | OpenAI-compatible endpoint (e.g. Ollama: `http://host.docker.internal:11434/v1`) |
| `LLM_MODEL` | `llama3.1` | Model name |
| `LLM_TIMEOUT` | `60` | Seconds per LLM call |
| `IDE_BACKEND_URL` | `http://localhost:3001/api` (image: `http://host.docker.internal:3001/api`) | IDE backend |

## Docker

```bash
docker build -t hyperion-starter-hyperion .
docker run --rm -p 8000:8000 -e API_KEY=... --add-host host.docker.internal:host-gateway hyperion-starter-hyperion
```

* Multi-stage, runs as non-root (uid 10001), has a `HEALTHCHECK`, listens on `0.0.0.0:8000`, docs included.
* **Publish an `amd64` image** (evaluators typically run amd64; an arm64-only image from Apple Silicon fails with
  `exec format error`): `docker build --platform linux/amd64 -t <user>/hyperion:latest .` then `docker push`.
* Behind a TLS-inspecting corporate proxy, copy your CA bundle to `./ca-bundle.pem` before building. It is only used in
  the throwaway builder stage and is not part of the shipped image (`.gitignore`d).

## Tests

```bash
uv run pytest -q      # 188 tests: API/SSE, guardrails, path safety, HITL, analyzer (every finding type), remediation, agent flows
```

Tests run the whole agent against a simulated IDE (`tests/conftest.py: FakeIDE`) that executes SSE actions the way the
real IDE does, including a laggy-IDE mode. LLM calls are faked.

## Demo (2–3 minutes)

Seed with `uv run python demo/seed_workspace.py`, reload the IDE, open Hyperion, then say:

1. `Prepare this application for edge deployment.` → Edge Readiness report (score, numbered findings).
2. `What should I fix first?` → top findings with evidence and why.
3. `Fix everything you safely can.` → plan: safe / needs confirmation / manual. Nothing changed yet.
4. `yes, all` → files created/rewritten in the explorer, `deployment.yaml` opens, verified re-read, **before → after score**.
5. `What changed and why?` → per-file change list tied to resolved findings.
6. Bonus: `Create a deployment YAML for a service using the nginx Docker image` · `delete deployment.yaml` → confirm ·
   `What is the Application Profile Manager?` (RAG) · `What is the weather today?` (guardrail).

## Known limitations

* The score and findings are heuristics over files in the workspace; Sentinel does not deploy to or inspect real edge nodes.
* HITL is conversational; the IDE gives no way to render a confirm button.
* The live LLM paths (RAG answers, free-form create/edit, ambiguous-scope classification) need the team `API_KEY`;
  with a small 8B model, free-form edits are always diffed and confirmed before being written.
* Image pinning uses a small table of conservative tags, not a registry lookup.
* Docs for RAG are the six official HYPER-AI deliverable summaries plus short IDE notes (`knowledge/HyperAI_IDE_Notes.md`);
  that is all the grounding there is.

## License

[Apache 2.0](LICENCE)
