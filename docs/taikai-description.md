## Hyperion Sentinel - the edge-readiness engineer inside the HYPER-AI IDE

**Challenge 1 (HYPER-AI): Hyperion - an LLM-powered agentic assistant.**

Hyperion lets developers talk to the HYPER-AI IDE in natural language. **Sentinel** is what makes it more than a chatbot: it inspects the developer's real workspace, scores how ready it is for constrained edge/cloud deployment, explains concrete problems with evidence, fixes what is safe, asks before anything risky, then **re-reads the IDE and shows the before/after improvement**.

> *"Prepare this application for edge deployment."* → report (35/100) → *"Fix everything you safely can."* → plan → *"yes"* → files change in the IDE → **65/100, +30, 12 findings resolved**.

### Every challenge criterion
1. **Working agent** - FastAPI `/chat` on :8000, SSE streaming; natural language becomes real IDE actions (`create_file`, `edit_file`, `delete_file`) and the file opens in the editor. We reverse-engineered the IDE's action protocol from the frontend.
2. **Guardrails** - deterministic scope + prompt-injection rules; ambiguous text goes to an LLM classifier that fails closed. Off-topic requests never touch files.
3. **RAG** - BM25 over the six official HYPER-AI deliverables (baked into the image, works offline), with cited sources; when the docs don't cover a question it says so instead of guessing.
4. **Memory** - bounded per-`user_id` session: findings ("fix the *second* issue"), plan, facts ("my name is…"), last file ("delete *it*").
5. **Human-in-the-loop** - every delete, every overwrite and every remediation plan waits for an explicit *yes*; mass deletes are refused.

### The differentiator: deterministic, evidence-backed analysis
Dockerfile, Kubernetes, Docker Compose and **HYPER-AI application profiles** (native + device, plus the IDE's own validator), dependencies, secrets (never printed) and project completeness. Findings carry severity, file, line, evidence, why it matters, the fix and an automation-safety level. The score is a transparent formula - **the LLM never invents findings or scores** - and is explicitly *not* an official HYPER-AI metric. Fixes are comment-preserving, re-parsed, idempotent, and verified by re-reading the workspace through the IDE. Model-drafted files are validated and self-checked by Sentinel before they are written.

### Engineering
Python 3.14 · FastAPI · LangChain (OpenAI-compatible, Llama 3.1) · ruamel.yaml · BM25 · Docker (multi-stage, non-root, amd64). **203 automated tests** (API, guardrails, path safety, HITL, every finding type, remediation, memory), verified in the real HYPER-AI IDE and against the live model.

### Links
- Code: https://github.com/TusharTechs/hyperion-sentinel
- Docker image: `tushartechs/hyperion:latest` - https://hub.docker.com/r/tushartechs/hyperion
- Run: `docker run -p 8000:8000 -e API_KEY=<key> --add-host host.docker.internal:host-gateway tushartechs/hyperion:latest`

Built on the official `hyperion-starter` (HYPER-AI project, Eclipse Research Labs). Apache-2.0.
