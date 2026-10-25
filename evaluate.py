from pathlib import Path
import argparse
import json
from src.evaluation import evaluate_questions

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description="Evaluate section retrieval against the single-turn practice set.")
parser.add_argument("--output", type=Path, default=root / "reports" / "drafts" / "retrieval_final.json")
args = parser.parse_args()
result = evaluate_questions(root / "data/raw/practice/questions.csv", root / "data/raw/kb")
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2, ensure_ascii=False))
print(f"Saved retrieval metrics to {args.output.resolve()}")

