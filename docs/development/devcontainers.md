# Parallel worktree Dev Containers

## Prerequisites

Install Git and Docker Desktop (or Docker Engine with Compose). Start host
Ollama and pull the models listed in the root README. Containers reach it at
`http://host.docker.internal:11434`.

Check the host service:

```bash
curl http://localhost:11434/api/tags
```

## Create an isolated agent worktree

From the primary checkout:

```bash
./scripts/devcontainer-worktree.sh timing-window
```

The helper creates branch `agent/timing-window`, worktree
`.worktrees/timing-window`, and a unique Compose project. Use `--base <ref>` to
change the starting revision or `--no-start` to create files without Docker.
It never copies `.env`, Chroma data, logs, or corpus files.

## Open manually

Open either the primary checkout or a linked worktree in Cursor or VS Code and
choose **Dev Containers: Reopen in Container**. The host initialization command
generates worktree-local, gitignored Compose metadata before attachment.

## Test and run

Inside the container, run the CI-equivalent gate:

```bash
./scripts/run_ci_checks.sh full
```

Check shared Ollama from inside the container:

```bash
curl http://host.docker.internal:11434/api/tags
```

CI does not require Ollama. If the health check fails, start Ollama on the host
and confirm Docker permits `host.docker.internal`.

Start the UI on demand:

```bash
streamlit run app.py --server.address 0.0.0.0
```

In a host terminal, use the helper's printed Compose command ending in:

```bash
docker compose port app 8501
```

Open `http://localhost:<reported-port>`. Every worktree receives a distinct
Docker-selected host port.

The container's `HOME` (`/tmp/astro-home`) is per-container and intentionally
ephemeral: it exists only to give the raw numeric host user a writable home for
`pip --user` installs, and it disappears whenever that worktree's container is
removed (`docker compose ... down` or a rebuild). Nothing you need to keep
should be written there.

## Stop one container project

Run the exact `docker compose ... down` command printed by the helper. It
targets only that worktree's explicit Compose project and does not remove the Git worktree or branch.
Remove those later with explicit `git worktree remove`
and `git branch -d` commands when their changes are safely integrated.

## Parallel smoke test

Create two temporary worktrees:

```bash
./scripts/devcontainer-worktree.sh smoke-one
./scripts/devcontainer-worktree.sh smoke-two
```

For each worktree, use its printed commands to:

1. Run `python --version` and confirm Python 3.11.
2. Run `python -c "import astro_agent; print(astro_agent.__file__)"`.
3. Run `./scripts/run_ci_checks.sh full`.
4. Run `git status`.
5. Make an empty test commit with explicit smoke-test identity:
   `git -c user.name=Smoke -c user.email=smoke@example.test commit --allow-empty -m "test: container git smoke"`.
6. Check `curl http://host.docker.internal:11434/api/tags`.
7. Start Streamlit and resolve `docker compose port app 8501`.

Confirm the project names, containers, networks, and reported host ports differ.
Stop `smoke-one` and verify `smoke-two` still responds. Run the full CI gate in
one container with host Ollama stopped to prove CI remains offline-safe.

After verification, run each printed `down` command, then explicitly remove the
temporary worktrees and branches:

```bash
git worktree remove .worktrees/smoke-one
git worktree remove .worktrees/smoke-two
git branch -D agent/smoke-one agent/smoke-two
```
