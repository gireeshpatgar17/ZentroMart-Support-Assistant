"""Create a prompt-only vs. RAG answer comparison sheet from practice questions.

This script compares prompt-only and RAG answers, then fills objective rubric
checks in a CSV. The rubric checks use literal criteria and evidence IDs; they
are screening metrics, not a semantic human-quality score.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from src.agent import ROOT, answer


BASELINE_PROMPT = (
    "You are ZentroMart's customer-support assistant. Answer the customer's "
    "question using only what you already know; you have not been given company "
    "documents or order tools. If you are uncertain, say so. Do not invent "
    "company policies, discounts, order status, or actions. Reply in the "
    "customer's language in two or three short sentences."
)

NUMBER_WORDS = {
    "1": ("one", "एक", "एक ही", "ek"), "3": ("three", "तीन"), "5": ("five", "पाँच", "पांच"),
    "7": ("seven", "सात"), "10": ("ten", "दस"),
    "12": ("twelve", "बारह"), "15": ("fifteen", "पंद्रह", "पन्द्रह"),
    "30": ("thirty", "तीस"), "48": ("forty eight", "forty-eight", "अड़तालीस"),
    "79": ("seventy nine", "seventy-nine"),
}


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold().replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", value).strip()


def _criterion_groups(text: str) -> list[list[str]]:
    return [[part.strip() for part in group.split("/") if part.strip()]
            for group in text.split(";") if group.strip()]


def _contains_variant(answer_text: str, variant: str) -> bool:
    answer_norm, variant_norm = _normalize(answer_text), _normalize(variant)
    if not variant_norm:
        return False
    variants = [variant_norm]
    if variant_norm == "quality check":
        variants.append("क्वालिटी चेक")
    if variant_norm.isdigit():
        variants.extend(_normalize(word) for word in NUMBER_WORDS.get(variant_norm, ()))
        return any(re.search(rf"(?<!\w){re.escape(item)}(?!\w)", answer_norm) for item in variants)
    return any(item in answer_norm for item in variants)


def _criteria_complete(answer_text: str, criteria: str) -> str:
    groups = _criterion_groups(criteria)
    if not groups:
        return "N/A"
    return "Yes" if all(any(_contains_variant(answer_text, item) for item in group) for group in groups) else "No"


def _prohibited_claims(answer_text: str, criteria: str) -> str:
    return "Yes" if any(
        any(_contains_variant(answer_text, item) for item in group)
        for group in _criterion_groups(criteria)
    ) else "No"


def _abstains(answer_text: str) -> bool:
    return bool(re.search(
        r"couldn['’]t find|could not find|don't have (?:that )?information|do not have (?:that )?information|"
        r"not sure|no (?:relevant )?information|not mentioned|not covered|cannot confirm|can't confirm|"
        r"not seeing any policy|available (?:documents|policies) (?:don't|do not) (?:mention|specify)|"
        r"jaankari nahi mili|policies mein .* nahi mili|"
        r"जानकारी नहीं|उल्लेख नहीं|नहीं मिली|नहीं मिलता|नीति उपलब्ध नहीं|उपलब्ध नीतियों में .*नहीं मिली",
        answer_text, re.I,
    ))


def _decision_grade(row: dict, answer_text: str) -> str:
    decision = row.get("expected_decision", "answer").casefold().strip()
    answer_norm = _normalize(answer_text)
    if decision == "escalate":
        # This script compares single-turn answer generation, not conversation tools.
        return "N/A - evaluate in conversation flow"
    if decision == "refuse":
        return "Yes" if re.search(r"can't|cannot|won't|will not|can't share|cannot share|नहीं बता|साझा नहीं", answer_norm, re.I) else "No"
    if decision == "clarify":
        return "Yes" if re.search(r"\?|which (?:item|product)|what (?:item|product)|कौन सा|किस (?:सामान|वस्तु)|किससे भुगतान", answer_text, re.I) else "No"
    if row.get("answerable", "").casefold() == "false":
        return "Yes" if _abstains(answer_text) else "No"
    if _abstains(answer_text):
        return "No"
    return _criteria_complete(answer_text, row.get("must_include", ""))


def _grounded_grade(row: dict, answer_text: str, sources: str) -> str:
    gold = [item.strip() for item in row.get("gold_evidence", "").split(";") if item.strip()]
    if not gold:
        return "Yes" if _abstains(answer_text) else "No"
    returned = {item.strip() for item in sources.split(";") if item.strip()}
    return "Yes" if any(item in returned for item in gold) else "No"


def _baseline(client: OpenAI, model: str, question: str) -> str:
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": BASELINE_PROMPT},
            {"role": "user", "content": question},
        ],
    )
    return response.choices[0].message.content or ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("answer_comparison.csv"),
        help="CSV grading sheet to create (default: answer_comparison.csv)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Optionally process only the first N rows for a small initial run; 0 means all rows.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume an interrupted run by keeping completed rows already in --output.",
    )
    parser.add_argument(
        "--language", default="",
        help="Optionally evaluate only rows whose language code matches (for example hi).",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = (os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY", "")).strip()
    if not api_key:
        raise SystemExit("Set GROQ_API_KEY in the project .env before running this comparison.")
    client_kwargs = {"api_key": api_key}
    if os.getenv("OPENAI_BASE_URL"):
        client_kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
    client = OpenAI(**client_kwargs)
    model = os.getenv("CHAT_MODEL", "openai/gpt-oss-20b")

    questions_path = ROOT / "data" / "raw" / "practice" / "questions.csv"
    with questions_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if args.language:
        rows = [row for row in rows if row.get("language", "").casefold() == args.language.casefold()]
    if args.limit > 0:
        rows = rows[:args.limit]

    output_columns = [
        "id", "language", "question", "answerable", "expected_decision",
        "acceptable_decisions", "reference_answer", "must_include",
        "must_not_include", "gold_evidence", "prompt_only_answer", "rag_answer",
        "rag_sources", "prompt_only_correct_decision", "prompt_only_required_facts",
        "prompt_only_prohibited_claims", "prompt_only_grounded", "rag_correct_decision",
        "rag_required_facts", "rag_prohibited_claims", "rag_grounded", "review_notes",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed: dict[str, dict[str, str]] = {}
    if args.resume and args.output.exists():
        with args.output.open(encoding="utf-8-sig", newline="") as stream:
            completed = {row.get("id", ""): row for row in csv.DictReader(stream) if row.get("id")}
        rows = [row for row in rows if row.get("id", "") not in completed]
    mode = "a" if completed else "w"
    with args.output.open(mode, encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=output_columns)
        if not completed:
            writer.writeheader()
        for index, row in enumerate(rows, start=1):
            question = row.get("question", "")
            baseline = _baseline(client, model, question)
            rag = answer(question)
            writer.writerow({
                "id": row.get("id", ""),
                "language": row.get("language", ""),
                "question": question,
                "answerable": row.get("answerable", ""),
                "expected_decision": row.get("expected_decision", ""),
                "acceptable_decisions": row.get("acceptable_decisions", ""),
                "reference_answer": row.get("reference_answer", ""),
                "must_include": row.get("must_include", ""),
                "must_not_include": row.get("must_not_include", ""),
                "gold_evidence": row.get("gold_evidence", ""),
                "prompt_only_answer": baseline,
                "rag_answer": rag.get("answer", ""),
                "rag_sources": "; ".join(rag.get("evidence", [])),
                "prompt_only_correct_decision": _decision_grade(row, baseline),
                "prompt_only_required_facts": _criteria_complete(baseline, row.get("must_include", "")),
                "prompt_only_prohibited_claims": _prohibited_claims(baseline, row.get("must_not_include", "")),
                "prompt_only_grounded": "No - no retrieved evidence in baseline",
                "rag_correct_decision": _decision_grade(row, rag.get("answer", "")),
                "rag_required_facts": _criteria_complete(rag.get("answer", ""), row.get("must_include", "")),
                "rag_prohibited_claims": _prohibited_claims(rag.get("answer", ""), row.get("must_not_include", "")),
                "rag_grounded": _grounded_grade(row, rag.get("answer", ""), "; ".join(rag.get("evidence", []))),
                "review_notes": "Automated literal criteria/evidence checks; tool scenarios are graded separately.",
            })
            stream.flush()
            print(f"[{len(completed) + index}/{len(rows) + len(completed)}] {row.get('id', '')}: generated prompt-only and RAG answers")

    print(f"Saved auto-scored comparison sheet to: {args.output.resolve()}")
    print(f"Model: {model}; questions: {len(rows) + len(completed)}; chat completions this run: up to {2 * len(rows)}")
    print("Scores use literal must_include/must_not_include variants and gold evidence IDs; they are objective screening metrics, not semantic judgments.")


if __name__ == "__main__":
    main()

