# qara — project plan

> **Purpose of this document:** A complete, implementation-ready project plan for the `qara` open-source tool. Use this file to instruct Claude Code during every phase of development. Each section is written to be copy-pasteable as a prompt context.

---

## 1. Project overview

**qara** is a cross-platform daemon that tracks running processes on your machine and notifies you — and lets you send commands back — through messaging platforms, starting with Telegram.

### Core value proposition
- Wrap any command: `qara run python train.py` → get notified on finish or crash
- Attach to an existing PID: `qara attach 18432` → same notifications
- Bidirectional: send `/kill`, `/status`, `/run <script>` from Telegram
- Plugin architecture: ML-specific metrics (GPU, loss, early stopping) via optional plugin
- Cross-platform: Linux, macOS, Windows from day one
- Runs as a system daemon (systemd / launchd / Windows SCM)

### What makes it different from existing tools
| Tool | Problem |
|---|---|
| Telewrap | Unmaintained, wrap-only, no attach |
| Knockknock | Decorator-only, no bidirectional control |
| TeleGrad | Keras/TF specific, unmaintained |
| ntfy.sh | One-way push only, no remote control |
| SysTamer | No plugin system, not on PyPI |

qara is maintained, general-purpose, bidirectional, extensible, and installable via `pip`.

---

## 2. Architecture

### High-level layers

```
┌─────────────────────────────────────────────┐
│               user layer                    │
│  Telegram bot  │  Slack (future)  │  OpenClaw (future)  │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│           notification bus                  │
│   Routes events → active channel adapters   │
└──────┬─────────────────────────┬────────────┘
       │ events                  │ commands
┌──────▼──────────────────────────────────────┐
│             core daemon                     │
│  ProcessWatcher │ EventEngine │ CommandHandler │
│  Config store (TOML + Pydantic)             │
└──────┬──────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────┐
│             plugin layer                    │
│  ML plugin (GPU/loss) │ Resource monitor │ Custom hooks │
└─────────────────────────────────────────────┘
```

### Key abstractions

**ProcessWatcher**
- Two modes: **spawn mode** (`qara run`) and **attach mode** (`qara attach`)
- **Spawn mode:** qara forks the process and owns its stdin/stdout/stderr pipes. Streams stdout/stderr line by line via asyncio. Full event set available.
- **Attach mode:** qara cannot intercept the stdout/stderr of a process it did not spawn. Only PID-level events are available: `ProcessStarted`, `ProcessFinished`, `ProcessCrashed`. `StdoutLine`/`StderrLine` are NOT emitted in attach mode. `/logs` is unavailable for attached processes.
- Emits typed events: `ProcessStarted`, `ProcessFinished(exit_code, duration)`, `ProcessCrashed(exit_code, stderr_tail)`, `StdoutLine(text)` *(spawn mode only)*, `StderrLine(text)` *(spawn mode only)*
- Uses `psutil` for PID existence checks, CPU/RAM sampling
- Stores the original `argv: list[str]` from spawn mode (required for `/restart`)
- Maintains an in-memory ring buffer of the last 1000 stdout+stderr lines per process (used by `/logs`)
- Handles PID recycling race: if the PID exits between `qara attach` and watcher start, emit `ProcessCrashed` immediately

**EventEngine**
- Internal async pub/sub
- Watcher and plugins publish events here
- NotificationBus subscribes and routes to channels
- No direct coupling between watchers and channels

**NotificationBus**
- Holds a registry of `BaseChannel` adapters
- **Filters before routing:** `StdoutLine` and `StderrLine` events are NOT forwarded to channels by default — they are only consumed by plugins and the in-memory log buffer. Only `ProcessStarted`, `ProcessFinished`, `ProcessCrashed`, and `PluginMetric` (summary only, on finish) are routed to channels.
- On each routable event, calls `channel.send(event)` for all registered adapters
- Telegram is the first adapter; Slack/Discord/OpenClaw are future adapters

**CommandHandler**
- Receives commands from channels (e.g. Telegram `/kill 1234`)
- Validates against allowlist from config
- Authorizes by Telegram user ID (whitelist in config)
- Executes: kill process, restart, run whitelisted script

**BaseChannel (abstract)**
```python
class BaseChannel(ABC):
    @abstractmethod
    async def send(self, event: BaseEvent) -> None: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    async def receive_command(self, command: str, params: dict) -> None:
        """Override to handle inbound commands from this channel."""
        pass
```
Adding a new channel = implement this interface, register in config. The `receive_command` hook lets channel adapters (e.g. aiogram handlers) dispatch into CommandHandler.

**WatcherRegistry**
- The daemon owns a `WatcherRegistry` (dict mapping pid → ProcessWatcher)
- Enforces unique PIDs; duplicate attach returns an error
- Names must be unique within the registry; collision raises an error at attach time
- Provides lookup by pid or name (for `/kill <name>`, `/restart <name>`)

