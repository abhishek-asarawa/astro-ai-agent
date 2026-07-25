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

The container's `HOME` (`/tmp/astro-home`) is per-container. It survives `docker compose ... stop` and `start`,
but it is lost whenever the container is removed or recreated — for example
`docker compose ... down`, or an `up -d --build` that recreates the container
after a rebuild. It exists only to give the raw numeric host user a writable
home for `pip --user` installs; nothing you need to keep should be written
there.

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
8. Curl each worktree's own Streamlit URL and require HTTP success:

   ```bash
   curl -sf -o /dev/null -w '%{http_code}\n' http://localhost:<smoke-one-port>
   curl -sf -o /dev/null -w '%{http_code}\n' http://localhost:<smoke-two-port>
   ```

   Both commands must print `200` and exit `0`. `-f` makes curl itself fail on
   a non-2xx response, so a non-zero exit means that worktree's app is not
   actually serving Streamlit, not merely that the port lookup succeeded.

Confirm the project names, containers, networks, and reported host ports differ.
Stop `smoke-one` and verify `smoke-two` still responds. Run the full CI gate in
one container with host Ollama stopped to prove CI remains offline-safe.

### Dependency-cache verification

In one worktree, append a uniquely tagged probe line to one source file — not
`requirements.txt`, `requirements-dev.txt`, or `pyproject.toml`:

```bash
echo "# smoke-cache-probe: $(date +%s)" >> astro_agent/__init__.py
```

Rerun that worktree's printed `up -d --build app` command. In the build log,
confirm the build reports the `pip install --no-cache-dir -r requirements-dev.txt` step as `CACHED`
rather than re-running it. That `CACHED` marker on the dependency-install layer
is the proof the layer was reused, not rebuilt: only the three copied manifest
files can invalidate it, because application source is bind-mounted at runtime and never copied into the image.

Immediately after that check, restore only the probe line — before any other
cleanup:

```bash
grep -v '^# smoke-cache-probe:' astro_agent/__init__.py > astro_agent/__init__.py.tmp
mv astro_agent/__init__.py.tmp astro_agent/__init__.py
git status --short
```

`git status --short` must print nothing: the probe line is the only change
this procedure ever makes, and filtering it out by its unique marker restores
the file exactly, without `git reset --hard` or `git checkout --`, either of
which would also discard any other uncommitted change already sitting in that
file. This keeps the worktree clean so the non-forced `git worktree remove`
below succeeds without needing `--force`.

After verification, run each printed `down` command, then explicitly remove the
temporary worktrees and branches:

```bash
git worktree remove .worktrees/smoke-one
git worktree remove .worktrees/smoke-two
git branch -D agent/smoke-one agent/smoke-two
```

## Temporary smoke-image cleanup

Routine `down` intentionally leaves the built image in place after removing a
project's containers and network — that is by design, so a later `up` on an
ordinary contributor worktree you intend to keep reuses the cached
dependency-install layer instead of rebuilding it.

Temporary smoke worktrees are the exception: once their worktrees and branches
are removed, their images serve no further purpose, so remove them too as
smoke-only cleanup (this step is specific to disposable smoke worktrees, not
part of routine `down`):

```bash
docker image rm <smoke-one-project>-app <smoke-two-project>-app
```
