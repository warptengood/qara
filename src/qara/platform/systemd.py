import subprocess
import sys
from pathlib import Path


from qara.config.loader import config_path


def _unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "qara.service"


def _qara_bin() -> str:
    return str(Path(sys.executable).parent / "qara")


def _unit_content() -> str:
    return f"""\
[Unit]
Description=qara process monitor daemon
After=default.target

[Service]
Type=simple
ExecStart={_qara_bin()} daemon start --foreground
Restart=on-failure
RestartSec=5
Environment=QARA_CONFIG={config_path()}

[Install]
WantedBy=default.target
"""


def install() -> None:
    """Write the systemd user unit and enable + start the service"""
    unit = _unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(_unit_content(), encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "qara"], check=True)
    subprocess.run(["systemctl", "--user", "start", "qara"], check=True)


def uninstall() -> None:
    """Stop, disable, and remove the systemd user unit."""
    subprocess.run(["systemctl", "--user", "stop", "qara"], check=False)
    subprocess.run(["systemctl", "--user", "disable", "qara"], check=False)

    unit = _unit_path()
    try:
        unit.unlink()
    except FileNotFoundError:
        pass

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)


def is_installed() -> bool:
    return _unit_path().exists()