### IPC (CLI ↔ daemon)
- Linux/macOS: Unix domain socket at `{platformdirs.user_runtime_dir}/qara/daemon.sock`
- Windows: named pipe `\\.\pipe\qara`. Access is restricted via security descriptor (`win32security`) to the creating user's SID — equivalent to `chmod 600` on Unix.
- Thin `transport.py` module abstracts both; CLI and future OpenClaw use this
- Protocol: newline-delimited JSON messages
- CLI-side: 10-second timeout on all IPC calls; connection refused = daemon not running, print actionable message and exit 1
- **Daemon singleton:** on startup, write a PID file at `{platformdirs.user_runtime_dir}/qara/daemon.pid`. On shutdown, remove it. On startup, if the socket file exists, attempt a `ping`; if it responds, refuse to start (daemon already running); if it doesn't respond, remove the stale socket and PID file and continue.

---

## 3. Repository structure

```
qara/
├── pyproject.toml
├── .python-version              # pinned via uv (3.11)
├── .pre-commit-config.yaml
├── README.md
├── CHANGELOG.md
├── LICENSE                      # MIT
│
├── src/
│   └── qara/
│       ├── __init__.py
│       ├── __main__.py          # entry point: python -m qara
│       ├── cli.py               # Typer CLI (run, attach, status, install, etc.)
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── daemon.py        # main async event loop, wires everything together
│       │   ├── watcher.py       # ProcessWatcher class
│       │   ├── events.py        # typed event dataclasses
│       │   ├── event_engine.py  # internal pub/sub
│       │   ├── bus.py           # NotificationBus
│       │   └── command_handler.py
│       │
│       ├── channels/
│       │   ├── __init__.py
│       │   ├── base.py          # BaseChannel ABC
│       │   └── telegram.py      # aiogram 3 adapter
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   ├── schema.py        # Pydantic v2 models
│       │   └── loader.py        # TOML loader + platformdirs paths
│       │
│       ├── storage/
│       │   ├── __init__.py
│       │   └── log.py           # append-only JSONL writer + tail reader
│       │
│       ├── platform/
│       │   ├── __init__.py
│       │   ├── detector.py      # sys.platform → enum
│       │   ├── systemd.py       # Linux: write + install unit file
│       │   ├── launchd.py       # macOS: write + load plist
│       │   └── windows_scm.py   # Windows: pywin32 SCM registration
│       │
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── server.py        # daemon-side socket server
│       │   └── client.py        # CLI-side socket client
│       │
│       └── plugins/
│           ├── __init__.py
│           └── base.py          # BasePlugin ABC + entry point loader
│
├── plugins/
│   └── ml/                      # Optional ML plugin (separate installable)
│       ├── pyproject.toml
│       └── src/
│           └── qara_ml/
│               ├── __init__.py
│               ├── gpu.py       # pynvml GPU metrics
│               └── loss.py      # stdout log parsing for loss/metrics
│
└── tests/
    ├── conftest.py
    ├── core/
    │   ├── test_watcher.py
    │   ├── test_event_engine.py
    │   └── test_command_handler.py
    ├── channels/
    │   └── test_telegram.py
    ├── config/
    │   └── test_schema.py
    ├── platform/
    │   └── test_installer.py
    ├── storage/
    │   └── test_log.py
    └── transport/
        └── test_ipc.py
```

---

## 4. Full tech stack

### Tooling
| Tool | Version | Role |
|---|---|---|
| `uv` | latest | Package manager, venv, Python version pinning |
| `ruff` | latest | Linter + formatter (replaces flake8 + black + isort) |
| `mypy` | latest | Static type checking, strict mode |
| `pre-commit` | latest | Git hooks: ruff + mypy + tests before commit |
| GitHub Actions | — | CI: lint + type check + test matrix (Linux/macOS/Windows) |

### Core runtime
| Library | Version | Role |
|---|---|---|
| Python | 3.11+ | Language; `tomllib` stdlib, required by aiogram 3 |
| `asyncio` | stdlib | Concurrency: watch N processes + bot simultaneously |
| `psutil` | latest | Cross-platform PID tracking, CPU/RAM metrics |
| `pydantic` | v2 | Config validation, typed settings, Rust-backed |
| `platformdirs` | latest | Cross-platform config/log/runtime paths |

### CLI & UX
| Library | Role |
|---|---|
| `typer` | CLI framework, type-hint driven, auto `--help` |
| `rich` | Terminal UI: tables, live panels, colored logs |

### Telegram integration
| Library | Role |
|---|---|
| `aiogram` | v3, async-native Telegram bot framework |

Rationale: aiogram 3 was designed async-first. `python-telegram-bot` has async bolted onto a synchronous core. Since the entire daemon is asyncio-native, aiogram is the correct choice.

