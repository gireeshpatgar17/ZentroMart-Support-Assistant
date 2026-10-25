"""Gold-set retrieval evaluation. Generation scoring can be layered on later."""
from __future__ import annotations

import csv
from pathlib import Path
from .knowledge import load_chunks, retrieve


def evaluate_questions(questions_csv: Path, kb_dir: Path, k: int = 5) -> dict:
    chunks = load_chunks(kb_dir)
    evaluated = 0
    recall_hits = 0
    reciprocal_rank = 0.0
    by_language: dict[str, list[int]] = {}
    with questions_csv.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("answerable", "").casefold() != "true":
                continue
            gold = {part.strip() for part in row.get("gold_evidence", "").split(";") if part.strip() and not part.strip().startswith("products.csv:")}
            if not gold:
                continue
            ranked = [c.section_id for _, c in retrieve(row.get("question", ""), chunks, k)]
            evaluated += 1
            hit = int(bool(gold.intersection(ranked)))
            recall_hits += hit
            rank = next((i + 1 for i, section in enumerate(ranked) if section in gold), None)
            reciprocal_rank += 1 / rank if rank else 0
            lang = row.get("language", "unknown")
            by_language.setdefault(lang, []).append(hit)
    return {
        "answerable_with_section_evidence": evaluated,
        f"section_hit_rate_at_{k}": recall_hits / evaluated if evaluated else 0,
        "mrr": reciprocal_rank / evaluated if evaluated else 0,
        "by_language_hit_rate": {lang: sum(hits) / len(hits) for lang, hits in sorted(by_language.items())},
        "note": "Retrieval-only metric; excludes catalog-row evidence and does not measure answer correctness.",
    }

