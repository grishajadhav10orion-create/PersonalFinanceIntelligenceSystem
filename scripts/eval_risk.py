"""Measure risk-flag detection on tests/risk_variants.json.  Run: python scripts/eval_risk.py
NOTE: the variants were written by the project author, so this is a self-test of the rules,
NOT an estimate of recall on real bank statements."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import risk


def evaluate(path=None):
    data = json.load(open(path or os.path.join(HERE, "..", "tests", "risk_variants.json")))
    per, issues = {}, []
    for d in data:
        got, exp = {f["type"] for f in risk.detect_flags(d["narration"])}, set(d["expected"])
        for k in exp:
            per.setdefault(k, [0, 0]); per[k][1] += 1
            if k in got: per[k][0] += 1
            else: issues.append((d["narration"], "MISSED " + k))
        if got - exp: issues.append((d["narration"], "EXTRA " + ",".join(sorted(got - exp))))
    clean = [d for d in data if not d["expected"]]
    fp = sum(1 for d in clean if risk.detect_flags(d["narration"]))
    return {"variants": len(data), "per_type": {k: {"detected": v[0], "total": v[1], "recall": v[0] / v[1]} for k, v in per.items()},
            "false_positives_on_clean": fp, "clean_total": len(clean), "issues": issues}


if __name__ == "__main__":
    r = evaluate()
    print(f"{r['variants']} variants")
    for k, v in r["per_type"].items():
        print(f"  {k:22} recall {v['detected']}/{v['total']} = {v['recall']:.0%}")
    print(f"  false positives on clean narrations: {r['false_positives_on_clean']}/{r['clean_total']}")
    for m in r["issues"]: print("  ISSUE:", m)
