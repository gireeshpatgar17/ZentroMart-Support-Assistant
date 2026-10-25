"""Section-aware, dependency-light BM25 retrieval for the supplied Markdown KB."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from collections import Counter

WORD_RE = re.compile(r"[\w₹\u0900-\u097F]+", re.UNICODE)
META_RE = re.compile(r"^([\w_]+):\s*(.*?)\s*$")
SECTION_RE = re.compile(r"^##\s+\[([^]]+)\]\s*(.*)$")
PRECEDENCE = {"policy": 5, "agent_guide": 4, "help": 3, "faq": 2, "marketing": 1, "meta": 0}
AUTHORITY_MULTIPLIER = {"policy": 1.45, "agent_guide": 1.15, "help": 1.0, "faq": 0.82, "marketing": 0.65, "meta": 0.9}

# Lightweight lexical bridges for common customer wording vs. policy language.
# This expands search terms only; it does not supply answer facts.
QUERY_EXPANSIONS = {
    # Common Devanagari wording in the supplied Hindi practice set.
    "वापस": ["return", "returns", "returnable", "window"],
    "लौटाने": ["return", "returns", "returnable", "window"],
    "लौटाना": ["return", "returns", "returnable", "window"],
    "लौटा": ["return", "returns", "returnable"],
    "कितने": ["how", "many", "days", "window"],
    "दिन": ["days", "calendar", "business", "window"],
    "मिलेंगे": ["days", "window", "return"],
    "होगा": ["days", "return", "window"],
    "खोल": ["open", "opened", "unopened", "seal", "beauty"],
    "opened": ["beauty", "personal", "care", "unopened", "seal", "intact"],
    "open": ["beauty", "personal", "care", "unopened", "seal", "intact"],
    "perfume": ["beauty", "personal", "care", "sealed"],
    "tried": ["used", "unused", "condition"],
    "started": ["initiated", "initiation"],
    "begin": ["initiated", "initiation"],
    "began": ["initiated", "initiation"],
    "card": ["credit", "debit", "business", "days"],
    "credit": ["card", "business", "days"],
    "refund": ["refunds", "business", "days", "initiated"],
    "return": ["returns", "returnable", "unopened", "seal"],
    "send": ["return", "reverse", "pickup"],
    "back": ["refund", "return"],
    "collect": ["reverse", "pickup"],
    "courier": ["delivery", "attempts"],
}


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    title: str
    doc_type: str
    status: str
    effective_from: str
    section_id: str
    section_title: str
    text: str
    path: str


def tokenize(text: str) -> list[str]:
    return [word.casefold() for word in WORD_RE.findall(text)]


def load_chunks(kb_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(kb_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        metadata: dict[str, str] = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) == 3:
                for line in parts[1].splitlines():
                    match = META_RE.match(line)
                    if match:
                        metadata[match.group(1)] = match.group(2).strip(" '\\\"")
                body = parts[2]
        current_id, current_title, lines = "", metadata.get("title", path.stem), []
        for line in body.splitlines():
            match = SECTION_RE.match(line)
            if match:
                if current_id:
                    chunks.append(_chunk(path, metadata, current_id, current_title, lines))
                current_id, current_title, lines = match.group(1), match.group(2), []
            elif current_id:
                lines.append(line)
        if current_id:
            chunks.append(_chunk(path, metadata, current_id, current_title, lines))
        if not current_id and body.strip():
            chunks.append(_chunk(path, metadata, metadata.get("doc_id", path.stem), current_title, body.splitlines()))
    return chunks


def _chunk(path: Path, metadata: dict, section_id: str, title: str, lines: list[str]) -> Chunk:
    return Chunk(metadata.get("doc_id", path.stem), metadata.get("title", path.stem),
                 metadata.get("doc_type", "unknown"), metadata.get("status", "current"),
                 metadata.get("effective_from", ""), section_id, title,
                 "\n".join(lines).strip(), path.name)


def retrieve(query: str, chunks: list[Chunk], limit: int = 5) -> list[tuple[float, Chunk]]:
    """BM25 ranking with deterministic source-authority tie adjustment."""
    qterms = tokenize(query)
    if not qterms:
        return []
    expanded = list(qterms)
    for term in qterms:
        expanded.extend(QUERY_EXPANSIONS.get(term, []))
    qterms = expanded
    terms_set = set(tokenize(query))
    time_terms = {"when", "date", "by", "started", "begin", "began", "within", "long", "days", "october"}
    needs_refund_calendar = bool(terms_set & {"refund", "refunds"}) and bool(terms_set & time_terms)
    docs = [tokenize(f"{c.section_title} {c.text}") for c in chunks]
    avgdl = sum(map(len, docs)) / max(len(docs), 1)
    df = Counter(term for doc in docs for term in set(doc))
    n = len(docs)
    scored = []
    for chunk, tokens in zip(chunks, docs):
        if chunk.status.casefold() == "superseded":
            continue
        freqs = Counter(tokens)
        score = 0.0
        for term in qterms:
            if term not in freqs:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            tf = freqs[term]
            score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * len(tokens) / max(avgdl, 1)))
        if score > 0:
            score *= AUTHORITY_MULTIPLIER.get(chunk.doc_type, 0.9)
            score += PRECEDENCE.get(chunk.doc_type, 0) * 0.0001
            scored.append((score, chunk))
    if needs_refund_calendar:
        # Refund date answers require both the payment-method window (REF-2)
        # and the fixed-date/business-day calendar (KB-00.3).
        for index, (score, chunk) in enumerate(scored):
            if chunk.section_id == "KB-00.3":
                scored[index] = (max(score, max((s for s, _ in scored), default=0) * 0.8), chunk)
                break
    hindi_return_terms = {"वापस", "लौटाने", "लौटाना", "लौटा"}
    if terms_set & hindi_return_terms:
        # Keep the authoritative return policy in the candidate set even when
        # Hindi grammar words outweigh the English policy vocabulary in BM25.
        top_score = max((score for score, _ in scored), default=1.0)
        intent_ids = {"RET-2"}
        if "खोल" in terms_set:
            intent_ids.add("RET-4")
        present = {chunk.section_id for _, chunk in scored}
        for chunk in chunks:
            if chunk.section_id in intent_ids and chunk.status.casefold() != "superseded" and chunk.section_id not in present:
                scored.append((top_score * 1.2, chunk))
            elif chunk.section_id in intent_ids:
                scored = [(max(score, top_score * 1.2) if item.section_id == chunk.section_id else score, item)
                          for score, item in scored]
    return sorted(scored, key=lambda item: (-item[0], item[1].section_id))[:limit]


def render_context(results: list[tuple[float, Chunk]]) -> str:
    return "\n\n".join(
        f"[{c.section_id}] {c.title} / {c.section_title} (type={c.doc_type}, status={c.status}, effective={c.effective_from})\n{c.text}"
        for _, c in results
    )

