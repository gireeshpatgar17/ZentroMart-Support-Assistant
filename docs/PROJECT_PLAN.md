# Project plan: ZentroMart AI Support Agent

## Problem statement

Online retail support questions often combine policy interpretation with order-specific facts. A general chatbot can confidently quote stale FAQs, miss Hindi/Hinglish intent, leak private order details, or invent exceptions. This project builds a grounded assistant that retrieves versioned policy sections, reads structured catalog/order facts only through the appropriate path, and escalates safely.

## Objectives and success criteria

1. Return concise answers grounded in authoritative current documents, with source section IDs.
2. Refuse to disclose order facts until identity verification succeeds.
3. Handle multi-turn clarification, one-retry verification, and ticketed handoff.
4. Evaluate all 52 single-turn questions and 96 multi-turn turns using decisions, required facts, prohibited claims, evidence IDs, and tool-call expectations.
5. Provide the required audio-folder batch command; use Gnani exclusively for STT and TTS.
6. Report limitations and measured errors honestly; do not claim a score until the harness is run.

## Architecture

```text
Customer text
   ├── normalize language / ASR transcript
   ├── section-aware BM25 retrieval ── current policies and agent rules
   ├── explicit structured lookup ── products / pincodes / verified orders
   ├── safety and escalation controller ── verify, retry, ticket
   └── concise response + evidence section IDs
             └── evaluation against questions.csv and conversations.csv
```

Retrieval stores each section as a separate chunk with document ID, section ID, type, status and effective date. At answer time, filter out superseded sources and rank current policies above guides, help, FAQs and marketing. Include the precedence rule in context. Structured CSV access is separated from policy retrieval. Conversation state is ephemeral and never persisted with verification values.

## Evaluation protocol

- **Retrieval:** section-ID recall@5 and reciprocal rank against `gold_evidence` for answerable questions.
- **Decision:** exact/acceptable decision accuracy (answer, clarify, escalate, refuse).
- **Required facts:** each `must_include` item must be present; slash-separated alternatives count as one acceptable fact.
- **Safety:** detect any `must_not_include` claim and any order data returned before verification.
- **Evidence:** compare returned source IDs to gold evidence; catalog rows must be attributed as `products.csv:SKU`.
- **Tool use:** compare conversation tool calls against expected calls, including absence of calls where none are expected.
- **Language:** report performance by `language`; manually review any generated Hindi/Hinglish samples before claiming quality.

Use deterministic retrieval ablations: BM25 baseline; policy/status/precedence filtering; optional multilingual query expansion. Keep model temperature low and cache no private order data. Separate retrieval errors from generation errors through retrieved evidence inspection.

## Milestones

1. Dataset ingestion and integrity check.
2. Section-aware retrieval and a small inspectable terminal query interface.
3. Single-turn answer generation with citation IDs and uncertainty fallback.
4. Tool-gated order lookup, conversation state and ticket escalation.
5. Automated evaluation and error analysis, including Step 1 prompt-only vs Step 2 RAG.
6. Gnani voice integration and batch folder processing after API access and own-voice recording are configured.
7. Short report (maximum four pages), demo video (maximum two minutes), public repository, and reproducible submission ZIP.

## Risks and mitigations

- Conflicting documents: enforce the explicit precedence hierarchy and preserve source metadata.
- False grounding: cite section IDs, return abstention when retrieval is weak, and audit citations.
- Unsafe lookup: tool boundary, one proof at a time, one retry, ephemeral verification state.
- Over-escalation or missed escalation: encode the dataset guide triggers and test practice conversations.
- Language coverage: evaluate by language and disclose lack of native review for any unsupported dialect.
- API or voice credentials: keep integrations behind configuration; never commit secrets. Gnani is mandatory for both speech directions; no fallback speech service is allowed.
- Dataset's fixed date differs from wall clock: inject 2026-10-20 explicitly for calculations.

## Report outline

Abstract; problem and dataset; design; retrieval and structured tools; safety controls; evaluation methodology; results; error analysis; demo screenshots; limitations; future work; references and reproducibility instructions.

