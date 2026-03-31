import asyncio
import logging
import sys

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from qara.config.loader import load_config, socket_path
from qara.config.schema import QaraConfig
from qara.transport.client import IPCClient

app = typer.Typer(name="qara", help="Process monitor with Telegram notifications.")
daemon_app = typer.Typer(help="Manage the qara daemon.")
config_app = typer.Typer(help="Manage qara configuration.")
app.add_typer(daemon_app, name="daemon")
app.add_typer(config_app, name="config")

console = Console()


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )


def _load_config_or_exit() -> QaraConfig:
    from pydantic import ValidationError
    from qara.config.loader import config_path
    try:
        return load_config()
    except FileNotFoundError:
        typer.echo(
            f"[error] Config not found: {config_path()}\n"
            "Run `qara config init` to create one.",
            err=True,
        )
        raise typer.Exit(1)
    except ValidationError as e:
        typer.echo(f"[error] Config is invalid:\n{e}", err=True)
        raise typer.Exit(1)


def _run_ipc(action: str, params: dict | None = None) -> dict:
    cfg = _load_config_or_exit()
    client = IPCClient(str(socket_path()))
    try:
        return asyncio.run(client.send(action, params))
    except RuntimeError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Process commands
# ---------------------------------------------------------------------------

@app.command()
def run(
    argv: list[str] = typer.Argument(..., help="Command and arguments to run"),
    name: str = typer.Option("", "--name", "-n", help="Human label for this process"),
) -> None:
    """Spawn a process via the daemon and watch it."""
    label = name or argv[0]
    result = _run_ipc("run", {"argv": argv, "name": label})
    if result.get("ok"):
        data = result["data"]
        typer.echo(f"Watching PID {data['pid']} as '{data['name']}'")
    else:
        typer.echo(f"[error] {result.get('error')}", err=True)
        raise typer.Exit(1)


@app.command()
def attach(
    pid: int = typer.Argument(..., help="PID to attach to"),
    name: str = typer.Option("", "--name", "-n", help="Human label"),
) -> None:
    """Attach to an existing process."""
    label = name or str(pid)
    result = _run_ipc("attach", {"pid": pid, "name": label})
    if result.get("ok"):
        typer.echo(f"Attached to PID {pid} as '{label}'")
    else:
        typer.echo(f"[error] {result.get('error')}", err=True)
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """List all currently watched processes."""
    result = _run_ipc("status")
    if not result.get("ok"):
        typer.echo(f"[error] {result.get('error')}", err=True)
        raise typer.Exit(1)
    entries = result["data"]
    if not entries:
        typer.echo("No processes currently watched.")
        return
    table = Table("PID", "Name", "Mode")
    for e in entries:
        table.add_row(str(e["pid"]), e["name"], e["mode"])
    console.print(table)


@app.command()
def history(last: int = typer.Option(20, "--last", "-n")) -> None:
    """Show recent completed runs."""
    result = _run_ipc("history", {"limit": last})
    if not result.get("ok"):
        typer.echo(f"[error] {result.get('error')}", err=True)
        raise typer.Exit(1)
    runs = result["data"]
    if not runs:
        typer.echo("No runs recorded yet.")
        return
    table = Table("Name", "PID", "Exit", "Duration (s)", "Finished")
    for r in runs:
        table.add_row(
            str(r.get("name")),
            str(r.get("pid")),
            str(r.get("exit_code")),
            f"{r.get('duration_seconds', 0):.1f}",
            str(r.get("finished_at", ""))[:19],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Daemon commands
# ---------------------------------------------------------------------------

@daemon_app.command("start")
def daemon_start(
    foreground: bool = typer.Option(False, "--foreground", help="Run in foreground (used by systemd/launchd)"),
) -> None:
    """Start the qara daemon."""
    cfg = _load_config_or_exit()
    _setup_logging(cfg.daemon.log_level)

    if foreground:
        from qara.core.daemon import Daemon
        asyncio.run(Daemon(cfg).run_forever())
    else:
        import os
        import subprocess
        from pathlib import Path
        from platformdirs import user_log_path

        log_file = user_log_path("qara") / "daemon.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Use the qara entry point script from the same venv as the current
        # executable — more reliable than -m qara in a detached process.
        qara_bin = Path(sys.executable).parent / "qara"
        cmd = [str(qara_bin), "daemon", "start", "--foreground"]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"  # ensure output is flushed before any crash

        with log_file.open("w") as lf:
            proc = subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=env,
            )
        typer.echo(f"Daemon started in background (PID {proc.pid})")
        typer.echo(f"Logs: {log_file}")


@daemon_app.command("stop")
def daemon_stop() -> None:
    """Stop the running daemon."""
    result = _run_ipc("ping")  # just to check it's running
    if not result.get("ok"):
        typer.echo("Daemon does not appear to be running.")
        raise typer.Exit(1)
    import signal, os
    from qara.config.loader import pid_file_path
    pid_file = pid_file_path()
    if not pid_file.exists():
        typer.echo("PID file not found.")
        raise typer.Exit(1)
    pid = int(pid_file.read_text().strip())
    os.kill(pid, signal.SIGTERM)
    typer.echo(f"Sent SIGTERM to daemon (PID {pid})")


@daemon_app.command("status")
def daemon_status() -> None:
    """Check if the daemon is running."""
    result = _run_ipc("ping")
    if result.get("ok"):
        typer.echo("Daemon is running.")
    else:
        typer.echo("Daemon is not running.")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Config commands
# ---------------------------------------------------------------------------

@config_app.command("init")
def config_init(force: bool = typer.Option(False, "--force")) -> None:
    """Create a default config.toml."""
    from qara.config.loader import config_path
    path = config_path()
    if path.exists() and not force:
        typer.echo(f"Config already exists: {path}\nUse --force to overwrite.")
        raise typer.Exit(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """\
[daemon]
log_level = "INFO"

[telegram]
bot_token = "YOUR_BOT_TOKEN_HERE"
allowed_user_ids = []  # add your Telegram user ID, e.g. [123456789]

[telegram.notifications]
on_start = true
on_finish = true
on_crash = true
stdout_tail_lines = 20

[commands]
enabled = ["status", "kill", "restart"]

[commands.allowed_scripts]
# eval = "/home/user/scripts/eval.py"

[plugins]
enabled = []
""",
        encoding="utf-8",
    )
    typer.echo(f"Config created: {path}\nEdit it to add your Telegram bot token.")


@config_app.command("path")
def config_path_cmd() -> None:
    """Print the config file path."""
    from qara.config.loader import config_path
    typer.echo(config_path())


@config_app.command("validate")
def config_validate() -> None:
    """Validate the current config."""
    _load_config_or_exit()
    typer.echo("Config is valid.")
