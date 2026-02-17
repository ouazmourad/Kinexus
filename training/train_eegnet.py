"""
ThoughtLink — EEGNet Training Loop
PyTorch training with AdamW, CosineAnnealingLR, class-weighted CrossEntropy.
Trains binary first, then 5-class. Uses GPU.
"""
import os
import sys
import json
import time
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import CHECKPOINT_DIR, RESULTS_DIR, LABEL_NAMES, LABEL_NAMES_BINARY
from training.preprocessing import DatasetBuilder
from training.model import EEGNet, count_parameters


class EEGDataset(Dataset):
    """Wraps numpy arrays into PyTorch Dataset.
    Converts (N, 500, 6) -> (N, 1, 500, 6) float32 tensors.
    Supports data augmentation for training.
    """

    def __init__(self, X: np.ndarray, y: np.ndarray, augment: bool = False):
        # Add channel dim: (N, 500, 6) -> (N, 1, 500, 6)
        self.X = torch.from_numpy(X).float().unsqueeze(1)
        self.y = torch.from_numpy(y).long()
        self.augment = augment

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        x = self.X[idx]
        if self.augment:
            # Light Gaussian noise
            x = x + torch.randn_like(x) * 0.05
            # Small random amplitude scaling (0.9 to 1.1x)
            scale = 0.9 + 0.2 * torch.rand(1).item()
            x = x * scale
        return x, self.y[idx]


class Trainer:
    """Training loop with validation, checkpointing, and metrics logging."""

    def __init__(self, model, device, config, class_weights=None):
        self.model = model.to(device)
        self.device = device
        self.config = config

        # Loss with class weights + label smoothing
        if class_weights is not None:
            weight_tensor = torch.from_numpy(class_weights).float().to(device)
            self.criterion = nn.CrossEntropyLoss(weight=weight_tensor, label_smoothing=0.1)
        else:
            self.criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

        # Optimizer
        self.optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config["learning_rate"],
            weight_decay=config["weight_decay"]
        )

        # Scheduler
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=config["epochs"]
        )

        self.history = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": [], "lr": []}

    def train_epoch(self, loader):
        self.model.train()
        total_loss = 0.0
        correct = 0
        total = 0

        for X_batch, y_batch in loader:
            X_batch = X_batch.to(self.device)
            y_batch = y_batch.to(self.device)

            self.optimizer.zero_grad()
            logits = self.model(X_batch)
            loss = self.criterion(logits, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()

            total_loss += loss.item() * X_batch.size(0)
            preds = logits.argmax(dim=1)
            correct += (preds == y_batch).sum().item()
            total += X_batch.size(0)

        return total_loss / total, correct / total

    @torch.no_grad()
    def validate(self, loader):
        self.model.eval()
        total_loss = 0.0
        correct = 0
        total = 0

        for X_batch, y_batch in loader:
            X_batch = X_batch.to(self.device)
            y_batch = y_batch.to(self.device)

            logits = self.model(X_batch)
            loss = self.criterion(logits, y_batch)

            total_loss += loss.item() * X_batch.size(0)
            preds = logits.argmax(dim=1)
            correct += (preds == y_batch).sum().item()
            total += X_batch.size(0)

        return total_loss / total, correct / total

    def train(self, train_loader, val_loader, epochs, checkpoint_path):
        best_val_acc = 0.0
        patience_counter = 0
        patience = self.config.get("early_stopping_patience", 10)

        print(f"Training for {epochs} epochs on {self.device}")
        print(f"Model params: {count_parameters(self.model)}")

        for epoch in range(1, epochs + 1):
            t0 = time.time()
            train_loss, train_acc = self.train_epoch(train_loader)
            val_loss, val_acc = self.validate(val_loader)
            self.scheduler.step()

            lr = self.optimizer.param_groups[0]["lr"]
            self.history["train_loss"].append(train_loss)
            self.history["val_loss"].append(val_loss)
            self.history["train_acc"].append(train_acc)
            self.history["val_acc"].append(val_acc)
            self.history["lr"].append(lr)

            elapsed = time.time() - t0
            print(f"Epoch {epoch:3d}/{epochs} | "
                  f"Train Loss: {train_loss:.4f} Acc: {train_acc:.4f} | "
                  f"Val Loss: {val_loss:.4f} Acc: {val_acc:.4f} | "
                  f"LR: {lr:.6f} | {elapsed:.1f}s")

            # Checkpointing
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                patience_counter = 0
                torch.save({
                    "epoch": epoch,
                    "model_state_dict": self.model.state_dict(),
                    "optimizer_state_dict": self.optimizer.state_dict(),
                    "val_acc": val_acc,
                    "val_loss": val_loss,
                    "history": self.history,
                }, checkpoint_path)
                print(f"  -> Saved best model (val_acc={val_acc:.4f})")
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    print(f"  Early stopping at epoch {epoch} (patience={patience})")
                    break

        print(f"\nBest val accuracy: {best_val_acc:.4f}")
        return self.history, best_val_acc


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path) as f:
        return json.load(f)


