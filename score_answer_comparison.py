"""Apply reproducible literal-criteria and source-coverage checks to a comparison CSV."""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from evaluate_answers import (
    _criteria_complete,
    _decision_grade,
    _grounded_grade,
    _prohibited_claims,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("answer_comparison.csv"))
    parser.add_argument("--output", type=Path, default=Path("scored_answer_comparison.csv"))
    args = parser.parse_args()

    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
        columns = list(rows[0]) if rows else []
    if not rows:
        raise SystemExit(f"No comparison rows found in {args.input}")

    for row in rows:
        for mode in ("prompt_only", "rag"):
            text = row.get(f"{mode}_answer", "")
            row[f"{mode}_correct_decision"] = _decision_grade(row, text)
            row[f"{mode}_required_facts"] = _criteria_complete(text, row.get("must_include", ""))
            row[f"{mode}_prohibited_claims"] = _prohibited_claims(text, row.get("must_not_include", ""))
        row["prompt_only_grounded"] = "No - no retrieved evidence in baseline"
        row["rag_grounded"] = _grounded_grade(row, row.get("rag_answer", ""), row.get("rag_sources", ""))
        row["review_notes"] = "Automated literal criteria/evidence checks; tool scenarios are graded separately."

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Scored {len(rows)} comparison rows -> {args.output.resolve()}")
    for mode in ("prompt_only", "rag"):
        decisions = Counter(row[f"{mode}_correct_decision"] for row in rows)
        facts = Counter(row[f"{mode}_required_facts"] for row in rows)
        violations = sum(row[f"{mode}_prohibited_claims"] == "Yes" for row in rows)
        print(f"{mode}: decision checks={dict(decisions)}; required-fact checks={dict(facts)}; prohibited-claim rows={violations}")
    print(f"rag: gold-evidence hit checks={dict(Counter(row['rag_grounded'] for row in rows))}")
    print("These are deterministic screening metrics, not semantic answer-accuracy scores.")


if __name__ == "__main__":
    main()

