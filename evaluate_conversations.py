"""Run all supplied multi-turn practice conversations through the local agent."""
from __future__ import annotations

import csv
import argparse
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import src.conversation as conversation
from evaluate_answers import _criteria_complete, _prohibited_claims

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "data" / "raw" / "practice" / "conversations.csv"
OUTPUT = ROOT / "reports" / "drafts" / "conversation_evaluation.csv"


def _decision_ok(row: dict[str, str], answer: str, observed_tools: list[str]) -> str:
    decision = row.get("expected_decision", "").casefold().strip()
    if decision == "escalate":
        return "Yes" if "create_ticket" in observed_tools and re.search(
            r"ticket|colleague|human|connect|सहयोगी|टिकट", answer, re.I
        ) else "No"
    if decision == "clarify":
        return "Yes" if row.get("must_include") and _criteria_complete(answer, row["must_include"]) == "Yes" else (
            "Yes" if "?" in answer else "No"
        )
    if decision == "refuse":
        return "Yes" if re.search(r"can't|cannot|won't|will not|no compensation|not eligible|refuse|decline|नहीं बता|साझा नहीं|मना|nahi ho sakta|nahi diya|नहीं दिया", answer, re.I) else "No"
    return "Yes" if answer.strip() else "No"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Disable model calls; run deterministic conversation/tool flows only.")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="CSV report path")
    args = parser.parse_args()
    if args.offline:
        # agent.answer() loads .env without overriding explicit process values.
        os.environ["GROQ_API_KEY"] = ""
        os.environ["OPENAI_API_KEY"] = ""

    with INPUT.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["conversation_id"]].append(row)

    calls: list[str] = []
    original_lookup, original_create = conversation.lookup_order, conversation.create_ticket

    def lookup_spy(*args, **kwargs):
        calls.append("lookup_order")
        return original_lookup(*args, **kwargs)

    def ticket_spy(*args, **kwargs):
        calls.append("create_ticket")
        return {"created": True, "ticket_id": "TKT-EVAL"}

    conversation.lookup_order = lookup_spy
    conversation.create_ticket = ticket_spy
    output: list[dict[str, str]] = []
    scenario_results: list[tuple[str, bool]] = []
    try:
        for conversation_id, turns in groups.items():
            turns.sort(key=lambda row: int(row["turn"]))
            state = conversation.new_state()
            scenario_ok = True
            for row in turns:
                calls.clear()
                result = conversation.respond(row["customer_message"], state)
                answer = result.get("answer", "")
                evidence = result.get("evidence", [])
                decision = _decision_ok(row, answer, calls)
                facts = _criteria_complete(answer, row.get("must_include", ""))
                prohibited = _prohibited_claims(answer, row.get("must_not_include", ""))
                expected_tools = set(re.findall(r"lookup_order|create_ticket", row.get("expected_tool_calls", "")))
                tools_ok = "Yes" if expected_tools == set(calls) else "No"
                gold = {item.strip() for item in row.get("gold_evidence", "").split(";") if item.strip()}
                evidence_hit = "N/A" if not gold else ("Yes" if gold.intersection(evidence) else "No")
                scenario_turn_ok = decision == "Yes" and facts in {"Yes", "N/A"} and prohibited == "No" and tools_ok == "Yes" and evidence_hit in {"Yes", "N/A"}
                scenario_ok = scenario_ok and scenario_turn_ok
                output.append({
                    "conversation_id": conversation_id, "scenario": row["scenario"], "turn": row["turn"],
                    "language": row["language"], "customer_message": row["customer_message"], "answer": answer,
                    "expected_decision": row["expected_decision"], "decision_check": decision,
                    "required_facts_check": facts, "prohibited_claim_check": prohibited,
                    "expected_tools": ";".join(sorted(expected_tools)), "observed_tools": ";".join(calls),
                    "tool_check": tools_ok, "gold_evidence": ";".join(sorted(gold)),
                    "returned_evidence": ";".join(evidence), "gold_evidence_hit": evidence_hit,
                    "turn_screen": "Pass" if scenario_turn_ok else "Review",
                })
            scenario_results.append((conversation_id, scenario_ok))
    finally:
        conversation.lookup_order, conversation.create_ticket = original_lookup, original_create

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output[0]) if output else []
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    passed = sum(ok for _, ok in scenario_results)
    print(f"Scored {len(scenario_results)} conversations / {len(output)} turns -> {args.output.resolve()}")
    print(f"Whole-scenario literal screen: {passed}/{len(scenario_results)} passed")
    for key in ("decision_check", "required_facts_check", "prohibited_claim_check", "tool_check", "gold_evidence_hit", "turn_screen"):
        print(f"{key}: {dict(Counter(row[key] for row in output))}")
    print("These checks are literal and tool-call based; they do not assess semantic answer quality or voice quality.")


if __name__ == "__main__":
    main()

