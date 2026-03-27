import tomllib
from pathlib import Path

from platformdirs import user_config_path, user_log_path, user_runtime_path

from qara.config.schema import QaraConfig


def config_path() -> Path:
    return user_config_path("qara") / "config.toml"

def log_path() -> Path:
    return user_log_path("qara") / "runs.jsonl"

def socket_path() -> Path:
    return user_runtime_path("qara") / "daemon.pid"

def load_config(path: Path | None = None) -> QaraConfig:
    """Load and validate config from TOML. Raises FileNotFoundError or ValidationError."""
    p = path or config_path()
    with p.open("rb") as f:
        raw = tomllib.load(f)
    return QaraConfig.model_validate(raw)