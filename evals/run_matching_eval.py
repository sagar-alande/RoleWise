"""Matching eval: extract requirements, score against golden profiles, compare to labeled results.

Checks per case: requirement statuses, importance bands (optional), verdict (optional), score range.
Run from apps/backend:  python ../../evals/run_matching_eval.py
With BEDROCK_ENABLED=true it evaluates the real extraction prompt. Exits non-zero below the threshold.
"""

import json
import sys
from pathlib import Path

from rolewise.services.ai import get_ai
from rolewise.services.matching import FactIn, JobIn, PreferencesIn, RequirementIn, score_match

CASES = json.loads((Path(__file__).parent / "golden" / "matching_cases.json").read_text())
PROMPT = "job_requirements.v2"
MIN_ACCURACY = 0.9


def run() -> int:
    ai = get_ai()
    total = correct = hard_fail = 0
    for case in CASES:
        name = case["name"]
        facts = [
            FactIn(f"f{i}", f["kind"], f["title"], f.get("verified", True), "user_entry",
                   ai.embed([f"{f['kind']}: {f['title']}"])[0], f.get("years"))
            for i, f in enumerate(case["facts"])
        ]
        data, _ = ai.complete_json(PROMPT, fast=True, job_title=case.get("title", "Engineer"),
                                   job_description=case["job"])
        reqs = [
            RequirementIn(f"r{i}", r["kind"], r["text"], ai.embed([r.get("normalized") or r["text"]])[0],
                          r.get("normalized"), r.get("min_years"), r.get("importance"), r.get("evidence_tier"),
                          r.get("jd_signal"))
            for i, r in enumerate(data["requirements"])
        ]
        job = JobIn(case.get("title", "Engineer"), case["job"], "eval", case.get("location"),
                    case.get("remote_mode"), None, reqs)
        result = score_match(job, facts, PreferencesIn(**case.get("prefs", {})))
        by_text = {r.text.lower(): r for r in result.requirements}

        for text, expected in case["expected"].items():
            total += 1
            got = by_text[text].status if text in by_text else None
            correct += got == expected
            if got != expected:
                print(f"  [{name}] {text}: expected {expected}, got {got}")
        for text, expected in case.get("expected_importance", {}).items():
            total += 1
            got = by_text[text].importance if text in by_text else None
            correct += got == expected
            if got != expected:
                print(f"  [{name}] importance of {text}: expected {expected}, got {got}")
        if "expected_verdict" in case and result.verdict != case["expected_verdict"]:
            hard_fail += 1
            print(f"  [{name}] verdict: expected {case['expected_verdict']}, got {result.verdict}")
        lo, hi = case["score_range"]
        if not lo <= result.score <= hi:
            hard_fail += 1
            print(f"  [{name}] score {result.score} outside {lo}-{hi}")

    accuracy = correct / total if total else 0
    print(f"label accuracy {accuracy:.0%} ({correct}/{total}), verdict/score failures {hard_fail}")
    return 0 if accuracy >= MIN_ACCURACY and hard_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
