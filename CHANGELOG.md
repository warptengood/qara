# Changelog

All notable changes will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