def run_training(binary=False):
    """Run full training pipeline for binary or 5-class."""
    config = load_config()
    train_cfg = config["training"]

    # Device setup — use GPU 1 (RTX 3070 Ti)
    gpu_id = train_cfg.get("gpu_device", 0)
    if torch.cuda.is_available():
        device = torch.device(f"cuda:{gpu_id}")
        print(f"Using GPU: {torch.cuda.get_device_name(gpu_id)}")
    else:
        device = torch.device("cpu")
        print("WARNING: CUDA not available, using CPU")

    task_name = "binary" if binary else "5class"
    num_classes = 2 if binary else 5
    label_names = LABEL_NAMES_BINARY if binary else LABEL_NAMES

    print(f"\n{'=' * 60}")
    print(f"Training EEGNet — {task_name.upper()} ({num_classes} classes)")
    print(f"{'=' * 60}")

    # Build dataset
    builder = DatasetBuilder(binary=binary)
    splits, class_weights = builder.build()

    # Create data loaders (augmentation on training set only)
    train_ds = EEGDataset(splits["X_train"], splits["y_train"], augment=True)
    val_ds = EEGDataset(splits["X_val"], splits["y_val"], augment=False)
    test_ds = EEGDataset(splits["X_test"], splits["y_test"], augment=False)

    train_loader = DataLoader(train_ds, batch_size=train_cfg["batch_size"],
                              shuffle=True, num_workers=0, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=train_cfg["batch_size"],
                            shuffle=False, num_workers=0, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=train_cfg["batch_size"],
                             shuffle=False, num_workers=0, pin_memory=True)

    print(f"Train: {len(train_ds)}, Val: {len(val_ds)}, Test: {len(test_ds)}")

    # Create model
    model_cfg = config["model"]
    model = EEGNet(
        num_classes=num_classes,
        channels=model_cfg["channels"],
        samples=model_cfg["samples"],
        temporal_filters=model_cfg["temporal_filters"],
        spatial_multiplier=model_cfg["spatial_multiplier"],
        dropout_rate=model_cfg["dropout_rate"],
    )

    # Train
    checkpoint_path = os.path.join(CHECKPOINT_DIR, f"best_{task_name}.pt")
    trainer = Trainer(model, device, train_cfg, class_weights)
    history, best_val_acc = trainer.train(
        train_loader, val_loader,
        epochs=train_cfg["epochs"],
        checkpoint_path=checkpoint_path,
    )

    # Test evaluation
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    test_loss, test_acc = trainer.validate(test_loader)
    print(f"\nTest Loss: {test_loss:.4f}, Test Accuracy: {test_acc:.4f}")

    # Save training history
    history_path = os.path.join(RESULTS_DIR, f"training_history_{task_name}.json")
    save_history = {
        "task": task_name,
        "num_classes": num_classes,
        "best_val_acc": best_val_acc,
        "test_acc": test_acc,
        "test_loss": test_loss,
        "epochs_trained": len(history["train_loss"]),
        "model_params": count_parameters(model),
        "history": history,
    }
    with open(history_path, "w") as f:
        json.dump(save_history, f, indent=2)
    print(f"History saved to {history_path}")

    return model, history, test_acc


def main():
    print("=" * 60)
    print("ThoughtLink — EEGNet Training Pipeline")
    print("=" * 60)

    # Train binary first
    model_bin, hist_bin, test_acc_bin = run_training(binary=True)

    # Then 5-class
    model_5, hist_5, test_acc_5 = run_training(binary=False)

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print(f"  Binary test accuracy:  {test_acc_bin:.4f}")
    print(f"  5-class test accuracy: {test_acc_5:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
