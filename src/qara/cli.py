import asyncio
import logging
import sys

import typer
from rich.logging import RichHandler

from qara.config.loader import QaraConfig
from qara.core.daemon import Daemon

app = typer.Typer(name="qara", help="Process monitor with Telegram notifications.")

def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],   
    )

def _load_config_or_exit() -> QaraConfig:
    from qara.config.loader import config_path, load_config
    from pydantic import ValidationError
    try:
        return load_config()
    except FileNotFoundError:
        typer.echo(
            f"[error] Config file not found: {config_path()}\n"
            "Run `qara config init` to create one, then add your Telegram bot token.",
            err=True,
        )
        raise typer.Exit(1)
    except ValidationError as e:
        typer.echo(f"[error] Config is invalid: \n{e}", err=True)
        raise typer.Exit(1)


@app.command()
def run(
    argv: list[str] = typer.Argument(..., help="Command and arguments to run"),
    name: str = typer.Option("", "--name", "-n", help="Human label for this process"),
    no_stdout: bool = typer.Option(False, "--no-stdout", help="Don't print output to terminal"),
) -> None:
    """Spawn a proces and watch it."""
    cfg = _load_config_or_exit()
    _setup_logging(cfg.daemon.log_level)

    label = name or argv[0]
    daemon = Daemon(cfg)

    if not no_stdout:
        # Echo output events to the terminal as they arrive
        original_subscribe = daemon.engine.subscribe

        async def _echo(event: object) -> None:
            from qara.core.events import StdoutLine, StderrLine
            if isinstance(event, StdoutLine):
                typer.echo(event.text)
            elif isinstance(event, StderrLine):
                typer.echo(event.text, err=True)
        
        daemon.engine.subscribe(_echo) # type: ignore[arg-type]

    asyncio.run(daemon.run_process(argv=argv, name=label))


@app.command()
def attach(
    pid: int = typer.Argument(..., help="PID to attach to"),
    name: str = typer.Option("", "--name", "-n", help="Human label for this process"),
) -> None:
    """Attach to an existing process and watch it."""
    cfg = _load_config_or_exit()
    _setup_logging(cfg.daemon.log_level)

    label = name or str(pid)
    daemon = Daemon(cfg)
    asyncio.run(daemon.attach_process(pid=pid, name=label))


config_app = typer.Typer(help="Manage qara configuration.")
app.add_typer(config_app, name="config")

@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing config"),
) -> None:
    """Create a default config.toml at the platfrom config path."""
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
    """Validate the current config file."""
    _load_config_or_exit()
    type.echo("Config is valid.")

if __name__ == "__main__":
    app()