"""Tests for config loading and schema validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from qara.config.loader import load_config
from qara.config.schema import (
    CommandsConfig,
    DaemonConfig,
    MLPluginConfig,
    PluginsConfig,
    QaraConfig,
    TelegramConfig,
    TelegramNotificationsConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_TOML = """\
[telegram]
bot_token = "test_token"
allowed_user_ids = [123456]
"""

_FULL_TOML = """\
[daemon]
log_level = "DEBUG"

[telegram]
bot_token = "abc:XYZ"
allowed_user_ids = [111, 222]

[telegram.notifications]
on_start = false
on_finish = true
on_crash = true
stdout_tail_lines = 50

[commands]
enabled = ["status", "kill"]
kill_timeout_seconds = 5

[plugins]
enabled = ["ml"]

[plugins.ml]
gpu_poll_interval_seconds = 10
report_on_finish = false
"""


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_minimal(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(_MINIMAL_TOML, encoding="utf-8")

    cfg = load_config(cfg_file)
    assert cfg.telegram.bot_token == "test_token"
    assert cfg.telegram.allowed_user_ids == [123456]


def test_load_config_full(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(_FULL_TOML, encoding="utf-8")

    cfg = load_config(cfg_file)
    assert cfg.daemon.log_level == "DEBUG"
    assert cfg.telegram.bot_token == "abc:XYZ"
    assert cfg.telegram.allowed_user_ids == [111, 222]
    assert cfg.telegram.notifications.on_start is False
    assert cfg.telegram.notifications.stdout_tail_lines == 50
    assert cfg.commands.kill_timeout_seconds == 5
    assert "ml" in cfg.plugins.enabled


def test_load_config_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.toml")


def test_load_config_missing_required_field(tmp_path: Path) -> None:
    # telegram section is required — omitting it should raise
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[daemon]\nlog_level = 'INFO'\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(cfg_file)


def test_load_config_invalid_log_level(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[daemon]\nlog_level = "VERBOSE"\n[telegram]\nbot_token = "t"\nallowed_user_ids = []\n',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_config(cfg_file)


# ---------------------------------------------------------------------------
# Schema defaults
# ---------------------------------------------------------------------------


def test_daemon_config_defaults() -> None:
    cfg = DaemonConfig()
    assert cfg.log_level == "INFO"
    assert cfg.socket_path == ""
    assert cfg.history_file == ""


def test_commands_config_defaults() -> None:
    cfg = CommandsConfig()
    assert "status" in cfg.enabled
    assert "kill" in cfg.enabled
    assert cfg.kill_timeout_seconds == 10
    assert cfg.allowed_scripts == {}


def test_telegram_notifications_defaults() -> None:
    cfg = TelegramNotificationsConfig()
    assert cfg.on_start is True
    assert cfg.on_finish is True
    assert cfg.on_crash is True
    assert cfg.stdout_tail_lines == 20


def test_plugins_config_defaults() -> None:
    cfg = PluginsConfig()
    assert cfg.enabled == []
    assert isinstance(cfg.ml, MLPluginConfig)


def test_telegram_config_requires_bot_token() -> None:
    with pytest.raises(ValidationError):
        TelegramConfig(allowed_user_ids=[1])  # type: ignore[call-arg]


def test_qara_config_requires_telegram() -> None:
    with pytest.raises(ValidationError):
        QaraConfig.model_validate({})
