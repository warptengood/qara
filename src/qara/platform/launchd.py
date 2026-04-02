import contextlib
import os
import subprocess
import sys
from pathlib import Path

from qara.config.loader import config_path

_LABEL = "com.qara.daemon"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _qara_bin() -> str:
    return str(Path(sys.executable).parent / "qara")


def _plist_content() -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{_qara_bin()}</string>
    <string>daemon</string>
    <string>start</string>
    <string>--foreground</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QARA_CONFIG</key>
    <string>{config_path()}</string>
  </dict>
</dict>
</plist>
"""


def install() -> None:
    """Write the launchd plist and bootstrap it into the user session."""
    plist = _plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(_plist_content(), encoding="utf-8")

    uid = str(os.getuid())
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
        check=True,
    )


def uninstall() -> None:
    """Bootoit the service and remove the plist."""
    uid = str(os.getuid())
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", _LABEL],
        check=False,
    )
    with contextlib.suppress(FileNotFoundError):
        _plist_path().unlink()


def is_installed() -> bool:
    return _plist_path().exists()
