import argparse
import sys
from pathlib import Path
from typing import Dict

from api.config import get_settings
from api.evaluation.persistence import latest_run, load_run


def aggregate_scores(run: dict) -> Dict[str, float]:
    """Average each metric across scored cases in a run. Errored cases are excluded."""
    totals: Dict[str, list] = {}
    for case in run["cases"]:
        if case["status"] != "scored":
            continue
        for metric, score in case["scores"].items():
            totals.setdefault(metric, []).append(score)
    return {metric: sum(values) / len(values) for metric, values in totals.items() if values}


def compare(baseline_path: str, current_path: str, threshold: float) -> int:
    """Diff aggregate metric scores between two runs.

    :param threshold: Absolute drop (baseline - current) that triggers a
        regression. This is a tolerance band for LLM-judge noise, not a
        precision target — see the eval harness design doc.
    :returns: 0 if no metric regressed past threshold, 1 otherwise (CI exit code).
    """
    baseline = aggregate_scores(load_run(baseline_path))
    current = aggregate_scores(load_run(current_path))

    regressions = []
    print(f"{'Metric':<28}{'Baseline':>10}{'Current':>10}{'Delta':>10}")
    for metric in sorted(set(baseline) | set(current)):
        base_score = baseline.get(metric)
        cur_score = current.get(metric)
        if base_score is None or cur_score is None:
            print(f"{metric:<28}{'--':>10}{'--':>10}{'N/A':>10}")
            continue
        delta = cur_score - base_score
        print(f"{metric:<28}{base_score:>10.3f}{cur_score:>10.3f}{delta:>+10.3f}")
        if delta < -threshold:
            regressions.append((metric, base_score, cur_score, delta))

    if regressions:
        print("\nREGRESSION DETECTED:")
        for metric, base_score, cur_score, delta in regressions:
            print(f"  {metric}: {base_score:.3f} -> {cur_score:.3f} (drop of {abs(delta):.3f}, threshold {threshold})")
        return 1

    print("\nNo regression past threshold.")
    return 0


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Diff two eval harness runs and gate on a regression threshold.")
    parser.add_argument(
        "--baseline",
        default="latest-other",
        help="Path to baseline run JSON, or 'latest-other' to auto-pick the second-newest run in results_dir",
    )
    parser.add_argument("--current", default=None, help="Path to current run JSON (defaults to the newest run)")
    parser.add_argument("--threshold", type=float, default=settings.eval.regression_threshold)
    args = parser.parse_args()

    results_dir = settings.eval.results_dir
    current_path = args.current or latest_run(results_dir)
    if args.baseline == "latest-other":
        baseline_path = latest_run(results_dir, exclude=Path(current_path) if current_path else None)
    else:
        baseline_path = args.baseline

    if not current_path or not baseline_path:
        print("Not enough persisted runs to compare. Run the harness at least twice first.")
        sys.exit(1)

    sys.exit(compare(str(baseline_path), str(current_path), args.threshold))


if __name__ == "__main__":
    main()
