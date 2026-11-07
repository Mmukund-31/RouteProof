"""Measure what AI_CONFIDENCE_THRESHOLD actually buys you, using labelled synthetic POD documents (all fictional).

    # real model (needs AI_PROVIDER=claude and AI_API_KEY in backend/.env); ~1 API call per sample
    python scripts/calibrate_confidence.py --samples 120 --target-error 0.01 --out calibration.json

Prints, for each candidate threshold, how many critical-field readings would be auto-accepted (coverage) and how many
of those were wrong (error rate), and recommends the lowest threshold that keeps the error rate within the target on
every critical field. The synthetic set is a starting point: add real, consented, anonymised PODs before trusting the
number in production, and re-run after any model or prompt change.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.services.ai.calibration import calibrate  # noqa: E402
from app.services.ai.factory import get_provider  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--target-error", type=float, default=0.01, help="max share of wrong readings among auto-accepted ones")
    ap.add_argument("--min-accepted", type=int, default=30, help="min accepted readings per field before trusting a threshold")
    ap.add_argument("--out", type=Path, help="write the full JSON report here")
    a = ap.parse_args()

    s = get_settings()
    if s.ai_provider != "claude":
        sys.exit(f"AI_PROVIDER is '{s.ai_provider}'. Calibration is only meaningful against the real model (AI_PROVIDER=claude).")
    rep = calibrate(get_provider(), a.samples, seed=a.seed, target_error_rate=a.target_error, min_accepted=a.min_accepted)

    print(f"model={s.ai_model} samples={rep.samples} provider_errors={rep.provider_errors} target_error<={rep.target_error_rate:.2%}")
    print(f"{'thr':>5}  " + "  ".join(f"{f[:12]:>22}" for f in rep.per_field) + "   worst   ok")
    for row in rep.per_threshold:
        cells = "  ".join(f"{(v['coverage'] or 0):>6.0%} cov {v['error_rate']:>6.1%} err" for v in row["fields"].values())
        print(f"{row['threshold']:>5.2f}  {cells}  {row['worst_error_rate']:>6.1%}  {'yes' if row['meets_target'] else ' no'}")
    print()
    print(f"current AI_CONFIDENCE_THRESHOLD={s.ai_confidence_threshold}  recommended={rep.recommended_threshold}")
    print(rep.note)
    if a.out:
        a.out.write_text(json.dumps(rep.as_dict(), indent=2))
        print(f"report written to {a.out}")
