from typing import Literal

from pydantic import BaseModel

class DaemonConfig(BaseModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    socket_path: str = ""
    history_file: str = ""


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
    allowed_scripts: dict[str, str] = {} # alias -> absolute path
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
