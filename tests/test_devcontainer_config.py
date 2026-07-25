"""Static contracts for the shared Compose and Dev Container environment."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER = REPO_ROOT / ".devcontainer"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def test_dockerfile_uses_python_311_and_cached_dependency_layer() -> None:
    text = (DEVCONTAINER / "Dockerfile").read_text()
    assert "python:1-3.11-bookworm" in text
    assert "rm -f /etc/apt/sources.list.d/yarn.list" in text
    assert "COPY requirements.txt requirements-dev.txt pyproject.toml" in text
    assert "pip install --no-cache-dir -r requirements-dev.txt" in text
    assert text.index("COPY requirements.txt") < text.index("pip install --no-cache-dir")
    assert "USER vscode" in text


def test_compose_service_is_idle_and_uses_shared_ollama() -> None:
    text = (DEVCONTAINER / "compose.yaml").read_text()
    assert "app:" in text
    assert 'user: "${LOCAL_UID}:${LOCAL_GID}"' in text
    assert "target: /workspace" in text
    assert "HOME: /tmp/astro-home" in text
    assert 'mkdir -p "$$HOME"' in text
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


def test_dockerignore_excludes_local_metadata_and_large_artifacts() -> None:
    patterns = {
        line.strip() for line in DOCKERIGNORE.read_text().splitlines() if line.strip() and not line.startswith("#")
    }
    required = {
        ".git",
        ".worktrees/",
        ".venv*/",
        "**/__pycache__/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        "chroma_db/",
        "eval_reports/",
        "acceptance_*/",
        "data/corpus/",
        "ocr_work/",
        "books/",
        "*.log",
        ".devcontainer/.env",
        ".devcontainer/compose.local.yaml",
    }
    assert required <= patterns


def test_dockerignore_retains_build_manifests_and_package_source() -> None:
    text = DOCKERIGNORE.read_text()
    assert "requirements.txt" not in text
    assert "requirements-dev.txt" not in text
    assert "pyproject.toml" not in text
    assert "astro_agent/" not in text
