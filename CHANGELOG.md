# Changelog

All notable changes will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1] - 2026-04-14

### Added
- `cwd` preserved when spawning processes — `qara run` now captures the working directory and restarts use the original launch directory
- Unicode box-drawing table output for `/status` and `/history` Telegram commands
- `qara-ml` plugin: PyPI metadata, classifiers, and README reference

### Fixed
- Thread safety bug in JSONL log: lock was not actually acquired when appending runs
- `tail_runs` now correctly parses the first line of the log file (previously skipped when reading in reverse chunks)
- `/history` Telegram command now shows ✅/❌ status icons instead of raw exit codes
- `format_table` import moved to module level in `telegram.py`

### Changed
- Copyright holder updated to Yerassyl Kenes in LICENSE
- GitHub Actions publish workflow excludes `v*-ml` tags (reserved for plugin releases)

---

## [0.1.0] - 2026-04-01

### Added
- Process watcher with spawn and attach modes
- Telegram notifications (start / finish / crash)
- Bidirectional Telegram commands: `/status`, `/kill`, `/history`, `/logs`
- IPC transport over Unix socket
- Daemon management: `start`, `stop`, `status` with systemd/launchd install
- Plugin system via `importlib.metadata` entry points
- `qara-ml` plugin: GPU metrics (pynvml) and training loss tracking
- `qara history --format json` and `qara status --format json`