### Storage
| Mechanism | Role |
|---|---|
| Append-only JSONL file | One line per completed run; zero dependencies |

No database in v1. Each completed run appends a single JSON line to `{platformdirs.user_log_dir}/qara/runs.jsonl`. Readable with `tail`, parseable by any tool, survives daemon restarts. The `/history` bot command reads the last N lines of this file.

If structured querying becomes a real user need post-launch, a SQLite layer (`aiosqlite` + `sqlite-utils`) can be added in v2 without changing any other code — the log file becomes the migration source.

### Plugin system
- Discovery via `importlib.metadata` entry points (stdlib, Python 3.9+)
- Plugins declare: `[project.entry-points."qara.plugins"] ml = "qara_ml:MLPlugin"`
- Core loads all registered plugins at daemon start, zero custom loader code

### ML plugin dependencies
| Library | Role |
|---|---|
| `pynvml` | Official NVML Python bindings (GPU util, VRAM, temp) |

`pynvml` queries the GPU directly — no subprocess call to `nvidia-smi`. Faster and more reliable.

### Daemon distribution
| Platform | Mechanism | Library |
|---|---|---|
| Linux | systemd unit file | none (file write + subprocess `systemctl`) |
| macOS | launchd plist | none (file write + subprocess `launchctl`) |
| Windows | Service Control Manager | `pywin32` (optional dep) |

`pywin32` is declared as `[project.optional-dependencies] windows = ["pywin32"]`.
Windows users: `pip install qara[windows]`
Linux/macOS users: `pip install qara`

### Config format
- TOML, parsed with stdlib `tomllib` (Python 3.11+)
- Config path: `{platformdirs.user_config_dir}/qara/config.toml`
- Validated on load by Pydantic v2 models

---

## 5. Configuration schema

Full annotated `config.toml`:

```toml
[daemon]
log_level = "INFO"                    # DEBUG | INFO | WARNING | ERROR
socket_path = ""                      # override default; empty = platformdirs default
history_file = ""                     # override default JSONL path; empty = platformdirs default

[telegram]
bot_token = "YOUR_BOT_TOKEN"
allowed_user_ids = [123456789]        # whitelist; bot ignores all other users

[telegram.notifications]
on_start   = true
on_finish  = true
on_crash   = true
stdout_tail_lines = 20               # lines to include in crash notification

[commands]
# Explicit allowlist — no arbitrary shell execution
# NOTE: "run" is intentionally absent from the default. Add it only after
# populating allowed_scripts. Enabling "run" without allowed_scripts is a no-op.
enabled = ["status", "kill", "restart"]
# alias → absolute path mapping. Users send "/run eval" not a full path.
# Paths are resolved with Path.resolve() before comparison (prevents traversal).
[commands.allowed_scripts]
eval   = "/home/yera/scripts/eval.py"
cleanup = "/home/yera/scripts/cleanup.sh"

[plugins]
enabled = ["ml"]                     # loaded by entry point name

[plugins.ml]
gpu_poll_interval_seconds = 5
report_on_finish = true              # send GPU summary when process ends
loss_pattern = ""                    # regex to parse loss from stdout; empty = use default pattern
```

### Pydantic schema (implement in `config/schema.py`)

```python
from pydantic import BaseModel, field_validator
from typing import Literal

class DaemonConfig(BaseModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    socket_path: str = ""
    history_file: str = ""  # path to JSONL log; empty = platformdirs default

class TelegramNotificationsConfig(BaseModel):
    on_start: bool = True
    on_finish: bool = True
    on_crash: bool = True
    stdout_tail_lines: int = 20

class TelegramConfig(BaseModel):
    bot_token: str
    allowed_user_ids: list[int]
    notifications: TelegramNotificationsConfig = TelegramNotificationsConfig()

class CommandsConfig(BaseModel):
    enabled: list[str] = ["status", "kill", "restart"]
    allowed_scripts: dict[str, str] = {}  # alias → absolute path
    kill_timeout_seconds: int = 10

class MLPluginConfig(BaseModel):
    gpu_poll_interval_seconds: int = 5
    report_on_finish: bool = True
    loss_pattern: str = ""

class PluginsConfig(BaseModel):
    enabled: list[str] = []
    ml: MLPluginConfig = MLPluginConfig()

class QaraConfig(BaseModel):
    daemon: DaemonConfig = DaemonConfig()
    telegram: TelegramConfig
    commands: CommandsConfig = CommandsConfig()
    plugins: PluginsConfig = PluginsConfig()
```

---

## 6. Events system

All events in `core/events.py`. Use `dataclasses` with `frozen=True`.

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

