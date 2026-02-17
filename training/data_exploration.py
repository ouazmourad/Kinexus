"""
ThoughtLink — Data Exploration
Scan all .npz files, report statistics, flag bad files.
"""
import os
import sys
import json
import glob
import numpy as np
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import DATA_DIR, LABEL_MAP, RESULTS_DIR, MIN_DURATION_SECONDS


def explore_dataset(data_dir: str = DATA_DIR) -> dict:
    """Scan all .npz files and generate dataset statistics."""
    npz_files = sorted(glob.glob(os.path.join(data_dir, "*.npz")))
    print(f"Found {len(npz_files)} .npz files in {data_dir}")

    label_counts = Counter()
    subject_counts = Counter()
    session_counts = Counter()
    durations = []
    bad_files = []
    eeg_shapes = []
    moments_shapes = []
    label_subject_map = defaultdict(set)
    file_details = []

    for i, fpath in enumerate(npz_files):
        fname = os.path.basename(fpath)
        try:
            data = np.load(fpath, allow_pickle=True)
            eeg = data["feature_eeg"]
            moments = data["feature_moments"]
            label_info = data["label"].item()

            label_str = label_info["label"]
            subject_id = label_info["subject_id"]
            session_id = label_info["session_id"]
            duration = label_info["duration"]

            # Map label
            if label_str not in LABEL_MAP:
                bad_files.append({"file": fname, "reason": f"Unknown label: {label_str}"})
                continue

            label_idx = LABEL_MAP[label_str]

            # Check shapes
            if eeg.shape != (7499, 6):
                bad_files.append({"file": fname, "reason": f"Bad EEG shape: {eeg.shape}"})
                continue

            # Check duration
            is_short = duration < MIN_DURATION_SECONDS

            label_counts[label_str] += 1
            subject_counts[subject_id] += 1
            session_counts[session_id] += 1
            durations.append(duration)
            eeg_shapes.append(eeg.shape)
            moments_shapes.append(moments.shape)
            label_subject_map[label_str].add(subject_id)

            detail = {
                "file": fname,
                "label": label_str,
                "label_idx": label_idx,
                "subject_id": subject_id,
                "session_id": session_id,
                "duration": round(duration, 3),
                "eeg_shape": list(eeg.shape),
                "moments_shape": list(moments.shape),
                "short_duration": is_short,
            }
            file_details.append(detail)

            if is_short:
                bad_files.append({"file": fname, "reason": f"Duration {duration:.2f}s < {MIN_DURATION_SECONDS}s"})

        except Exception as e:
            bad_files.append({"file": fname, "reason": str(e)})

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(npz_files)} files...")

    durations_arr = np.array(durations) if durations else np.array([0.0])

    report = {
        "total_files": len(npz_files),
        "valid_files": len(file_details),
        "bad_files_count": len(bad_files),
        "unique_subjects": len(subject_counts),
        "unique_sessions": len(session_counts),
        "num_classes": len(label_counts),
        "class_distribution": dict(label_counts.most_common()),
        "subject_trial_counts": dict(subject_counts.most_common()),
        "duration_stats": {
            "mean": round(float(durations_arr.mean()), 3),
            "std": round(float(durations_arr.std()), 3),
            "min": round(float(durations_arr.min()), 3),
            "max": round(float(durations_arr.max()), 3),
            "median": round(float(np.median(durations_arr)), 3),
        },
        "subjects_per_class": {k: sorted(list(v)) for k, v in label_subject_map.items()},
        "bad_files": bad_files,
    }

    return report


def main():
    print("=" * 60)
    print("ThoughtLink — Data Exploration")
    print("=" * 60)

    report = explore_dataset()

    print(f"\nTotal files:     {report['total_files']}")
    print(f"Valid files:     {report['valid_files']}")
    print(f"Bad files:       {report['bad_files_count']}")
    print(f"Unique subjects: {report['unique_subjects']}")
    print(f"Unique sessions: {report['unique_sessions']}")
    print(f"Num classes:     {report['num_classes']}")

    print("\nClass Distribution:")
    for label, count in report["class_distribution"].items():
        print(f"  {label:20s}: {count}")

    print(f"\nDuration Stats:")
    for k, v in report["duration_stats"].items():
        print(f"  {k:8s}: {v:.3f}s")

    if report["bad_files"]:
        print(f"\nBad Files ({report['bad_files_count']}):")
        for bf in report["bad_files"][:20]:
            print(f"  {bf['file']}: {bf['reason']}")
        if report["bad_files_count"] > 20:
            print(f"  ... and {report['bad_files_count'] - 20} more")

    # Save report
    out_path = os.path.join(RESULTS_DIR, "data_exploration.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {out_path}")


if __name__ == "__main__":
    main()
