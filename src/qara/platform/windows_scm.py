import sys


def _check_platform() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Windows SCM installer is only available on Windows")


def install() -> None:
    _check_platform()
    try:
        import win32serviceutil  # noqa: F401 # type: ignore[import-untyped, import]
    except ImportError:
        raise RuntimeError(
            "pywin32 is required for Windows service installation.\n"
            "Install it with: pip install qara[windows]"
        ) from None
    # Full implementation in Phase 4 follow-up — pywin32 SCM registration
    raise NotImplementedError("Windows SCM installer not yet implemented")


def uninstall() -> None:
    _check_platform()
    raise NotImplementedError("Windows SCM uninstaller not yet implemented")


def is_installed() -> bool:
    return False