class EventType(Enum):
    PROCESS_STARTED  = "process_started"
    PROCESS_FINISHED = "process_finished"
    PROCESS_CRASHED  = "process_crashed"
    STDOUT_LINE      = "stdout_line"
    STDERR_LINE      = "stderr_line"
    PLUGIN_METRIC    = "plugin_metric"

@dataclass(frozen=True)
class BaseEvent:
    pid: int
    name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(frozen=True)
class ProcessStarted(BaseEvent):
    argv: list[str] = field(default_factory=list)  # full command as list; required for /restart

@dataclass(frozen=True)
class ProcessFinished(BaseEvent):
    exit_code: int = 0
    duration_seconds: float = 0.0

@dataclass(frozen=True)
class ProcessCrashed(BaseEvent):
    exit_code: int = -1
    stderr_tail: str = ""
    duration_seconds: float = 0.0

@dataclass(frozen=True)
class StdoutLine(BaseEvent):
    text: str = ""

@dataclass(frozen=True)
class StderrLine(BaseEvent):
    text: str = ""

@dataclass(frozen=True)
class PluginMetric(BaseEvent):
    plugin_name: str = ""
    key: str = ""
    value: float = 0.0
    unit: str = ""
```

---

## 7. CLI interface

Implemented with Typer in `cli.py`. Commands:

```bash
# Wrap and run a command — qara spawns it
qara run python train.py --name "cifar10-v3"
qara run -- ./long_script.sh --arg1 val1

# Attach to existing PID
qara attach 18432 --name "my-training"

# Status of all watched processes
qara status

# Process history from DB
qara history --last 20

# Daemon management
# NOTE: "qara daemon start" has two distinct behaviors:
#   1. When called by systemd/launchd ExecStart → starts the daemon process in-process (foreground)
#   2. When called by a user in a terminal → forks the daemon to the background
# These are differentiated by a --foreground flag (set by the service unit file).
qara daemon start [--foreground]
qara daemon stop      # sends shutdown signal via IPC; daemon finishes watched processes or abandons them per --on-stop policy
qara daemon restart
qara daemon status

# One-time installation as system service
qara install --daemon
qara uninstall --daemon

# Config
qara config init       # write default config.toml to platformdirs path
qara config validate   # parse + validate current config, report errors
qara config path       # print config file location
```

**Key CLI flags:**
- `--notify` — comma-separated: `on-finish,on-crash,on-start` (default: `on-finish,on-crash`). Hyphens are normalized to underscores before comparing against config keys.
- `--name` — human label for the process (used in notifications and log). Names must be unique within the daemon; duplicate names are rejected with an error.
- `--no-stdout` — suppress stdout/stderr forwarding to the terminal. StdoutLine/StderrLine events are still emitted internally (plugins and `/logs` still work).
- `--format json` — machine-readable output for `status` and `history`

---

## 8. Telegram bot commands

Registered as aiogram handlers. All commands check `message.from_user.id in config.telegram.allowed_user_ids` before executing.

| Command | Description |
|---|---|
| `/start` | Welcome message, list available commands |
| `/status` | List all currently watched processes with PID, name, runtime, CPU%, RAM |
| `/history [n]` | Last n completed runs (default 20) from JSONL log |
| `/kill <pid_or_name>` | Send SIGTERM; SIGKILL after 10s if still running |
| `/restart <pid_or_name>` | Kill + re-run same command (spawn mode only; errors on attached PIDs) |
| `/run <alias>` | Run a whitelisted script by its configured alias |
| `/logs <pid_or_name> [n]` | Last n lines from stdout/stderr ring buffer (spawn mode only) |
| `/help` | Command reference |

**Notification message format (on finish):**
```
✅ Process finished
Name: cifar10-v3
PID: 18432
Exit code: 0
Duration: 2h 14m 33s
Last stdout:
  Epoch 50/50 - loss: 0.0341 - val_acc: 0.9712
```

**Notification message format (on crash):**
```
❌ Process crashed
Name: cifar10-v3
PID: 18432
Exit code: 137
Duration: 0h 03m 12s
Stderr tail:
  RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB
  ...
