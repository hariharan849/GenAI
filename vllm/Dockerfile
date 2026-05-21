# ---- Base image ----
ARG BASE_IMAGE=vllm/vllm-openai:v0.11.0
FROM ${BASE_IMAGE}

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Ensure both python and python3 exist
RUN which python3 && ln -sf $(which python3) /usr/bin/python

# Install deps
RUN uv pip install --system --no-cache --break-system-packages \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.34" \
    "pydantic-settings>=2.7"

COPY pyproject.toml .python-version ./
COPY src/ src/
COPY application.py ./

RUN uv pip install --system --no-cache --break-system-packages --no-deps .

EXPOSE 8000

ENTRYPOINT ["python3", "-m", "application"]