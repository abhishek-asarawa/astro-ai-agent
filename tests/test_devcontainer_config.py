"""Static contracts for the shared Compose and Dev Container environment."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER = REPO_ROOT / ".devcontainer"


def test_dockerfile_uses_python_311_and_cached_dependency_layer() -> None:
    text = (DEVCONTAINER / "Dockerfile").read_text()
    assert "python:1-3.11-bookworm" in text
    assert "COPY requirements.txt requirements-dev.txt pyproject.toml" in text
    assert "pip install --no-cache-dir -r requirements-dev.txt" in text
    assert text.index("COPY requirements.txt") < text.index("pip install --no-cache-dir")
    assert "USER vscode" in text


def test_compose_service_is_idle_and_uses_shared_ollama() -> None:
    text = (DEVCONTAINER / "compose.yaml").read_text()
    assert "app:" in text
    assert "target: /workspace" in text
    assert "sleep infinity" in text
    assert "ASTRO_OLLAMA_HOST: http://host.docker.internal:11434" in text
    assert "host.docker.internal:host-gateway" in text
    assert "target: 8501" in text
    assert 'published: "0"' in text
    assert "streamlit run" not in text


def test_devcontainer_attaches_to_compose_app_service() -> None:
    config = json.loads((DEVCONTAINER / "devcontainer.json").read_text())
    assert config["service"] == "app"
    assert config["workspaceFolder"] == "/workspace"
    assert config["dockerComposeFile"] == ["compose.yaml", "compose.local.yaml"]
    assert config["initializeCommand"] == "python3 scripts/devcontainer_support.py prepare --worktree ."
    assert config["postCreateCommand"] == "python -m pip install --user -e ."
    assert config["remoteUser"] == "vscode"
    assert config["shutdownAction"] == "stopCompose"
