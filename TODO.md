# qara — TODO

Items are grouped by area. Check them off as they're done.

---

## Installation & Distribution

- [ ] **Publish `qara-ml` to PyPI** — workflow ready (`publish-ml.yml`), triggered by `v0.1.0-ml` tag. Before first publish: set up Trusted Publishing on PyPI for `qara-ml` under the `pypi-ml` GitHub environment (same steps as `qara`, but for the `qara-ml` package name)
- [ ] **`qara install` UX clarity** — users don't understand what it does. After running it:
  - Print a clear explanation: "qara is now registered as a user service. It will start automatically when you log in. You don't need to run `qara daemon start` manually anymore."
  - Print the next step: "Start it now with: `systemctl --user start qara`" (Linux) or `launchctl start com.qara.daemon` (macOS)
  - Add `qara install --help` description that explains the purpose upfront

---

## CLI & UX

- [ ] **Interactive PID browser** — `qara ps` command that shows a live, navigable list of system processes (like `htop` lite) so users can pick a PID to attach to without manually running `ps aux`. Use `rich.Live` + `psutil` for a terminal UI updated every second
- [ ] **`qara attach` discovery** — tab-completion or fuzzy search over running processes when no PID is given
- [ ] **`qara daemon logs`** — tail the daemon log file directly from the CLI instead of `cat ~/.local/state/qara/log/daemon.log`
- [ ] **`qara status` in detached mode** — show status without requiring the daemon to be running (read from JSONL log)

---

## Notifications & Channels

- [ ] **Discord channel** — send notifications to a Discord webhook; reuse `format_table()` from `channels/formatting.py` with triple-backtick wrapping
- [ ] **Slack channel** — webhook-based; same pattern
- [ ] **stdout tail in finish notification** — include last N lines of stdout in the "process finished" Telegram message (config: `stdout_tail_lines`)

---

## ML Plugin (`qara-ml`)

- [ ] **Publish to PyPI** as a separate package (see Distribution above)
- [ ] **Per-GPU breakdown** — report metrics per device, not just aggregated, when multiple GPUs are present
- [ ] **Wandb / MLflow integration** — link to the run URL in the finish notification if detected in env vars
- [ ] **Epoch detection** — parse epoch number from stdout alongside loss

---

## Daemon & Core

- [ ] **Windows support** — IPC currently uses Unix sockets; implement named pipe fallback for Windows (stub exists in `transport/`)
- [ ] **`qara restart <name>`** — restart a crashed or finished process with the same argv
- [ ] **Process groups** — watch multiple related processes as a named group; notify when all finish
- [ ] **Rate limiting on notifications** — avoid flooding Telegram if a process crashes in a loop
- [ ] **Stale daemon detection on startup** — check PID file on `daemon start`; if the recorded PID is still alive, refuse to start with a clear error ("daemon already running, PID X"). If the PID is dead (stale file), delete it and proceed. Currently a second daemon starts silently, both poll the same bot token, and `TelegramConflictError` causes an infinite retry loop that blocks IPC responses, making `qara run` time out.

---

## Testing

- [ ] **Integration tests** — end-to-end test that spawns the daemon, runs a process, and checks the JSONL log
- [ ] **Telegram channel tests** — mock the Bot and assert correct message formatting for each event type
- [ ] **`format_table()` edge cases** — empty rows, very long values, unicode in cell content
