# qara-ml

GPU metrics and training loss tracking plugin for [qara](https://github.com/warptengood/qara).

## Install

```bash
pip install qara-ml
```

Requires an NVIDIA GPU and `nvidia-ml-py` (installed automatically).

## Setup

Enable the plugin in `~/.config/qara/config.toml`:

```toml
[plugins]
enabled = ["ml"]

[plugins.ml]
gpu_poll_interval_seconds = 5   # how often to sample GPU metrics
loss_pattern = ""               # custom regex, leave empty for default
```

## What it does

After each watched process finishes, qara sends an additional Telegram summary:

```
GPU summary:
  Peak VRAM: 18204 MB / 24576 MB
  Avg GPU util: 94%
  Peak temp: 78°C

Training summary:
  Final loss: 0.0342
  Best loss: 0.0298 (step 4200)
```

**GPU metrics** — polls all NVIDIA GPUs every `gpu_poll_interval_seconds` and reports peak VRAM usage, average utilisation, and peak temperature over the lifetime of the process.

**Loss tracking** — scans stdout for loss values matching common patterns like `loss=0.123`, `train_loss: 0.456`, `Loss = 0.789`. Reports the final loss and the best (lowest) loss with its step number.

### Custom loss regex

If your training framework uses a different format, set a custom pattern:

```toml
[plugins.ml]
loss_pattern = "val_loss: ([0-9.]+)"
```

## Requirements

- `qara >= 0.1.0`
- NVIDIA GPU with drivers installed
- `nvidia-ml-py >= 12.0` (installed automatically)

If no NVIDIA GPU is detected, the plugin loads silently and loss tracking still works — only GPU metrics are skipped.

## License

MIT — see [LICENSE](LICENSE)
