"""
ThoughtLink — Model Evaluation
Per-class metrics, confusion matrix, confidence distributions, training curves.
"""
import os
import sys
import json
import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import CHECKPOINT_DIR, RESULTS_DIR, LABEL_NAMES, LABEL_NAMES_BINARY
from training.model import EEGNet
from training.preprocessing import DatasetBuilder
from training.train_eegnet import EEGDataset, load_config

# Try to import matplotlib, but don't fail if not available
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


@torch.no_grad()
def get_predictions(model, loader, device):
    """Get all predictions, probabilities, and true labels."""
    model.eval()
    all_preds = []
    all_probs = []
    all_labels = []

    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        logits = model(X_batch)
        probs = F.softmax(logits, dim=1)
        preds = logits.argmax(dim=1)

        all_preds.append(preds.cpu().numpy())
        all_probs.append(probs.cpu().numpy())
        all_labels.append(y_batch.numpy())

    return (np.concatenate(all_preds),
            np.concatenate(all_probs),
            np.concatenate(all_labels))


def evaluate_model(task_name="5class", device=None):
    """Full evaluation of a trained model."""
    config = load_config()
    binary = task_name == "binary"
    num_classes = 2 if binary else 5
    label_names = LABEL_NAMES_BINARY if binary else LABEL_NAMES

    if device is None:
        gpu_id = config["training"].get("gpu_device", 0)
        device = torch.device(f"cuda:{gpu_id}" if torch.cuda.is_available() else "cpu")

    print(f"\n{'=' * 60}")
    print(f"Evaluating {task_name.upper()} model on {device}")
    print(f"{'=' * 60}")

    # Load model
    model_cfg = config["model"]
    model = EEGNet(
        num_classes=num_classes,
        channels=model_cfg["channels"],
        samples=model_cfg["samples"],
        temporal_filters=model_cfg["temporal_filters"],
        spatial_multiplier=model_cfg["spatial_multiplier"],
        dropout_rate=model_cfg["dropout_rate"],
    )

    checkpoint_path = os.path.join(CHECKPOINT_DIR, f"best_{task_name}.pt")
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    print(f"Loaded checkpoint from epoch {checkpoint['epoch']} "
          f"(val_acc={checkpoint['val_acc']:.4f})")

    # Build test dataset
    builder = DatasetBuilder(binary=binary)
    splits, _ = builder.build()
    from torch.utils.data import DataLoader
    test_ds = EEGDataset(splits["X_test"], splits["y_test"])
    test_loader = DataLoader(test_ds, batch_size=64, shuffle=False, num_workers=0)

    # Get predictions
    preds, probs, labels = get_predictions(model, test_loader, device)

    # Classification report
    print("\nClassification Report:")
    report_str = classification_report(labels, preds, target_names=label_names, zero_division=0)
    print(report_str)
    report_dict = classification_report(labels, preds, target_names=label_names,
                                         zero_division=0, output_dict=True)

    # Confusion matrix
    cm = confusion_matrix(labels, preds)
    print("Confusion Matrix:")
    print(cm)

    # Confidence analysis
    max_probs = probs.max(axis=1)
    correct_mask = preds == labels
    print(f"\nConfidence Analysis:")
    print(f"  Mean confidence (correct):   {max_probs[correct_mask].mean():.4f}" if correct_mask.any() else "  No correct predictions")
    print(f"  Mean confidence (incorrect): {max_probs[~correct_mask].mean():.4f}" if (~correct_mask).any() else "  No incorrect predictions")

    # Per-class confidence
    print("\nPer-class confidence:")
    for i, name in enumerate(label_names):
        mask = labels == i
        if mask.any():
            cls_probs = probs[mask, i]
            print(f"  {name:20s}: mean={cls_probs.mean():.4f}, "
                  f"std={cls_probs.std():.4f}, "
                  f"acc={accuracy_score(labels[mask], preds[mask]):.4f}")

    # Save results
    results = {
        "task": task_name,
        "accuracy": float(accuracy_score(labels, preds)),
        "report": report_dict,
        "confusion_matrix": cm.tolist(),
        "confidence_stats": {
            "overall_mean": float(max_probs.mean()),
            "correct_mean": float(max_probs[correct_mask].mean()) if correct_mask.any() else None,
            "incorrect_mean": float(max_probs[~correct_mask].mean()) if (~correct_mask).any() else None,
        },
    }

    results_path = os.path.join(RESULTS_DIR, f"evaluation_{task_name}.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {results_path}")

    # Generate plots if matplotlib available
    if HAS_MATPLOTLIB:
        plot_results(task_name, cm, label_names, probs, labels, preds, checkpoint.get("history"))

    return results


def plot_results(task_name, cm, label_names, probs, labels, preds, history=None):
    """Generate evaluation plots."""
    if not HAS_MATPLOTLIB:
        return

    # Confusion matrix plot
    fig, ax = plt.subplots(1, 1, figsize=(8, 6))
    im = ax.imshow(cm, interpolation='nearest', cmap='Blues')
    ax.set_title(f'{task_name.upper()} Confusion Matrix')
    ax.set_ylabel('True Label')
    ax.set_xlabel('Predicted Label')
    tick_marks = np.arange(len(label_names))
    ax.set_xticks(tick_marks)
    ax.set_xticklabels(label_names, rotation=45, ha='right')
    ax.set_yticks(tick_marks)
    ax.set_yticklabels(label_names)

    # Add text annotations
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]),
                    ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black")

    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, f"confusion_matrix_{task_name}.png"), dpi=150)
    plt.close(fig)

    # Confidence distribution
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    max_probs = probs.max(axis=1)
    correct_mask = preds == labels
    ax.hist(max_probs[correct_mask], bins=30, alpha=0.7, label='Correct', color='green')
    ax.hist(max_probs[~correct_mask], bins=30, alpha=0.7, label='Incorrect', color='red')
    ax.set_xlabel('Confidence')
    ax.set_ylabel('Count')
    ax.set_title(f'{task_name.upper()} Confidence Distribution')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, f"confidence_dist_{task_name}.png"), dpi=150)
    plt.close(fig)

    # Training curves (if history available)
    if history and "train_loss" in history:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        epochs = range(1, len(history["train_loss"]) + 1)
        axes[0].plot(epochs, history["train_loss"], label="Train Loss")
        axes[0].plot(epochs, history["val_loss"], label="Val Loss")
        axes[0].set_xlabel("Epoch")
        axes[0].set_ylabel("Loss")
        axes[0].set_title(f"{task_name.upper()} Loss Curves")
        axes[0].legend()

        axes[1].plot(epochs, history["train_acc"], label="Train Acc")
        axes[1].plot(epochs, history["val_acc"], label="Val Acc")
        axes[1].set_xlabel("Epoch")
        axes[1].set_ylabel("Accuracy")
        axes[1].set_title(f"{task_name.upper()} Accuracy Curves")
        axes[1].legend()

        fig.tight_layout()
        fig.savefig(os.path.join(RESULTS_DIR, f"training_curves_{task_name}.png"), dpi=150)
        plt.close(fig)

    print(f"Plots saved to {RESULTS_DIR}")


def main():
    # Evaluate binary
    evaluate_model("binary")
    # Evaluate 5-class
    evaluate_model("5class")


if __name__ == "__main__":
    main()