```

---

## 9. Security model

**This is critical.** The daemon executes processes and can kill them. The following rules are non-negotiable:

1. **Telegram user whitelist.** `allowed_user_ids` in config is checked on every command handler. Any message from an unlisted user ID is silently ignored (no error response — prevents enumeration).

2. **Command allowlist.** The `[commands] enabled` list controls which commands are active. `/run` is opt-in and disabled by default.

3. **Script allowlist.** `/run` only executes scripts explicitly listed in `[commands] allowed_scripts`. Absolute paths only. Comparison uses `Path(input).resolve() == Path(allowlist_entry).resolve()` — prevents `..` traversal and symlink confusion. The user sends a short script alias (e.g. `/run eval`); the config maps aliases to absolute paths: `allowed_scripts = {eval = "/home/yera/scripts/eval.py"}`. No basename matching, no glob, no shell expansion.

4. **No arbitrary shell execution.** CommandHandler uses `asyncio.create_subprocess_exec` (list form), never `shell=True`. The resolved script path is passed as a list element — no interpolation.

5. **Kill escalation.** `/kill` sends SIGTERM first. If the process has not exited after 10 seconds, sends SIGKILL. The timeout is configurable via `[commands] kill_timeout_seconds = 10`.

6. **Socket permissions.** Unix socket created with `chmod 600` — only the daemon owner can connect. The parent directory (`{user_runtime_dir}/qara/`) is created with `chmod 700`. On Linux, the systemd unit runs as the installing user, not root. On Windows, the named pipe security descriptor is set to the creating user's SID only.

7. **No root required.** Installation uses user-level systemd (`systemctl --user`) and user launchd agents. qara never needs or asks for sudo.

8. **Restart command scope.** `/restart` is only available for processes started via `qara run` (spawn mode). Attempting to restart an attached PID returns an error — qara does not know the original command.

9. **Unauthorized access logging.** While inbound commands from unlisted Telegram user IDs are silently ignored (no error response — prevents enumeration), all such attempts are written to the daemon log at WARNING level with the user ID and command. This enables the owner to detect a leaked bot token.

---

## 10. Platform daemon installation

Implemented in `platform/` directory. Entry point: `qara install --daemon`.

### Linux (systemd)

Writes to `~/.config/systemd/user/qara.service`:

```ini
[Unit]
Description=qara process monitor daemon
# network.target is a system unit and meaningless in --user scope.
# default.target is the correct anchor for user session services.
After=default.target

[Service]
Type=simple
ExecStart={sys.executable} -m qara daemon start --foreground
Restart=on-failure
RestartSec=5
Environment=QARA_CONFIG={config_path}

[Install]
WantedBy=default.target
```

Then runs:
```bash
systemctl --user daemon-reload
systemctl --user enable qara
systemctl --user start qara
```

### macOS (launchd)

Writes to `~/Library/LaunchAgents/com.qara.daemon.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.qara.daemon</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>-m</string>
    <string>qara</string>
    <string>daemon</string>
    <string>start</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QARA_CONFIG</key>
    <string>{config_path}</string>
  </dict>
</dict>
</plist>
```

Then runs:
```bash
# launchctl load is deprecated since macOS Ventura (13.x).
# Use bootstrap/bootout instead:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.qara.daemon.plist
# For uninstall: launchctl bootout gui/$(id -u) com.qara.daemon
```

### Windows (SCM via pywin32)

Uses `win32serviceutil` from `pywin32`. Registers qara as a Windows service with auto-start. Only installed when `qara[windows]` is used.

---

## 11. IPC protocol (CLI ↔ daemon)

Both sides use newline-delimited JSON over a socket.

### Request format
```json
{"id": "uuid4", "action": "status", "params": {}}
{"id": "uuid4", "action": "attach", "params": {"pid": 18432, "name": "training"}}
{"id": "uuid4", "action": "kill", "params": {"pid": 18432}}
```

### Response format
```json
{"id": "uuid4", "ok": true, "data": {...}}
{"id": "uuid4", "ok": false, "error": "Process 18432 not found"}
```

### Available actions
| Action | Params | Description |
|---|---|---|
| `status` | — | List all watched processes |
| `run` | `argv: list[str]`, `name?` | Daemon spawns the process and watches it |
| `attach` | `pid`, `name?` | Attach watcher to existing PID (no stdout/stderr streaming) |
| `detach` | `pid` | Stop watching a PID |
| `kill` | `pid` | Send SIGTERM; SIGKILL after 10s if still running |
| `history` | `limit?` | Return last N run records from JSONL log |
| `logs` | `pid_or_name`, `n?` | Return last n lines from in-memory ring buffer (spawn mode only) |
| `ping` | — | Health check; daemon responds `{"pong": true}` |

---

## 12. Plugin system

### BasePlugin ABC (`plugins/base.py`)

```python
from abc import ABC, abstractmethod
from qara.core.events import BaseEvent

class BasePlugin(ABC):
    name: str = "unnamed"

    @abstractmethod
    async def on_start(self, pid: int, name: str) -> None:
        """Called when a process starts being watched."""
        ...

    @abstractmethod
    async def on_event(self, event: BaseEvent) -> None:
        """Called for every event from the watcher."""
        ...

    @abstractmethod
    async def on_finish(self, pid: int) -> dict[str, str]:
        """Called when process ends.
        Return a dict of label → value strings to append to the finish notification.
        Example: {"GPU summary": "Peak VRAM: 7.8 GB\nAvg util: 94%"}
        The daemon formats each key-value pair as a notification section.
        Return {} if no metrics to report.
        """
        ...

    async def setup(self) -> None:
        """Optional: called once at daemon start."""
        pass

    async def teardown(self) -> None:
        """Optional: called once at daemon shutdown."""
        pass
