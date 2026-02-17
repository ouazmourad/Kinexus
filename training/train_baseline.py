"""
ThoughtLink — Baseline Models (LogReg + SVM)
Feature extraction from EEG windows, sklearn classifiers.
"""
import os
import sys
import json
import numpy as np
from scipy.signal import welch
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (
    EEG_SAMPLE_RATE, LABEL_NAMES, LABEL_NAMES_BINARY, RESULTS_DIR,
)
from training.preprocessing import DatasetBuilder


def extract_features(X: np.ndarray, sample_rate: int = EEG_SAMPLE_RATE) -> np.ndarray:
    """Extract frequency-domain features from EEG windows.

    Per (500, 6) window:
    - PSD via Welch in mu (8-12Hz), beta (13-30Hz), theta (4-8Hz), alpha (8-13Hz) bands
    - 4 bands x 6 channels = 24 band power features
    - 6 mu/beta ratio features
    - 6 variance features
    Total: 36 features per window

    Args:
        X: (N, 500, 6) array of EEG windows
    Returns:
        (N, 36) feature array
    """
    n_windows = X.shape[0]
    n_channels = X.shape[2]
    features = np.zeros((n_windows, 36), dtype=np.float32)

    bands = {
        "theta": (4, 8),
        "alpha": (8, 13),
        "mu": (8, 12),
        "beta": (13, 30),
    }

    for i in range(n_windows):
        feat_idx = 0
        mu_powers = np.zeros(n_channels)
        beta_powers = np.zeros(n_channels)

        for ch in range(n_channels):
            signal = X[i, :, ch]
            # Handle constant/zero signals
            if np.std(signal) < 1e-12:
                for _ in bands:
                    features[i, feat_idx] = 0.0
                    feat_idx += 1
                continue

            freqs, psd = welch(signal, fs=sample_rate, nperseg=min(256, len(signal)))

            for band_name, (low, high) in bands.items():
                band_mask = (freqs >= low) & (freqs <= high)
                band_power = float(np.nanmean(psd[band_mask])) if band_mask.any() else 0.0
                if np.isnan(band_power) or np.isinf(band_power):
                    band_power = 0.0
                features[i, feat_idx] = band_power
                feat_idx += 1

                if band_name == "mu":
                    mu_powers[ch] = band_power
                elif band_name == "beta":
                    beta_powers[ch] = band_power

        # Mu/beta ratios (6 features)
        for ch in range(n_channels):
            ratio = mu_powers[ch] / (beta_powers[ch] + 1e-10)
            if np.isnan(ratio) or np.isinf(ratio):
                ratio = 0.0
            features[i, feat_idx] = ratio
            feat_idx += 1

        # Variance per channel (6 features)
        for ch in range(n_channels):
            var = float(np.var(X[i, :, ch]))
            if np.isnan(var) or np.isinf(var):
                var = 0.0
            features[i, feat_idx] = var
            feat_idx += 1

    # Final NaN cleanup
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
    return features


def train_and_evaluate(X_train, y_train, X_test, y_test, label_names, task_name=""):
    """Train LogReg and SVM, print reports."""
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    results = {}

    # Logistic Regression
    print(f"\n--- {task_name} Logistic Regression ---")
    lr = LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42)
    lr.fit(X_train_s, y_train)
    y_pred_lr = lr.predict(X_test_s)
    acc_lr = accuracy_score(y_test, y_pred_lr)
    report_lr = classification_report(y_test, y_pred_lr, target_names=label_names,
                                       zero_division=0, output_dict=True)
    print(classification_report(y_test, y_pred_lr, target_names=label_names, zero_division=0))
    print(f"Accuracy: {acc_lr:.4f}")
    results["logistic_regression"] = {"accuracy": acc_lr, "report": report_lr}

    # SVM
    print(f"\n--- {task_name} SVM (RBF) ---")
    svm = SVC(kernel='rbf', class_weight='balanced', random_state=42)
    svm.fit(X_train_s, y_train)
    y_pred_svm = svm.predict(X_test_s)
    acc_svm = accuracy_score(y_test, y_pred_svm)
    report_svm = classification_report(y_test, y_pred_svm, target_names=label_names,
                                        zero_division=0, output_dict=True)
    print(classification_report(y_test, y_pred_svm, target_names=label_names, zero_division=0))
    print(f"Accuracy: {acc_svm:.4f}")
    results["svm"] = {"accuracy": acc_svm, "report": report_svm}

    return results


def main():
    print("=" * 60)
    print("ThoughtLink — Baseline Training")
    print("=" * 60)

    all_results = {}

    # Binary classification first
    print("\n" + "=" * 40)
    print("BINARY CLASSIFICATION (Right Fist vs Left Fist)")
    print("=" * 40)
    builder_bin = DatasetBuilder(binary=True)
    splits_bin, _ = builder_bin.build()

    print("Extracting features (binary)...")
    X_train_feat = extract_features(splits_bin["X_train"])
    X_test_feat = extract_features(splits_bin["X_test"])
    print(f"Feature shape: {X_train_feat.shape}")

    results_bin = train_and_evaluate(
        X_train_feat, splits_bin["y_train"],
        X_test_feat, splits_bin["y_test"],
        LABEL_NAMES_BINARY, "Binary"
    )
    all_results["binary"] = results_bin

    # 5-class classification
    print("\n" + "=" * 40)
    print("5-CLASS CLASSIFICATION")
    print("=" * 40)
    builder_5 = DatasetBuilder(binary=False)
    splits_5, _ = builder_5.build()

    print("Extracting features (5-class)...")
    X_train_feat5 = extract_features(splits_5["X_train"])
    X_test_feat5 = extract_features(splits_5["X_test"])
    print(f"Feature shape: {X_train_feat5.shape}")

    results_5 = train_and_evaluate(
        X_train_feat5, splits_5["y_train"],
        X_test_feat5, splits_5["y_test"],
        LABEL_NAMES, "5-Class"
    )
    all_results["5class"] = results_5

    # Save results
    out_path = os.path.join(RESULTS_DIR, "baseline_results.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
