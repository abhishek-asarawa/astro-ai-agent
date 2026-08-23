FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

USER root

# Build tools cover Python packages that do not provide a wheel for the host
# architecture; curl supports explicit Ollama health checks.
# The base image's optional Yarn repository may outlive its bundled signing key.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Keep expensive ML and Chroma dependencies cached until a manifest changes.
COPY requirements.txt requirements-dev.txt pyproject.toml /tmp/astro-deps/
RUN python -m pip install --upgrade pip \
    && cd /tmp/astro-deps \
    && pip install --no-cache-dir -r requirements-dev.txt

USER vscode
CMD ["sleep", "infinity"]
