# qara examples

Manual test scripts for verifying qara's Telegram integration end-to-end.

## Prerequisites

1. **Install PyTorch** for your system from [pytorch.org](https://pytorch.org).
   CPU-only is fine for testing:

   ```bash
   pip install torch torchvision
   ```

2. **Configure qara** with your Telegram bot token and user ID:

   ```bash
   qara config init
   # Edit the config file (path shown by the command above)
   # Set bot_token and allowed_user_ids
   ```

   If you don't have a bot yet, message [@BotFather](https://t.me/BotFather) on Telegram.

3. **Start the daemon**:

   ```bash
   qara daemon start --foreground
   ```

## Scripts

### `train_mnist.py` — successful training run

Trains a small CNN on MNIST for 5 epochs (~60s on CPU). Tests start/finish notifications, `/status`, `/logs`, and loss tracking.

```bash
# In a second terminal:
qara run python examples/train_mnist.py --name "mnist-test"
```

Options:
- `--epochs N` — number of epochs (default: 5)
- `--batch-size N` — batch size (default: 64)
- `--lr F` — learning rate (default: 0.001)
- `--data-dir PATH` — where to download MNIST (default: ./data)

**What to expect on Telegram:**
- Start notification with PID and command
- Finish notification with exit code 0 and duration
- Try `/status` while it's running
- Try `/logs mnist-test` to see recent output

### `train_crash.py` — crash during training

Same training setup but deliberately crashes after 2 epochs with a simulated OOM error. Tests crash notifications and stderr capture.

```bash
qara run python examples/train_crash.py --name "crash-test"
```

Options:
- `--crash-after N` — crash after N epochs (default: 2)
- `--epochs N`, `--batch-size N`, `--data-dir PATH` — same as above

**What to expect on Telegram:**
- Start notification
- Crash notification with exit code 1, duration, and stderr tail showing the OOM error
