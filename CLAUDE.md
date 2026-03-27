# qara — Claude Code Guide

## Project overview

**qara** is a cross-platform process monitor daemon with Telegram notifications and bidirectional control. Core use case: `qara run python train.py` → get notified on finish/crash; send `/kill`, `/status`, `/run` back from Telegram.

Target users: ML practitioners running long training jobs.

## Tech stack

| Concern | Choice | Reason |
|---|---|---|
| Runtime | Python 3.11+, asyncio | async-native throughout |
| Package manager | uv | fast, lockfile-based |
| Telegram | aiogram 3 | async-native (not python-telegram-bot) |
| Config | stdlib `tomllib`, TOML files | zero extra deps |
| Storage | append-only JSONL | zero-dep, debuggable with `tail` |
| IPC | newline-delimited JSON over Unix socket (Linux/macOS) / named pipe (Windows) | no broker needed |
| GPU metrics | pynvml (not nvidia-smi subprocess) | direct API, no parsing |
| Build | hatchling | simple src-layout support |
| Lint/format | ruff | fast, single tool |
| Types | mypy strict | catches async mistakes early |

## Repo layout

```
src/qara/
  core/        # watcher, event engine, daemon
  channels/    # notification channels (Telegram, …)
  config/      # schema (pydantic v2) + loader (tomllib)
  storage/     # JSONL append log
  platform/    # systemd/launchd/Windows SCM installers
  transport/   # Unix socket / named pipe IPC
  plugins/     # importlib.metadata entry points
tests/
```

## Commands

```bash
# Install dev dependencies
uv sync --group dev

# Run linter
uv run ruff check src/

# Format
uv run ruff format src/

# Type check
uv run mypy src/

# Run tests
uv run pytest

# Run qara
uv run qara --help
```

## Non-negotiable decisions

- **Never use `shell=True`** in subprocess calls. Always use `asyncio.create_subprocess_exec` with a list.
- **No root required** anywhere in the codebase. Daemon runs as user-level service.
- **pynvml** for GPU metrics, not `nvidia-smi` subprocess.
- **aiogram 3** for Telegram, not python-telegram-bot.
- **JSONL** for v1 storage, not SQLite.
- **No new top-level dependencies** without discussion. Keep the install footprint small.

## Security model

- Telegram user ID whitelist (config-enforced)
- Command allowlist per user
- Script paths must be absolute and on an allowlist
- Unix socket: `chmod 600`
- Config file with Telegram token must never be committed (see `.gitignore`)

## Implementation phases

1. Foundation — watcher, event engine, config, JSONL log, basic CLI ← *in progress*
2. Telegram channel — notifications
3. Bidirectional control — Telegram commands + IPC transport
4. Daemon installation — systemd --user / launchd / Windows SCM
5. Plugin system + `qara-ml` plugin (pynvml, loss parsing)
6. Polish + PyPI release

## Code style

- Line length: 100 (ruff enforced)
- `ruff.lint` selects: E, F, I, UP, B, SIM, ANN (ANN101/102 ignored)
- mypy strict — all public functions need type annotations
- Async functions throughout; no blocking I/O on the event loop
