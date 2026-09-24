"""Matching eval: extract requirements, score against golden profiles, compare to labeled statuses.

Run from apps/backend:  python ../../evals/run_matching_eval.py
With BEDROCK_ENABLED=true it evaluates the real extraction prompt. Exits non-zero below the threshold.
"""

import json
import sys
from pathlib import Path

from rolewise.services.ai import get_ai
from rolewise.services.matching import FactIn, JobIn, PreferencesIn, RequirementIn, score_match

CASES = json.loads((Path(__file__).parent / "golden" / "matching_cases.json").read_text())
MIN_STATUS_ACCURACY = 0.9


def run() -> int:
    ai = get_ai()
    total = correct = score_fail = 0
    for case in CASES:
        facts = [
            FactIn(f"f{i}", f["kind"], f["title"], f.get("verified", True), "user_entry",
                   ai.embed([f"{f['kind']}: {f['title']}"])[0], f.get("years"))
            for i, f in enumerate(case["facts"])
        ]
        data, _ = ai.complete_json("job_requirements.v1", fast=True, job_title="eval", job_description=case["job"])
        reqs = [
            RequirementIn(f"r{i}", r["kind"], r["text"], ai.embed([r.get("normalized") or r["text"]])[0],
                          r.get("normalized"), r.get("min_years"))
            for i, r in enumerate(data["requirements"])
        ]
        result = score_match(JobIn("eval", case["job"], "eval", None, None, None, reqs), facts, PreferencesIn())
        got = {(r.normalized or r.text).lower(): res.status for r, res in zip(reqs, result.requirements)}

        for text, expected in case["expected"].items():
            total += 1
            ok = got.get(text) == expected
            correct += ok
            if not ok:
                print(f"  [{case['name']}] {text}: expected {expected}, got {got.get(text)}")
        lo, hi = case["score_range"]
        if not lo <= result.score <= hi:
            score_fail += 1
            print(f"  [{case['name']}] score {result.score} outside {lo}-{hi}")

    accuracy = correct / total if total else 0
    print(f"status accuracy {accuracy:.0%} ({correct}/{total}), score range failures {score_fail}")
    return 0 if accuracy >= MIN_STATUS_ACCURACY and score_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
