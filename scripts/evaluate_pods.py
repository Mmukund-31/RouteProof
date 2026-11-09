"""Evaluate POD extraction against the labelled evaluation set (synthetic) or a folder of real labelled photos.

    python scripts/evaluate_pods.py                          # synthetic set, real model (AI_PROVIDER=claude, AI_API_KEY)
    python scripts/evaluate_pods.py --manifest real/labels.json --out report.json
    python scripts/evaluate_pods.py --render-only eval_docs/  # just write the synthetic documents to look at

Reports field extraction accuracy separately from routing: `false_auto_verified` and
`auto_verified_with_misread_fields` must both be empty before a threshold or prompt change ships.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.services.ai import eval_set as ev  # noqa: E402
from app.services.ai.factory import get_provider  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, help="JSON manifest of real labelled photos (see eval_set.load_manifest)")
    ap.add_argument("--render-only", type=Path, metavar="DIR", help="write the synthetic documents to DIR and exit")
    ap.add_argument("--out", type=Path, help="write the full JSON report here")
    a = ap.parse_args()

    if a.render_only:
        a.render_only.mkdir(parents=True, exist_ok=True)
        for c in ev.CASES:
            (a.render_only / f"{c.id}.jpg").write_bytes(ev.render_case(c))
        print(f"wrote {len(ev.CASES)} documents to {a.render_only}")
        for n in ev.rendering_notes():
            print("note:", n)
        sys.exit(0)

    s = get_settings()
    if s.ai_provider != "claude":
        sys.exit(f"AI_PROVIDER is '{s.ai_provider}'. Evaluation is only meaningful against the real model (AI_PROVIDER=claude).")
    if a.manifest:
        cases, images = ev.load_manifest(a.manifest)
        report = ev.run(get_provider(), cases, images=images, threshold=s.ai_confidence_threshold, today=date.today())
    else:
        report = ev.run(get_provider(), threshold=s.ai_confidence_threshold)
    sm = report["summary"]
    print(f"model={s.ai_model} cases={sm['cases']} threshold={s.ai_confidence_threshold}")
    print("field accuracy:", ", ".join(f"{k}={v:.0%}" for k, v in sm["field_accuracy"].items()))
    print(f"routing agreement={sm['routing_agreement']:.0%}  auto-verified={sm['auto_verification_rate']:.0%} "
          f"(labelled {sm['expected_auto_verification_rate']:.0%})")
    print("FALSE auto-verified:", sm["false_auto_verified"] or "none")
    print("auto-verified with misread fields:", sm["auto_verified_with_misread_fields"] or "none")
    print("missed auto-verification (extra human work):", sm["missed_auto_verified"] or "none")
    for r in report["results"]:
        if not r["routing_ok"]:
            print(f"  {r['id']}: expected {r['expected_decision']}, got {r['decision']} {r['reasons']}")
    for n in report["rendering_notes"]:
        print("note:", n)
    if a.out:
        a.out.write_text(json.dumps(report, indent=2, default=str))
        print(f"report written to {a.out}")
