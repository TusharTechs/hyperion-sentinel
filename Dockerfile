# ---- builder: resolve and install dependencies (uv + pip never reach the final image) ----
FROM python:3.14-slim AS deps
WORKDIR /app
ENV UV_HTTP_TIMEOUT=180 PIP_DEFAULT_TIMEOUT=180
# `ca-bundle.pe[m]` is optional: behind a TLS-inspecting corporate proxy, copy your CA bundle to ./ca-bundle.pem
# before building. It exists only in this builder stage and is never shipped.
COPY pyproject.toml uv.lock ca-bundle.pe[m] ./
RUN if [ -f ca-bundle.pem ]; then export SSL_CERT_FILE=/app/ca-bundle.pem REQUESTS_CA_BUNDLE=/app/ca-bundle.pem PIP_CERT=/app/ca-bundle.pem; fi; \
    pip install --no-cache-dir uv && uv sync --no-dev --frozen --no-cache

# ---- runtime ----
FROM python:3.14-slim
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv

# Application code + the official HYPER-AI documentation used for RAG (no internet needed at runtime).
COPY main.py helpers.py ./
COPY hyperion/ ./hyperion/
COPY knowledge/*.md knowledge/embeddings.json ./knowledge/

# Run as an unprivileged user.
RUN useradd --system --uid 10001 --no-create-home hyperion
USER 10001

# Configuration comes from the environment - nothing secret is baked into the image.
#   API_KEY          key for the OpenAI-compatible LLM server (required for LLM answers)
#   LLM_BASE_URL     default https://legion1.di.uoa.gr/v1
#   LLM_MODEL        default llama3.1
#   IDE_BACKEND_URL  where the IDE backend lives from inside the container
ENV IDE_BACKEND_URL=http://host.docker.internal:3001/api \
    LLM_BASE_URL=https://legion1.di.uoa.gr/v1 \
    LLM_MODEL=llama3.1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["python", "main.py"]