```

### Entry point registration (in plugin's `pyproject.toml`)

```toml
[project.entry-points."qara.plugins"]
ml = "qara_ml:MLPlugin"
```

### Plugin loader (called at daemon start)

```python
from importlib.metadata import entry_points

def load_plugins(enabled: list[str]) -> list[BasePlugin]:
    eps = entry_points(group="qara.plugins")
    plugins = []
    for ep in eps:
        if ep.name in enabled:
            cls = ep.load()
            plugins.append(cls())
    return plugins
```

---

## 13. ML plugin design

Located in `plugins/ml/`. Installed separately: `pip install qara-ml`.

### GPU metrics (`gpu.py`)
- Uses `pynvml` — official NVML Python bindings, no `nvidia-smi` subprocess
- `setup()` calls `nvmlInit()`; if it raises `NVMLError` (no GPU, AMD GPU, missing driver), the plugin disables itself gracefully and logs a WARNING — it does not crash the daemon
- Polling loop is an asyncio `Task` stored per PID in a dict; cancelled in `on_finish`
- Polls every `gpu_poll_interval_seconds` (default: 5)
- Collects: GPU utilization %, VRAM used/total, temperature °C
- Emits `PluginMetric` events for each metric
- On process finish: cancels the polling task, then returns summary dict with peak VRAM, avg GPU util, peak temp

### Loss parsing (`loss.py`)
- Reads `StdoutLine` events
- Matches against `loss_pattern` from config — **this is a regex**, not a format string
- Default pattern: `r"(?i)(?:train_?)?loss[=:\s]+([0-9]+\.?[0-9]*(?:e[-+]?\d+)?)"` — matches common formats like `loss: 0.0341`, `Loss=0.034`, `train_loss: 0.034`
- Stores last N loss values per PID; on finish, reports final loss + best loss + epoch

### ML plugin finish notification (appended to base notification)
```
GPU summary:
  Peak VRAM: 7.8 GB / 8.0 GB
  Avg GPU util: 94%
  Peak temp: 81°C

Training summary:
  Final loss: 0.0341
  Best loss: 0.0298 (epoch 47)
```

---

## 14. Storage — append-only JSONL log

No database in v1. Completed runs are written as single JSON lines to:

```
{platformdirs.user_log_dir}/qara/runs.jsonl
```

### Log entry format

```json
{"name": "cifar10-v3", "pid": 18432, "command": "python train.py", "exit_code": 0, "duration_s": 8073.4, "started_at": "2025-03-23T12:07:27Z", "finished_at": "2025-03-23T14:22:01Z", "platform": "linux", "host": "yera-workstation"}
```

### `storage/log.py` interface

```python
import json
import threading
from pathlib import Path

_lock = threading.Lock()  # serialize concurrent appends from thread pool

def _log_path() -> Path:
    from platformdirs import user_log_path  # returns Path, not str
    p = user_log_path("qara")
    p.mkdir(parents=True, exist_ok=True)
    return p / "runs.jsonl"

def append_run(record: dict) -> None:
    """Append one completed run as a JSON line.
    Blocking — must be called via loop.run_in_executor, never directly from async code.
    Thread-safe via module-level lock.
    """
    with _lock:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

def tail_runs(n: int = 20) -> list[dict]:
    """Return last n run records, newest last.
    Reads from the end of the file in chunks to avoid loading the full file into memory.
    Skips and logs any malformed JSON lines rather than crashing.
    """
    path = _log_path()
    if not path.exists():
        return []
    # Efficient reverse-read: read in 8KB chunks from EOF
    results: list[dict] = []
    with path.open("rb") as f:
        f.seek(0, 2)
        remaining = f.tell()
        buffer = b""
        while remaining > 0 and len(results) < n:
            chunk_size = min(8192, remaining)
            remaining -= chunk_size
            f.seek(remaining)
            buffer = f.read(chunk_size) + buffer
            lines = buffer.split(b"\n")
            buffer = lines[0]  # possibly incomplete first line
            for line in reversed(lines[1:]):
                if line.strip():
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # log warning in real implementation
                    if len(results) == n:
                        break
    return list(reversed(results))
