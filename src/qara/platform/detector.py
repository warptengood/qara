import sys
from enum import Enum, auto


class Platform(Enum):
    LINUX = auto()
    MACOS = auto()
    WINDOWS = auto()
    UNKNOWN = auto()


def detect() -> Platform:
    if sys.platform.startswith("linux"):
        return Platform.LINUX
    if sys.platform.startswith("darwin"):
        return Platform.MACOS
    if sys.platform.startswith("win32"):
        return Platform.WINDOWS
    return Platform.UNKNOWN