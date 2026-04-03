"""MNIST training script that deliberately crashes — for testing qara crash notifications.

Usage:
    qara run python examples/script_train_mnist_crash.py --name "crash-test"

Prerequisites:
    Install PyTorch for your system: https://pytorch.org
    CPU-only is fine for testing:
        pip install torch torchvision
"""

import argparse
import sys
import time

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.utils.data import DataLoader
    from torchvision import datasets, transforms
except ImportError:
    print(
        "ERROR: PyTorch is required to run this example.\n"
        "Install it from https://pytorch.org\n"
        "  CPU-only:  pip install torch torchvision\n"
        "  With CUDA: pip install torch torchvision --index-url "
        "https://download.pytorch.org/whl/cu121",
        file=sys.stderr,
    )
    sys.exit(1)


class MNISTNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.fc1 = nn.Linear(32 * 7 * 7, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x


def train(epochs: int, crash_after_epoch: int, batch_size: int, data_dir: str) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device={device}")

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,)),
    ])

    train_dataset = datasets.MNIST(data_dir, train=True, download=True, transform=transform)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

    model = MNISTNet().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    print(f"epochs={epochs} batch_size={batch_size} crash_after_epoch={crash_after_epoch}")
    start = time.time()

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0
        correct = 0
        total = 0

        for batch_idx, (data, target) in enumerate(train_loader, 1):
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            pred = output.argmax(dim=1)
            correct += pred.eq(target).sum().item()
            total += target.size(0)

            if batch_idx % 100 == 0:
                avg_loss = epoch_loss / batch_idx
                acc = 100.0 * correct / total
                print(
                    f"epoch={epoch}/{epochs} "
                    f"batch={batch_idx}/{len(train_loader)} "
                    f"loss={avg_loss:.4f} "
                    f"accuracy={acc:.2f}%"
                )

        avg_loss = epoch_loss / len(train_loader)
        acc = 100.0 * correct / total
        elapsed = time.time() - start
        print(
            f"epoch={epoch}/{epochs} "
            f"train_loss={avg_loss:.4f} "
            f"train_accuracy={acc:.2f}% "
            f"elapsed={elapsed:.1f}s"
        )

        # --- Deliberate crash ---
        if epoch >= crash_after_epoch:
            print(
                f"FATAL: CUDA out of memory. Tried to allocate 2.00 GiB. "
                f"GPU 0 has a total capacity of 24.00 GiB.",
                file=sys.stderr,
            )
            print(
                "torch.OutOfMemoryError: CUDA out of memory.",
                file=sys.stderr,
            )
            raise RuntimeError(
                f"Simulated OOM crash after epoch {epoch} "
                f"(this crash is intentional for testing qara)"
            )

    print("training_complete (should not reach here)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train MNIST CNN then crash (qara example)")
    parser.add_argument("--epochs", type=int, default=5, help="Total epochs (won't finish)")
    parser.add_argument(
        "--crash-after", type=int, default=2, help="Crash after this many epochs"
    )
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size")
    parser.add_argument("--data-dir", type=str, default="./data", help="MNIST data directory")
    args = parser.parse_args()

    train(args.epochs, args.crash_after, args.batch_size, args.data_dir)