```

`append_run` is dispatched via `loop.run_in_executor(None, append_run, record)` from the async event handler. The module-level lock makes concurrent appends safe.

### `/history` bot command

Calls `tail_runs(n)` and formats the result as a Telegram message. The JSONL file is also directly inspectable from the terminal:

```bash
# Linux: user_log_path("qara") → ~/.local/state/qara/runs.jsonl (XDG_STATE_HOME)
tail -n 20 ~/.local/state/qara/runs.jsonl | python -m json.tool
# macOS: ~/Library/Logs/qara/runs.jsonl
```

### Future upgrade path

If structured querying is needed post-v1, the JSONL file is the migration source — import each line into SQLite. No other code changes required since nothing else depends on the storage layer directly.

---

## 15. `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qara"
version = "0.1.0"
description = "Cross-platform process monitor with Telegram notifications and remote control"
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.11"
keywords = ["process", "monitor", "telegram", "notifications", "ml", "training"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: System :: Monitoring",
]

dependencies = [
    "aiogram>=3.0",
    "platformdirs>=4.0",
    "psutil>=5.9",
    "pydantic>=2.0",
    "rich>=13.0",
    "typer>=0.12",
]

[project.optional-dependencies]
windows = ["pywin32"]
ml      = ["pynvml>=11.0"]
dev     = [
    "mypy>=1.0",
    "pre-commit",
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[project.scripts]
qara = "qara.cli:app"

# Note: [project.entry-points."qara.plugins"] is intentionally absent from the
# core package — the core registers no plugins. Third-party plugins declare
# this section in their own pyproject.toml.

[tool.uv]
# uv dev-dependencies is the canonical source; [project.optional-dependencies] dev
# is kept only for pip compatibility. Keep them in sync.
dev-dependencies = [
    "mypy>=1.0",
    "pre-commit",
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "ANN"]
ignore = ["ANN101", "ANN102"]

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = false

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["src/qara"]
```

---

## 16. GitHub Actions CI

File: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-type:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src/

  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.11", "3.12"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install ${{ matrix.python }}
      - run: uv sync --dev
      - run: uv run pytest --tb=short
```

---

## 17. Implementation phases

### Phase 1 — Foundation (implement first)
Goal: daemon runs, watches a process, writes completed runs to JSONL log.

- [ ] `pyproject.toml` and repo structure
- [ ] `config/schema.py` — Pydantic models
- [ ] `config/loader.py` — TOML loading + platformdirs paths
- [ ] `core/events.py` — typed event dataclasses
- [ ] `core/event_engine.py` — async pub/sub
- [ ] `core/watcher.py` — ProcessWatcher (spawn + attach modes)
- [ ] `storage/log.py` — JSONL append writer + tail reader
- [ ] `core/daemon.py` — wires watcher → event engine → log writer
- [ ] `cli.py` — `run` and `attach` commands (no bot yet)
- [ ] Tests: watcher, event engine, config loading, log writer

### Phase 2 — Telegram channel
Goal: notifications work end-to-end.

- [ ] `channels/base.py` — BaseChannel ABC
- [ ] `channels/telegram.py` — aiogram 3 adapter
  - Send notifications for `ProcessStarted`, `ProcessFinished`, `ProcessCrashed`
  - Format messages with Rich-like markdown for Telegram
- [ ] `core/bus.py` — NotificationBus routing events to channels
- [ ] Wire Telegram into daemon startup
- [ ] `cli.py` — add `config init` and `config validate`
- [ ] Tests: mock bot, test notification formatting

### Phase 3 — Bidirectional control
Goal: Telegram commands work, security model enforced.

- [ ] `core/command_handler.py` — allowlist validation + execution
- [ ] aiogram handlers: `/status`, `/kill`, `/restart`, `/run`, `/history`, `/logs`
- [ ] User ID whitelist check middleware in aiogram
- [ ] IPC transport — `transport/server.py` + `transport/client.py`
- [ ] Wire CLI `status`, `attach`, `kill` through IPC to running daemon
- [ ] Tests: command handler security, IPC round-trip

### Phase 4 — Daemon installation
Goal: `qara install --daemon` works on all three platforms.

- [ ] `platform/detector.py`
- [ ] `platform/systemd.py` — generate + install unit file
- [ ] `platform/launchd.py` — generate + load plist
- [ ] `platform/windows_scm.py` — pywin32 SCM (conditional import)
- [ ] `cli.py` — `install`, `uninstall`, `daemon start/stop/restart/status`
- [ ] Tests: generated file content (no actual systemctl calls in CI)

### Phase 5 — Plugin system + ML plugin
Goal: `pip install qara-ml` adds GPU metrics to notifications.

- [ ] `plugins/base.py` — BasePlugin ABC
- [ ] `plugins/__init__.py` — entry point loader
- [ ] Wire plugin lifecycle into daemon (setup, on_start, on_event, on_finish, teardown)
- [ ] `plugins/ml/gpu.py` — pynvml polling loop
- [ ] `plugins/ml/loss.py` — stdout pattern matching
- [ ] ML plugin `pyproject.toml` as separate package
- [ ] Tests: mock pynvml, test metric emission and formatting

### Phase 6 — Polish + OSS release
Goal: ready to publish to PyPI and announce.

- [ ] `README.md` — quick start, usage examples, config reference
- [ ] `CHANGELOG.md`
- [ ] GitHub issue templates (bug, feature, plugin)
- [ ] `CONTRIBUTING.md`
- [ ] PyPI publish workflow (`.github/workflows/publish.yml`)
- [ ] Versioning: `v0.1.0` tag triggers publish
- [ ] `qara config init` generates a commented example config
- [ ] `--format json` on `status` and `history` for scripting/OpenClaw

---

## 18. Key decisions log

This section records all non-obvious decisions and their rationale. Reference this when Claude Code suggests alternatives.

| Decision | Choice | Rejected alternative | Reason |
|---|---|---|---|
| Telegram library | `aiogram 3` | `python-telegram-bot` | aiogram is async-native; ptb has async bolted on. Daemon is 100% asyncio. |
| Package manager | `uv` | `poetry` | uv is 10-100× faster, single binary, replaces pyenv too. Poetry is slower and more complex. |
| Linter/formatter | `ruff` | `flake8 + black + isort` | Single tool, same Astral team as uv, significantly faster. |
| Config format | `TOML` | `YAML` | `tomllib` is Python 3.11 stdlib. YAML indentation errors are a common source of bugs. |
| Storage (v1) | Append-only JSONL file | `aiosqlite + sqlite-utils`, SQLAlchemy | Daemon is a notification tool, not a database. JSONL is zero-dep, debuggable with `tail`, and sufficient for `/history`. DB added in v2 only if users need structured queries. |
| ORM | None | SQLAlchemy, Tortoise | No DB in v1. If DB is added in v2, sqlite-utils is sufficient — two tables don't need an ORM. |
| Plugin system | `importlib.metadata` entry points | Custom plugin loader | Standard Python mechanism. Third-party plugins install via pip, zero custom loader code. |
| GPU metrics | `pynvml` | `subprocess nvidia-smi` | pynvml is the official NVML binding: no subprocess overhead, structured data, no parsing. |
| Platform dirs | `platformdirs` | Manual `sys.platform` branching | platformdirs handles all platform path conventions correctly. No `if sys.platform` in core code. |
| Daemon scope | User-level (no root) | System-level (root) | `systemctl --user`, user launchd agents. qara never needs sudo. |
| IPC protocol | Newline-delimited JSON | gRPC / msgpack | Simplest correct choice. Debuggable with `nc`. No compiled schemas needed. |
| Shell execution | `asyncio.create_subprocess_exec` (list) | `shell=True` | `shell=True` is a security liability. List form prevents injection entirely. |
| Windows daemon | `pywin32` (optional dep) | `subprocess sc.exe` | pywin32 is the canonical Windows service API from Python. sc.exe parsing is fragile. |
| Script allowlist format | `dict[alias → path]` | `list[path]` | Users send short aliases from Telegram (e.g. `/run eval`); full paths as Telegram commands are poor UX. |
| Attach mode stdout | Not supported | `/proc/PID/fd/1` | qara cannot intercept stdout of a process it didn't spawn in a cross-platform, reliable way. Attach mode is explicitly limited to PID-level events. |
| datetime in events | `datetime.now(timezone.utc)` | `datetime.utcnow()` | `utcnow()` deprecated in Python 3.12, produces naive datetimes inconsistent with UTC timestamps in JSONL. |
| ProcessStarted.argv | `list[str]` | `command: str` | `/restart` re-executes via `create_subprocess_exec` which requires a list. A string would require shell-style parsing, reintroducing injection risk. |
| JSONL reverse-read | Chunked from EOF | `read_text().splitlines()` | Full-file read is unbounded memory for long-running installations. |
| Daemon singleton | PID file + socket ping | None | Prevents two daemon instances binding the same socket path. |

---

## 19. OpenClaw compatibility notes

For future integration, keep these hooks in place from day one:

1. The IPC transport (`transport/`) is the integration point. OpenClaw connects as a CLI client — no changes to daemon needed.
2. `qara status --format json` returns machine-readable process state. OpenClaw can parse this as a tool response.
3. `qara history --format json` reads the JSONL log and returns structured run history. Useful for NLP queries like "how long did my last training take?"
4. Keep all notifications text-first (no image attachments) so they work over any channel including future OpenClaw text interface.
5. The `BaseChannel` ABC is already designed for OpenClaw: implement `OpenClawChannel(BaseChannel)` and register it in config.

---

## 20. Naming and branding

- **Package name:** `qara` (PyPI: `qara`)
- **CLI binary:** `qara`
- **ML plugin package:** `qara-ml` (PyPI: `qara-ml`)
- **GitHub org/repo:** `qara/qara` (or your personal account)
- **Bot username:** `@qara_bot` (register on BotFather)
- **License:** MIT

Check PyPI and GitHub for name availability before starting.
