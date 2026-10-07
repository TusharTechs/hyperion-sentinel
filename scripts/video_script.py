"""Narration + scene text for the demo video (single source of truth)."""

VOICE = "Ava (Premium)"
RATE = 184

# spoken text (acronyms spelled for the TTS engine)
NARRATION = {
    "problem": "Shipping to the edge fails on the basics: images pinned to latest, no resource limits, no health probes, "
               "containers running as root, secrets in config files. On constrained nodes, each one means unpredictable behavior, "
               "and developers lose hours digging for them.",
    "impact": "Hyperion Sentinel turns that into one conversation inside the HYPER A I I D E: it inspects your real workspace, "
              "explains with evidence, fixes what's safe, asks before anything risky, and proves the improvement.",
    "how": "How it works: deterministic analyzers produce the facts, across Docker, Kubernetes, Compose, and HYPER A I application profiles. "
           "The language model only converses, grounded in the official docs and the I D E tutorial. Every change is an I D E action you confirm, then re-verified.",
    "live1": "Now live, in the real I D E, with the real Llama model. I ask Hyperion to prepare this app for the edge. "
             "It reports an Edge Readiness score of thirty-five out of a hundred, every finding tied to a file, a line, and evidence.",
    "live2": "What should I fix first? It ranks by impact, and explains why.",
    "live3": "Fix everything you safely can. A plan: safe changes, changes needing my confirmation, and manual items it never touches. "
             "Nothing has changed yet.",
    "live4": "I confirm. Files are rewritten by I D E actions, the deployment opens in the editor, "
             "and Hyperion re-reads the workspace: thirty-five becomes sixty-five.",
    "live5": "It answers HYPER A I questions from the official documentation and the I D E tutorial, citing the exact section.",
    "live6": "Off-topic requests are refused, and no files are touched.",
    "live7": "And destructive actions always ask first.",
    "close": "Hyperion Sentinel: inspect, explain, fix safely, verify. Open source on GitHub, shipped as a Docker image. Thank you.",
}

# the live steps: (narration key, caption, message typed into the IDE chat)
LIVE_STEPS = [
    ("live1", "1  Inspect: Edge Readiness report", "Prepare this application for edge deployment."),
    ("live2", "2  Explain: what matters most", "What should I fix first?"),
    ("live3", "3  Plan: safe / confirm / manual", "Fix everything you safely can."),
    ("live4", "4  Fix + verify: confirm, apply, re-read", "yes, all"),
    ("live5", "RAG: official docs + IDE tutorial, cited", "Which registry must my container image be in?"),
    ("live6", "Guardrails: off-topic refused", "What is the weather today?"),
    ("live7", "Human-in-the-loop: asks before deleting", "delete .dockerignore"),
]
E2E_CONFIRM_NO = "no"
